"""App-facing room package facade (PRD-003 REQ-003-004).

Apps read surfaces, roles, floor plane, confidence, and generated-texture
handles through this API — not by opening OpenCV or companion internals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lumur.app.metrics import compute_surface_metrics
from lumur.schema.room import load_room_package
from lumur.surface_roles import assign_surface_roles, build_role_index


@dataclass(frozen=True)
class SurfaceRecord:
    """One allocatable surface from the current room package."""

    surface_id: int
    kind: str
    label: str
    roles: tuple[str, ...]
    width_m: float
    mean_confidence: float
    normal: tuple[float, float, float] | None = None
    d: float | None = None
    inlier_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.surface_id,
            "kind": self.kind,
            "label": self.label,
            "roles": list(self.roles),
            "width_m": self.width_m,
            "mean_confidence": self.mean_confidence,
            "normal": list(self.normal) if self.normal is not None else None,
            "d": self.d,
            "inlier_count": self.inlier_count,
        }


@dataclass
class RoomServices:
    """Room-as-file-system view over a loaded ``lumur.room`` package."""

    package_dir: Path
    document: dict[str, Any]
    surfaces: list[SurfaceRecord]
    role_index: dict[str, int]
    floor_plane_id: int | None
    generated_textures: dict[str, Any] = field(default_factory=dict)
    godot_dir: Path | None = None
    paint_manifest: dict[str, Any] | None = None

    @classmethod
    def load(cls, package_dir: str | Path) -> RoomServices:
        package_dir = Path(package_dir)
        doc, points, _projector_map = load_room_package(package_dir)
        planes = list(doc.get("planes") or [])
        roles_by_id = assign_surface_roles(planes)
        role_index = build_role_index(roles_by_id)

        metrics = compute_surface_metrics(points, planes, doc.get("floor_plane_id"))
        surfaces: list[SurfaceRecord] = []
        for plane in planes:
            pid = int(plane["plane_id"])
            kind = str(plane.get("kind") or "surface")
            if kind == "non_planar":
                continue
            m = metrics.get(pid, {})
            normal = plane.get("normal")
            surfaces.append(
                SurfaceRecord(
                    surface_id=pid,
                    kind=kind,
                    label=str(plane.get("label") or f"surface_{pid}"),
                    roles=tuple(roles_by_id.get(pid, [str(plane.get("label") or pid)])),
                    width_m=float(m.get("width_m", 0.0)),
                    mean_confidence=float(m.get("mean_confidence", 0.0)),
                    normal=tuple(float(x) for x in normal) if normal is not None else None,
                    d=float(plane["d"]) if plane.get("d") is not None else None,
                    inlier_count=int(plane.get("inlier_count") or 0),
                )
            )

        godot_dir, paint_manifest, generated = _load_godot_side(package_dir, doc)
        # Prefer role_index from paint export when present (canonical for Godot).
        if paint_manifest and isinstance(paint_manifest.get("role_index"), dict):
            role_index = {
                str(k): int(v) for k, v in paint_manifest["role_index"].items()
            }
            # Merge paint surface metrics if export already computed them.
            by_id = {s.surface_id: s for s in surfaces}
            enriched: list[SurfaceRecord] = []
            for entry in paint_manifest.get("surfaces") or []:
                if not isinstance(entry, dict):
                    continue
                pid = int(entry.get("id", -1))
                base = by_id.get(pid)
                if base is None:
                    continue
                width = entry.get("width_m", base.width_m)
                conf = entry.get("mean_confidence", base.mean_confidence)
                roles = entry.get("roles") or list(base.roles)
                enriched.append(
                    SurfaceRecord(
                        surface_id=base.surface_id,
                        kind=str(entry.get("kind") or base.kind),
                        label=str(entry.get("label") or base.label),
                        roles=tuple(str(r) for r in roles),
                        width_m=float(width),
                        mean_confidence=float(conf),
                        normal=base.normal,
                        d=base.d,
                        inlier_count=base.inlier_count,
                    )
                )
            if enriched:
                surfaces = enriched

        return cls(
            package_dir=package_dir,
            document=doc,
            surfaces=surfaces,
            role_index=role_index,
            floor_plane_id=(
                int(doc["floor_plane_id"])
                if doc.get("floor_plane_id") is not None
                else None
            ),
            generated_textures=generated,
            godot_dir=godot_dir,
            paint_manifest=paint_manifest,
        )

    def list_roles(self) -> list[str]:
        return sorted(self.role_index.keys())

    def surface_by_id(self, surface_id: int) -> SurfaceRecord | None:
        for s in self.surfaces:
            if s.surface_id == surface_id:
                return s
        return None

    def surface_by_role(self, role: str) -> SurfaceRecord | None:
        sid = self.role_index.get(role)
        if sid is None:
            return None
        return self.surface_by_id(int(sid))

    def generated_texture(self, key: str) -> dict[str, Any] | None:
        handle = self.generated_textures.get(key)
        return dict(handle) if isinstance(handle, dict) else None


def _load_godot_side(
    package_dir: Path, doc: dict[str, Any]
) -> tuple[Path | None, dict[str, Any] | None, dict[str, Any]]:
    arrays = doc.get("arrays") or {}
    godot_rel = arrays.get("godot")
    candidates: list[Path] = []
    if isinstance(godot_rel, str) and godot_rel:
        candidates.append(package_dir / godot_rel)
        # arrays.godot may point at the manifest file itself.
        if godot_rel.endswith(".json"):
            candidates.append(package_dir / Path(godot_rel).parent)
    candidates.append(package_dir / "godot" / "paint_manifest.json")
    candidates.append(package_dir / "godot")

    for cand in candidates:
        manifest_path = cand
        godot_dir = cand
        if cand.is_dir():
            manifest_path = cand / "paint_manifest.json"
            godot_dir = cand
        elif cand.name == "paint_manifest.json":
            godot_dir = cand.parent
        else:
            continue
        if not manifest_path.is_file():
            continue
        paint = json.loads(manifest_path.read_text(encoding="utf-8"))
        generated = dict(paint.get("generated_textures") or {})
        return godot_dir, paint, generated
    return None, None, {}
