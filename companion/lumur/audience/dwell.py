"""Minimum dwell + debounce gate for zone actions (passers-by rejection).

Shared by optional Story Stage audience steering (bridge package) and
PRD-003 zone→app switching. Lives in Lumur core so the bridge is not
required for zone→app switching.

Semantics match the PRD-002 slice 4 contract:
- ``min_dwell_s`` inside a zone before an action may fire
- ``debounce_s`` per zone after a successful fire
- leave before dwell completes → ``dwell_too_short`` rejection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DwellWatch:
    person_id: int
    zone_id: str
    enter_t: float
    last_seen_t: float
    fired: bool = False


@dataclass
class DwellFire:
    """One successful dwell completion."""

    person_id: int
    zone_id: str
    dwell_s: float
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "zone_dwell",
            "person_id": self.person_id,
            "zone_id": self.zone_id,
            "dwell_s": self.dwell_s,
            "timestamp": self.timestamp,
        }


@dataclass
class DwellGate:
    """Track zone occupancy and emit fires only after dwell + debounce."""

    min_dwell_s: float = 1.5
    debounce_s: float = 0.8
    _dwell: dict[str, DwellWatch] = field(default_factory=dict)
    _last_fire_t: dict[str, float] = field(default_factory=dict)
    rejected: list[dict[str, Any]] = field(default_factory=list)

    def reset(self) -> None:
        self._dwell.clear()
        self._last_fire_t.clear()
        self.rejected.clear()

    def on_zone_enter(
        self, *, person_id: int, zone_id: str, timestamp: float
    ) -> None:
        key = f"{int(person_id)}|{zone_id}"
        self._dwell[key] = DwellWatch(
            person_id=int(person_id),
            zone_id=str(zone_id),
            enter_t=float(timestamp),
            last_seen_t=float(timestamp),
        )

    def on_zone_leave(
        self, *, person_id: int, zone_id: str, timestamp: float
    ) -> None:
        key = f"{int(person_id)}|{zone_id}"
        watch = self._dwell.pop(key, None)
        if watch is None or watch.fired:
            return
        dwell = float(timestamp) - watch.enter_t
        if dwell < self.min_dwell_s:
            self.rejected.append(
                {
                    "reason": "dwell_too_short",
                    "dwell_s": dwell,
                    "min_dwell_s": self.min_dwell_s,
                    "person_id": int(person_id),
                    "zone_id": str(zone_id),
                    "timestamp": float(timestamp),
                }
            )

    def note_seen(
        self, *, person_id: int, zone_id: str, timestamp: float
    ) -> None:
        key = f"{int(person_id)}|{zone_id}"
        watch = self._dwell.get(key)
        if watch is not None:
            watch.last_seen_t = float(timestamp)

    def tick(self, timestamp: float) -> list[DwellFire]:
        """Evaluate open watches; return fires that cleared dwell + debounce."""
        fired: list[DwellFire] = []
        ts = float(timestamp)
        for key, watch in list(self._dwell.items()):
            if watch.fired:
                continue
            dwell = ts - watch.enter_t
            if dwell < self.min_dwell_s:
                continue
            last = self._last_fire_t.get(watch.zone_id, -1e9)
            if (ts - last) < self.debounce_s:
                self.rejected.append(
                    {
                        "reason": "zone_debounce",
                        "zone_id": watch.zone_id,
                        "timestamp": ts,
                    }
                )
                watch.fired = True
                continue
            watch.fired = True
            self._last_fire_t[watch.zone_id] = ts
            fired.append(
                DwellFire(
                    person_id=watch.person_id,
                    zone_id=watch.zone_id,
                    dwell_s=dwell,
                    timestamp=ts,
                )
            )
        return fired

    def process_event(self, event: dict[str, Any]) -> list[DwellFire]:
        """Handle one ``zone_enter`` / ``zone_leave``; tick at event time."""
        ev_type = str(event.get("type", ""))
        ts = float(event.get("timestamp", 0.0))
        if ev_type == "zone_enter":
            self.on_zone_enter(
                person_id=int(event.get("person_id", -1)),
                zone_id=str(event.get("zone_id", "")),
                timestamp=ts,
            )
        elif ev_type == "zone_leave":
            self.on_zone_leave(
                person_id=int(event.get("person_id", -1)),
                zone_id=str(event.get("zone_id", "")),
                timestamp=ts,
            )
        return self.tick(ts)
