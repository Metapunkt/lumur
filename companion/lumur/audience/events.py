"""Audience event vocabulary (PRD-002 REQ-002-013).

Stable companion → Lumur → bridge types. Footstep remains
``lumur.track.footsteps.FootstepEvent``; this module covers presence / zones /
gathering. All serialize to the ADR 0014 ``lumur.event`` envelope payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AudienceEventType = Literal[
    "presence",
    "zone_enter",
    "zone_leave",
    "gathering",
]


@dataclass(frozen=True)
class AudienceEvent:
    """One room-runtime audience event (not footstep)."""

    type: AudienceEventType
    timestamp: float
    person_ids: tuple[int, ...] = ()
    count: int = 0
    person_id: int | None = None
    zone_id: str | None = None
    cluster_id: str | None = None
    position_floor: tuple[float, float] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "type": self.type,
            "timestamp": float(self.timestamp),
        }
        if self.person_ids:
            doc["person_ids"] = [int(p) for p in self.person_ids]
        if self.count or self.type == "presence":
            doc["count"] = int(self.count if self.count else len(self.person_ids))
        if self.person_id is not None:
            doc["person_id"] = int(self.person_id)
        if self.zone_id is not None:
            doc["zone_id"] = str(self.zone_id)
        if self.cluster_id is not None:
            doc["cluster_id"] = str(self.cluster_id)
        if self.position_floor is not None:
            doc["position_floor"] = [
                float(self.position_floor[0]),
                float(self.position_floor[1]),
            ]
        if self.meta:
            doc["meta"] = dict(self.meta)
        return doc

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AudienceEvent:
        pids = tuple(int(p) for p in (raw.get("person_ids") or []))
        pf = raw.get("position_floor")
        position_floor = None
        if isinstance(pf, (list, tuple)) and len(pf) >= 2:
            position_floor = (float(pf[0]), float(pf[1]))
        return cls(
            type=str(raw["type"]),  # type: ignore[arg-type]
            timestamp=float(raw.get("timestamp", 0.0)),
            person_ids=pids,
            count=int(raw.get("count", len(pids))),
            person_id=int(raw["person_id"]) if raw.get("person_id") is not None else None,
            zone_id=str(raw["zone_id"]) if raw.get("zone_id") is not None else None,
            cluster_id=(
                str(raw["cluster_id"]) if raw.get("cluster_id") is not None else None
            ),
            position_floor=position_floor,
            meta=dict(raw.get("meta") or {}),
        )
