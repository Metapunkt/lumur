"""Map audience events → Story Stage inputs (opt-in, debounced).

Only scenarios with an enabled ``lumur_audience`` section steer story state
(REQ-002-011). Debounce + minimum dwell reject passers-by.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from lumur.audience.detector import AudienceState
from lumur.audience.events import AudienceEvent
from lumur_synesyn.audience_config import LumurAudienceConfig, audience_config_from_scenario
from lumur_synesyn.mock_story_stage import MockStoryStageReceiver, StageAction


@dataclass
class _DwellWatch:
    person_id: int
    zone_id: str
    enter_t: float
    last_seen_t: float
    fired: bool = False


@dataclass
class AudienceSteeringBridge:
    """Filter audience events and drive a Story Stage receiver when opted in."""

    config: LumurAudienceConfig
    receiver: MockStoryStageReceiver
    # person_id|zone_id → dwell watch
    _dwell: dict[str, _DwellWatch] = field(default_factory=dict)
    # zone_id → last successful fire timestamp (debounce)
    _last_fire_t: dict[str, float] = field(default_factory=dict)
    _last_gathering_fire_t: float = -1e9
    _intensity: float = 0.0
    rejected: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_scenario(
        cls,
        scenario: Mapping[str, Any] | None,
        receiver: MockStoryStageReceiver | None = None,
    ) -> AudienceSteeringBridge:
        cfg = audience_config_from_scenario(scenario)
        recv = receiver or MockStoryStageReceiver(scenario=dict(scenario or {}))
        recv.steering_enabled = cfg.enabled
        recv.scenario = dict(scenario or {})
        return cls(config=cfg, receiver=recv)

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    def audience_state_for_metaprompt(self, state: AudienceState) -> dict[str, Any]:
        """Structured + text summary for opted-in scenario metaprompts."""
        if not self.enabled:
            return {
                "enabled": False,
                "text": "",
                "state": None,
            }
        return {
            "enabled": True,
            "text": state.summary_text(),
            "state": state.to_dict(),
            "intensity": float(self._intensity),
            "parameters": dict(self.receiver.parameters),
        }

    def process_event(self, event: AudienceEvent | dict[str, Any]) -> list[StageAction]:
        """Process one audience or footstep event. Returns applied stage actions."""
        if hasattr(event, "to_dict"):
            payload = event.to_dict()
            ev_type = str(payload.get("type", ""))
            ts = float(payload.get("timestamp", 0.0))
        else:
            payload = dict(event)
            ev_type = str(payload.get("type", ""))
            ts = float(payload.get("timestamp", 0.0))

        # Ambience always (REQ-002-012) — even when steering is off.
        self.receiver.forward_ambience(payload, timestamp=ts)

        if not self.enabled:
            return []

        applied: list[StageAction] = []

        if ev_type == "presence":
            count = int(payload.get("count", len(payload.get("person_ids") or [])))
            target = min(1.0, max(0.0, count * self.config.presence_intensity_scale))
            self._intensity = target
            action = StageAction(
                kind="set_parameter",
                timestamp=ts,
                parameter=self.config.intensity_parameter,
                value=target,
                source_event=payload,
            )
            if self.receiver.apply(action, steered=True):
                applied.append(action)

        elif ev_type == "zone_enter":
            pid = int(payload.get("person_id", -1))
            zid = str(payload.get("zone_id", ""))
            key = f"{pid}|{zid}"
            self._dwell[key] = _DwellWatch(
                person_id=pid, zone_id=zid, enter_t=ts, last_seen_t=ts
            )

        elif ev_type == "zone_leave":
            pid = int(payload.get("person_id", -1))
            zid = str(payload.get("zone_id", ""))
            key = f"{pid}|{zid}"
            watch = self._dwell.pop(key, None)
            if watch is not None and not watch.fired:
                dwell = ts - watch.enter_t
                if dwell < self.config.min_dwell_s:
                    self.rejected.append(
                        {
                            "reason": "dwell_too_short",
                            "dwell_s": dwell,
                            "min_dwell_s": self.config.min_dwell_s,
                            "event": payload,
                        }
                    )

        elif ev_type == "gathering":
            if (ts - self._last_gathering_fire_t) < self.config.debounce_s:
                self.rejected.append(
                    {"reason": "gathering_debounce", "event": payload}
                )
            else:
                action = self._action_from_gathering(payload, ts)
                if action is not None and self.receiver.apply(action, steered=True):
                    self._last_gathering_fire_t = ts
                    applied.append(action)

        elif ev_type == "footstep":
            delta = float(self.config.footstep_intensity_delta)
            self._intensity = min(1.0, self._intensity + delta)
            action = StageAction(
                kind="set_parameter",
                timestamp=ts,
                parameter=self.config.intensity_parameter,
                value=self._intensity,
                source_event=payload,
            )
            if self.receiver.apply(action, steered=True):
                applied.append(action)

        return applied

    def tick(self, timestamp: float, state: AudienceState | None = None) -> list[StageAction]:
        """Evaluate dwell watches (call each frame / after event batch)."""
        if not self.enabled:
            return []
        applied: list[StageAction] = []
        # Refresh last_seen from audience state occupants when provided.
        if state is not None:
            for zid, pids in state.occupants.items():
                for pid in pids:
                    key = f"{pid}|{zid}"
                    if key in self._dwell:
                        self._dwell[key].last_seen_t = float(timestamp)

        for key, watch in list(self._dwell.items()):
            if watch.fired:
                continue
            dwell = float(timestamp) - watch.enter_t
            if dwell < self.config.min_dwell_s:
                continue
            # Debounce per zone.
            last = self._last_fire_t.get(watch.zone_id, -1e9)
            if (float(timestamp) - last) < self.config.debounce_s:
                self.rejected.append(
                    {
                        "reason": "zone_debounce",
                        "zone_id": watch.zone_id,
                        "timestamp": float(timestamp),
                    }
                )
                watch.fired = True  # consume this dwell attempt
                continue
            za = self.config.action_for_zone(watch.zone_id)
            if za is None:
                # Default: choose_option index 0 for unknown mapped zones — skip.
                continue
            action = StageAction(
                kind=za.action if za.action != "cue" else "set_parameter",
                timestamp=float(timestamp),
                option_index=za.option_index,
                option_label=za.option_label or za.cue,
                parameter=za.parameter or (self.config.mood_parameter if za.cue else None),
                value=za.value if za.value is not None else za.cue,
                source_event={
                    "type": "zone_dwell",
                    "person_id": watch.person_id,
                    "zone_id": watch.zone_id,
                    "dwell_s": dwell,
                },
                meta={"zone_action": za.to_dict()},
            )
            # Normalise choose_option / advance_beat kinds.
            if za.action == "choose_option":
                action = StageAction(
                    kind="choose_option",
                    timestamp=float(timestamp),
                    option_index=za.option_index,
                    option_label=za.option_label,
                    source_event=action.source_event,
                    meta=action.meta,
                )
            elif za.action == "advance_beat":
                action = StageAction(
                    kind="advance_beat",
                    timestamp=float(timestamp),
                    source_event=action.source_event,
                    meta=action.meta,
                )
            if self.receiver.apply(action, steered=True):
                applied.append(action)
                watch.fired = True
                self._last_fire_t[watch.zone_id] = float(timestamp)
        return applied

    def process_batch(
        self,
        events: list[AudienceEvent | dict[str, Any]],
        *,
        timestamp: float | None = None,
        state: AudienceState | None = None,
    ) -> list[StageAction]:
        applied: list[StageAction] = []
        last_ts = timestamp if timestamp is not None else 0.0
        for ev in events:
            if hasattr(ev, "timestamp"):
                last_ts = float(ev.timestamp)
            elif isinstance(ev, dict):
                last_ts = float(ev.get("timestamp", last_ts))
            applied.extend(self.process_event(ev))
        applied.extend(self.tick(float(last_ts), state=state))
        return applied

    def _action_from_gathering(
        self, payload: dict[str, Any], ts: float
    ) -> StageAction | None:
        kind = self.config.gathering_action
        if kind == "advance_beat":
            return StageAction(
                kind="advance_beat", timestamp=ts, source_event=payload
            )
        if kind == "choose_option":
            return StageAction(
                kind="choose_option",
                timestamp=ts,
                option_index=0,
                source_event=payload,
            )
        if kind.startswith("set_parameter") or kind == "set_parameter":
            return StageAction(
                kind="set_parameter",
                timestamp=ts,
                parameter=self.config.mood_parameter,
                value="gathering",
                source_event=payload,
            )
        return StageAction(kind="advance_beat", timestamp=ts, source_event=payload)
