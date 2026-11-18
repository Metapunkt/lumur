"""Interaction zones on floor surface coordinates (u, v metres).

Zones are authored in the same floor u/v frame as footstep ``position_floor``
(default world +X / +Z — see ``FootstepDetector.floor_uv``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence

ZoneKind = Literal["rect", "polygon"]


@dataclass(frozen=True)
class FloorZone:
    """Named region on the scanned floor plane."""

    zone_id: str
    kind: ZoneKind = "rect"
    # Axis-aligned rectangle in floor u/v (inclusive bounds).
    u_min: float = 0.0
    u_max: float = 0.0
    v_min: float = 0.0
    v_max: float = 0.0
    # Polygon vertices as (u, v) when kind == "polygon".
    polygon: tuple[tuple[float, float], ...] = ()
    label: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def contains(self, u: float, v: float) -> bool:
        return point_in_zone(u, v, self)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "zone_id": self.zone_id,
            "kind": self.kind,
            "label": self.label or self.zone_id,
        }
        if self.kind == "rect":
            doc.update(
                {
                    "u_min": float(self.u_min),
                    "u_max": float(self.u_max),
                    "v_min": float(self.v_min),
                    "v_max": float(self.v_max),
                }
            )
        else:
            doc["polygon"] = [[float(a), float(b)] for a, b in self.polygon]
        if self.meta:
            doc["meta"] = dict(self.meta)
        return doc

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> FloorZone:
        kind = str(raw.get("kind", "rect")).lower()
        poly_raw = raw.get("polygon") or []
        polygon = tuple(
            (float(p[0]), float(p[1])) for p in poly_raw if len(p) >= 2
        )
        return cls(
            zone_id=str(raw["zone_id"]),
            kind="polygon" if kind == "polygon" else "rect",
            u_min=float(raw.get("u_min", 0.0)),
            u_max=float(raw.get("u_max", 0.0)),
            v_min=float(raw.get("v_min", 0.0)),
            v_max=float(raw.get("v_max", 0.0)),
            polygon=polygon,
            label=str(raw.get("label", "")),
            meta=dict(raw.get("meta") or {}),
        )

    @classmethod
    def rect(
        cls,
        zone_id: str,
        u_min: float,
        u_max: float,
        v_min: float,
        v_max: float,
        **kwargs: Any,
    ) -> FloorZone:
        return cls(
            zone_id=zone_id,
            kind="rect",
            u_min=float(min(u_min, u_max)),
            u_max=float(max(u_min, u_max)),
            v_min=float(min(v_min, v_max)),
            v_max=float(max(v_min, v_max)),
            **kwargs,
        )


def point_in_zone(u: float, v: float, zone: FloorZone) -> bool:
    if zone.kind == "rect":
        return zone.u_min <= u <= zone.u_max and zone.v_min <= v <= zone.v_max
    if len(zone.polygon) < 3:
        return False
    return _point_in_polygon(u, v, zone.polygon)


def _point_in_polygon(
    u: float, v: float, polygon: Sequence[tuple[float, float]]
) -> bool:
    """Ray-casting even-odd rule."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        ui, vi = polygon[i]
        uj, vj = polygon[j]
        if ((vi > v) != (vj > v)) and (
            u < (uj - ui) * (v - vi) / ((vj - vi) + 1e-12) + ui
        ):
            inside = not inside
        j = i
    return inside


def zones_from_documents(docs: Sequence[dict[str, Any]] | None) -> list[FloorZone]:
    if not docs:
        return []
    out: list[FloorZone] = []
    for raw in docs:
        if isinstance(raw, dict) and "zone_id" in raw:
            out.append(FloorZone.from_dict(raw))
    return out
