"""Export Godot-friendly paint assets from a ``lumur.room`` package.

GDScript cannot read ``.npz`` conveniently, so the companion writes PNG
lookup textures plus a JSON manifest under ``<package>/godot/``. See
ADR 0013 and ``docs/godot/paint-mode.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from lumur.app.metrics import compute_surface_metrics
from lumur.schema.room import load_room_package
from lumur.surface_roles import assign_surface_roles, build_role_index

GODOT_SUBDIR = "godot"
MANIFEST_FILENAME = "paint_manifest.json"
SURFACE_ID_FILENAME = "surface_id.png"
CONFIDENCE_FILENAME = "confidence.png"
LOOKUP_FILENAME = "lookup.png"  # RGB8: R=cam_u_norm, G=cam_v_norm, B=valid

# Re-export for callers that imported roles from this module.
__all__ = [
    "GODOT_SUBDIR",
    "MANIFEST_FILENAME",
    "SURFACE_ID_FILENAME",
    "CONFIDENCE_FILENAME",
    "LOOKUP_FILENAME",
    "assign_surface_roles",
    "build_role_index",
    "export_godot_paint_assets",
    "scatter_surface_id_to_projector",
]


def scatter_surface_id_to_projector(
    camera_surface_id: np.ndarray,
    projector_map: dict[str, np.ndarray],
) -> np.ndarray:
    """Build a projector-resolution ``surface_id`` map via correspondence."""
    cam_u = projector_map["cam_u"]
    cam_v = projector_map["cam_v"]
    valid = projector_map["valid"].astype(bool)
    proj_h, proj_w = cam_u.shape
    cam_h, cam_w = camera_surface_id.shape
    out = np.zeros((proj_h, proj_w), dtype=np.int32)
    if not np.any(valid):
        return out
    ui = np.clip(np.rint(cam_u[valid]).astype(np.int32), 0, cam_w - 1)
    vi = np.clip(np.rint(cam_v[valid]).astype(np.int32), 0, cam_h - 1)
    flat = out.ravel()
    flat[np.flatnonzero(valid)] = camera_surface_id[vi, ui]
    return flat.reshape(out.shape)


def _write_png_gray_u8(path: Path, image: np.ndarray) -> None:
    ok = cv2.imwrite(str(path), image.astype(np.uint8))
    if not ok:
        raise OSError(f"failed to write {path}")


def _write_lookup_png(
    path: Path,
    cam_u: np.ndarray,
    cam_v: np.ndarray,
    valid: np.ndarray,
    camera_size: tuple[int, int],
) -> None:
    """RGB8 lookup: RG = normalised camera UV, B = valid mask.

    Camera distortion is already baked into the Gray-code correspondence, so
    this texture is the distortion/geometry UV lookup for the final pass
    (scratchpad: bake distortion into a lookup texture).
    """
    cam_w, cam_h = camera_size
    r = np.zeros(cam_u.shape, dtype=np.uint8)
    g = np.zeros(cam_v.shape, dtype=np.uint8)
    b = (valid.astype(bool) * 255).astype(np.uint8)
    finite = valid.astype(bool) & np.isfinite(cam_u) & np.isfinite(cam_v)
    if np.any(finite):
        r[finite] = np.clip(
            np.rint(cam_u[finite] / max(cam_w, 1) * 255.0), 0, 255
        ).astype(np.uint8)
        g[finite] = np.clip(
            np.rint(cam_v[finite] / max(cam_h, 1) * 255.0), 0, 255
        ).astype(np.uint8)
    # OpenCV writes BGR.
    bgr = np.stack([b, g, r], axis=-1)
    ok = cv2.imwrite(str(path), bgr)
    if not ok:
        raise OSError(f"failed to write {path}")


def export_godot_paint_assets(
    room_package_dir: str | Path,
    *,
    output_subdir: str = GODOT_SUBDIR,
    confidence_threshold: float = 0.05,
) -> Path:
    """Write ``godot/`` paint assets into an existing room package.

    Returns the path to the Godot asset directory.
    """
    room_package_dir = Path(room_package_dir)
    doc, points, projector_map = load_room_package(room_package_dir)

    cam_w, cam_h = (
        int(doc["camera_resolution"][0]),
        int(doc["camera_resolution"][1]),
    )
    proj_w, proj_h = (
        int(doc["projector_resolution"][0]),
        int(doc["projector_resolution"][1]),
    )

    surface_id_cam = np.asarray(points["surface_id"], dtype=np.int32)
    surface_id_proj = scatter_surface_id_to_projector(surface_id_cam, projector_map)
    confidence = np.asarray(projector_map["confidence"], dtype=np.float32)
    valid = np.asarray(projector_map["valid"]).astype(bool)

    out_dir = room_package_dir / output_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Clamp ids into 0..255 for R8 texture (PRD-001 rooms have few planes).
    if int(surface_id_proj.max(initial=0)) > 255:
        raise ValueError("surface_id exceeds 255; widen paint texture format")
    _write_png_gray_u8(out_dir / SURFACE_ID_FILENAME, surface_id_proj)
    conf_u8 = np.clip(np.rint(confidence * 255.0), 0, 255).astype(np.uint8)
    conf_u8 = np.where(valid, conf_u8, 0)
    _write_png_gray_u8(out_dir / CONFIDENCE_FILENAME, conf_u8)
    _write_lookup_png(
        out_dir / LOOKUP_FILENAME,
        np.asarray(projector_map["cam_u"], dtype=np.float32),
        np.asarray(projector_map["cam_v"], dtype=np.float32),
        valid,
        (cam_w, cam_h),
    )

    planes = list(doc.get("planes") or [])
    roles = assign_surface_roles(planes)
    metrics = compute_surface_metrics(points, planes, doc.get("floor_plane_id"))
    surfaces = []
    for plane in planes:
        pid = int(plane["plane_id"])
        m = metrics.get(pid, {})
        surfaces.append(
            {
                "id": pid,
                "kind": plane.get("kind"),
                "label": plane.get("label"),
                "roles": roles.get(pid, [str(plane.get("label") or pid)]),
                "normal": plane.get("normal"),
                "d": plane.get("d"),
                # Fit metrics for Godot / room-fit (ADR 0017 / 0018). Additive.
                "width_m": float(m.get("width_m", 0.0)),
                "mean_confidence": float(m.get("mean_confidence", 0.0)),
                "inlier_count": int(plane.get("inlier_count") or 0),
            }
        )

    manifest = {
        "schema": "lumur.paint_godot",
        "schema_version": "1.0",
        "room_schema": doc.get("schema"),
        "room_schema_version": doc.get("schema_version"),
        "projector_resolution": [proj_w, proj_h],
        "camera_resolution": [cam_w, cam_h],
        "floor_plane_id": doc.get("floor_plane_id"),
        "confidence_threshold_default": float(confidence_threshold),
        "textures": {
            "surface_id": SURFACE_ID_FILENAME,
            "confidence": CONFIDENCE_FILENAME,
            "lookup": LOOKUP_FILENAME,
        },
        "texture_encoding": {
            "surface_id": "R8 pixel value = surface_id (0 = none)",
            "confidence": "R8 pixel value = confidence * 255",
            "lookup": (
                "RGB8; R = cam_u / camera_width * 255, "
                "G = cam_v / camera_height * 255, B = 255 if valid else 0. "
                "Distortion is baked into the Gray-code correspondence."
            ),
        },
        "surfaces": surfaces,
        "role_index": build_role_index(roles),
    }
    (out_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    # Point the room manifest at the Godot assets without breaking v1.0 readers.
    arrays = dict(doc.get("arrays") or {})
    arrays["godot"] = f"{output_subdir}/{MANIFEST_FILENAME}"
    doc["arrays"] = arrays
    (room_package_dir / "room.json").write_text(
        json.dumps(doc, indent=2) + "\n", encoding="utf-8"
    )
    return out_dir
