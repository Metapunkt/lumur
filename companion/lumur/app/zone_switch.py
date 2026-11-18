"""Optional zone→app switching (PRD-003 REQ-003-013).

Configuration maps floor zone ids to installed app ids. Standing in a zone
for ``min_dwell_s`` (with ``debounce_s``) switches the active app. Absent
configuration, zones do not switch apps — they may still feed permitted
inputs. Dwell / debounce reuse :class:`lumur.audience.dwell.DwellGate`
(same semantics as audience steering). Host path — not an ordinary app
permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from lumur.audience.dwell import DwellFire, DwellGate
from lumur.app.input_bus import AppInputBus, AppInputSession
from lumur.app.lifecycle import AppLifecycle, LifecycleError


@dataclass
class ZoneSwitchConfig:
    """Zone id → app id mapping plus dwell / debounce."""

    zone_to_app: dict[str, str] = field(default_factory=dict)
    min_dwell_s: float = 1.5
    debounce_s: float = 0.8
    enabled: bool = True

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> ZoneSwitchConfig:
        if not raw:
            return cls(enabled=False)
        mapping = raw.get("zone_to_app") or raw.get("zones") or {}
        if not isinstance(mapping, Mapping):
            mapping = {}
        enabled = bool(raw.get("enabled", True)) and bool(mapping)
        return cls(
            zone_to_app={str(k): str(v) for k, v in mapping.items()},
            min_dwell_s=float(raw.get("min_dwell_s", raw.get("dwell_s", 1.5))),
            debounce_s=float(raw.get("debounce_s", raw.get("debounce", 0.8))),
            enabled=enabled,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "zone_to_app": dict(self.zone_to_app),
            "min_dwell_s": self.min_dwell_s,
            "debounce_s": self.debounce_s,
        }


@dataclass
class ZoneAppSwitcher:
    """Privileged host that listens for zone dwell and switches apps."""

    lifecycle: AppLifecycle
    config: ZoneSwitchConfig
    host_id: str = "lumur.launcher.zone_switch"
    gate: DwellGate = field(init=False)
    host_session: AppInputSession | None = None
    switches: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    _gate_reject_cursor: int = 0

    def __post_init__(self) -> None:
        self.gate = DwellGate(
            min_dwell_s=self.config.min_dwell_s,
            debounce_s=self.config.debounce_s,
        )

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled and self.config.zone_to_app)

    def attach_bus(self, bus: AppInputBus | None = None) -> AppInputSession | None:
        """Register the host path on the input bus (zone_enter / zone_leave)."""
        if not self.enabled:
            return None
        bus = bus or self.lifecycle.input_bus
        self.host_session = bus.register_host(
            self.host_id, allowed=["zone_enter", "zone_leave"]
        )
        bus.subscribe(self.host_id, "zone_enter")
        bus.subscribe(self.host_id, "zone_leave")
        return self.host_session

    def process_event(
        self, event: Any, *, publish: bool = True
    ) -> list[dict[str, Any]]:
        """Feed one audience event; return switch records if any fired.

        When ``publish`` is True (default), the event is also fanned out on the
        lifecycle input bus so host + apps get their filtered views.
        """
        if hasattr(event, "to_dict"):
            payload = dict(event.to_dict())
        else:
            payload = dict(event)
        if publish:
            self.lifecycle.input_bus.publish(payload)
        if not self.enabled:
            return []
        fires = self.gate.process_event(payload)
        return self._apply_fires(fires)

    def tick(self, timestamp: float) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        return self._apply_fires(self.gate.tick(timestamp))

    def inject_and_tick(
        self, events: list[Any], *, final_t: float | None = None
    ) -> list[dict[str, Any]]:
        """Process a batch (sim helper); tick at last event time or ``final_t``."""
        applied: list[dict[str, Any]] = []
        last_t = 0.0
        for event in events:
            applied.extend(self.process_event(event))
            if hasattr(event, "to_dict"):
                payload = event.to_dict()
            else:
                payload = dict(event)
            last_t = float(payload.get("timestamp", last_t))
        if final_t is not None:
            applied.extend(self.tick(float(final_t)))
        elif events:
            applied.extend(self.tick(last_t))
        return applied

    def _drain_gate_rejections(self) -> None:
        new = self.gate.rejected[self._gate_reject_cursor :]
        if new:
            self.rejected.extend(new)
            self._gate_reject_cursor = len(self.gate.rejected)

    def _apply_fires(self, fires: list[DwellFire]) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        self._drain_gate_rejections()
        for fire in fires:
            app_id = self.config.zone_to_app.get(fire.zone_id)
            if not app_id:
                continue
            if app_id not in self.lifecycle.apps:
                self.rejected.append(
                    {
                        "reason": "unknown_app",
                        "app_id": app_id,
                        "zone_id": fire.zone_id,
                    }
                )
                continue
            try:
                self.lifecycle.switch(app_id)
            except LifecycleError as exc:
                self.rejected.append(
                    {
                        "reason": exc.reason,
                        "app_id": app_id,
                        "zone_id": fire.zone_id,
                        "error": str(exc),
                    }
                )
                continue
            rec = {
                "action": "zone_switch",
                "app_id": app_id,
                "zone_id": fire.zone_id,
                "person_id": fire.person_id,
                "dwell_s": fire.dwell_s,
                "timestamp": fire.timestamp,
            }
            self.switches.append(rec)
            applied.append(rec)
        return applied
