"""Parse ``[LUMUR_AUDIENCE]`` / ``lumur_audience`` scenario opt-in (REQ-002-011).

Absent or disabled → presence / zone / gathering / footstep must not advance
story state. Lumur still emits the events for ambience (REQ-002-012).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from lumur.audience.zones import FloorZone, zones_from_documents

# Synesyn-style section keys after scenario_loader normalisation.
AUDIENCE_SECTION_KEYS: frozenset[str] = frozenset(
    {
        "lumur_audience",
        "lumur_audience_text",  # free-text fallback if Synesyn loader lacks whitelist
    }
)


@dataclass(frozen=True)
class ZoneAction:
    """What a zone dwell maps to on the Story Stage receiver."""

    zone_id: str
    action: str  # choose_option | advance_beat | set_parameter | cue
    option_index: int | None = None
    option_label: str | None = None
    parameter: str | None = None
    value: float | str | None = None
    cue: str | None = None

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"zone_id": self.zone_id, "action": self.action}
        if self.option_index is not None:
            doc["option_index"] = int(self.option_index)
        if self.option_label is not None:
            doc["option_label"] = self.option_label
        if self.parameter is not None:
            doc["parameter"] = self.parameter
        if self.value is not None:
            doc["value"] = self.value
        if self.cue is not None:
            doc["cue"] = self.cue
        return doc


@dataclass
class LumurAudienceConfig:
    """Opt-in audience steering for one scenario."""

    enabled: bool = False
    zones: list[FloorZone] = field(default_factory=list)
    zone_actions: list[ZoneAction] = field(default_factory=list)
    min_dwell_s: float = 1.5
    debounce_s: float = 0.8
    gathering_min_count: int = 2
    gathering_dwell_s: float = 1.5
    # gathering → advance_beat by default when opted in
    gathering_action: str = "advance_beat"
    # Map presence count → intensity parameter (0..1 scaled)
    intensity_parameter: str = "intensity"
    mood_parameter: str = "mood"
    presence_intensity_scale: float = 0.25  # per person, clamped 0..1
    # Footsteps may bump intensity slightly when opted in (never alone as choice).
    footstep_intensity_delta: float = 0.05
    raw_section: dict[str, Any] = field(default_factory=dict)

    def action_for_zone(self, zone_id: str) -> ZoneAction | None:
        for za in self.zone_actions:
            if za.zone_id == zone_id:
                return za
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "min_dwell_s": float(self.min_dwell_s),
            "debounce_s": float(self.debounce_s),
            "gathering_min_count": int(self.gathering_min_count),
            "gathering_dwell_s": float(self.gathering_dwell_s),
            "gathering_action": self.gathering_action,
            "intensity_parameter": self.intensity_parameter,
            "mood_parameter": self.mood_parameter,
            "zones": [z.to_dict() for z in self.zones],
            "zone_actions": [a.to_dict() for a in self.zone_actions],
        }


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on", "enabled"):
        return True
    if s in ("0", "false", "no", "off", "disabled"):
        return False
    return default


def _parse_zone_action(zone_id: str, raw: Any) -> ZoneAction | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        # Shorthand: "option:0" | "advance" | "mood:calm"
        text = raw.strip()
        low = text.lower()
        if low in ("advance", "advance_beat", "beat"):
            return ZoneAction(zone_id=zone_id, action="advance_beat")
        if low.startswith("option:") or low.startswith("choose:"):
            rest = text.split(":", 1)[1].strip()
            if rest.isdigit():
                return ZoneAction(
                    zone_id=zone_id, action="choose_option", option_index=int(rest)
                )
            return ZoneAction(
                zone_id=zone_id, action="choose_option", option_label=rest
            )
        if ":" in text:
            param, val = text.split(":", 1)
            try:
                num = float(val)
                return ZoneAction(
                    zone_id=zone_id,
                    action="set_parameter",
                    parameter=param.strip(),
                    value=num,
                )
            except ValueError:
                return ZoneAction(
                    zone_id=zone_id,
                    action="set_parameter",
                    parameter=param.strip(),
                    value=val.strip(),
                )
        return ZoneAction(zone_id=zone_id, action="cue", cue=text)
    if not isinstance(raw, Mapping):
        return None
    action = str(raw.get("action", "choose_option")).strip().lower()
    return ZoneAction(
        zone_id=zone_id,
        action=action,
        option_index=(
            int(raw["option_index"]) if raw.get("option_index") is not None else None
        ),
        option_label=(
            str(raw["option_label"]) if raw.get("option_label") is not None else None
        ),
        parameter=str(raw["parameter"]) if raw.get("parameter") is not None else None,
        value=raw.get("value"),
        cue=str(raw["cue"]) if raw.get("cue") is not None else None,
    )


def _parse_free_text_section(text: str) -> dict[str, Any]:
    """Best-effort key:value parse for ``lumur_audience_text`` fallback."""
    out: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, val = line.split(":", 1)
        out[key.strip().lower()] = val.strip()
    if out and "enabled" not in out:
        out["enabled"] = "true"
    return out


def audience_section_from_scenario(
    scenario: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not scenario:
        return None
    for key, value in scenario.items():
        k = str(key).strip().lower()
        if k not in AUDIENCE_SECTION_KEYS:
            continue
        if isinstance(value, Mapping):
            return value
        if isinstance(value, str) and value.strip():
            return _parse_free_text_section(value)
    return None


def audience_config_from_scenario(
    scenario: Mapping[str, Any] | None,
) -> LumurAudienceConfig:
    """Return config; ``enabled`` is False unless the section opts in."""
    section = audience_section_from_scenario(scenario)
    if section is None:
        return LumurAudienceConfig(enabled=False)

    # Presence of the section with empty body still counts as opt-in when
    # enabled is omitted (Synesyn ADR 0027: section presence = feature on).
    enabled = _truthy(section.get("enabled"), default=True)
    zones = zones_from_documents(section.get("zones") or [])
    # Inline rect shorthand: zone_<id>: u_min,u_max,v_min,v_max
    for key, val in section.items():
        ks = str(key).strip().lower()
        if not ks.startswith("zone_") or ks in ("zone_actions", "zones"):
            continue
        zid = ks[len("zone_") :]
        if isinstance(val, str) and "," in val:
            parts = [float(x.strip()) for x in val.split(",")]
            if len(parts) >= 4:
                zones.append(
                    FloorZone.rect(zid, parts[0], parts[1], parts[2], parts[3])
                )

    zone_actions: list[ZoneAction] = []
    actions_raw = section.get("zone_actions") or section.get("actions") or {}
    if isinstance(actions_raw, Mapping):
        for zid, raw in actions_raw.items():
            za = _parse_zone_action(str(zid), raw)
            if za is not None:
                zone_actions.append(za)
    elif isinstance(actions_raw, Sequence) and not isinstance(actions_raw, (str, bytes)):
        for item in actions_raw:
            if isinstance(item, Mapping) and "zone_id" in item:
                za = _parse_zone_action(str(item["zone_id"]), item)
                if za is not None:
                    zone_actions.append(za)

    return LumurAudienceConfig(
        enabled=enabled,
        zones=zones,
        zone_actions=zone_actions,
        min_dwell_s=float(section.get("min_dwell_s", section.get("dwell_s", 1.5))),
        debounce_s=float(section.get("debounce_s", section.get("debounce", 0.8))),
        gathering_min_count=int(
            section.get("gathering_min_count", section.get("gathering_min", 2))
        ),
        gathering_dwell_s=float(section.get("gathering_dwell_s", 1.5)),
        gathering_action=str(section.get("gathering_action", "advance_beat")),
        intensity_parameter=str(section.get("intensity_parameter", "intensity")),
        mood_parameter=str(section.get("mood_parameter", "mood")),
        presence_intensity_scale=float(section.get("presence_intensity_scale", 0.25)),
        footstep_intensity_delta=float(section.get("footstep_intensity_delta", 0.05)),
        raw_section=dict(section),
    )


def is_audience_steering_enabled(scenario: Mapping[str, Any] | None) -> bool:
    return audience_config_from_scenario(scenario).enabled
