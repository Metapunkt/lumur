"""Derive optional mask / depth / normal control images from a room package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from lumur.paint.export import scatter_surface_id_to_projector
from lumur.schema.room import load_room_package


def _scatter_camera_array_to_projector(
    camera_array: np.ndarray,
    projector_map: dict[str, np.ndarray],
    *,
    fill: float | np.ndarray = 0.0,
) -> np.ndarray:
    """Scatter a camera-resolution array into projector resolution via correspondence."""
    cam_u = projector_map["cam_u"]
    cam_v = projector_map["cam_v"]
    valid = projector_map["valid"].astype(bool)
    proj_h, proj_w = cam_u.shape
    if camera_array.ndim == 2:
        out = np.full((proj_h, proj_w), fill, dtype=camera_array.dtype)
    else:
        out = np.full(
            (proj_h, proj_w) + camera_array.shape[2:],
            fill,
            dtype=camera_array.dtype,
        )
    if not np.any(valid):
        return out
    cam_h, cam_w = camera_array.shape[:2]
    ui = np.clip(np.rint(cam_u[valid]).astype(np.int32), 0, cam_w - 1)
    vi = np.clip(np.rint(cam_v[valid]).astype(np.int32), 0, cam_h - 1)
    if camera_array.ndim == 2:
        flat = out.ravel()
        flat[np.flatnonzero(valid)] = camera_array[vi, ui]
        return flat.reshape(out.shape)
    flat = out.reshape(-1, *camera_array.shape[2:])
    flat[np.flatnonzero(valid)] = camera_array[vi, ui]
    return flat.reshape(out.shape)


def resolve_surface_id(
    room_doc: dict[str, Any],
    *,
    surface: str | int,
    role_index: dict[str, int] | None = None,
) -> int:
    if isinstance(surface, int) or (isinstance(surface, str) and surface.isdigit()):
        return int(surface)
    name = str(surface)
    if role_index and name in role_index:
        return int(role_index[name])
    # Fall back: plane label match.
    for plane in room_doc.get("planes") or []:
        if str(plane.get("label") or "") == name:
            return int(plane["plane_id"])
        if str(plane.get("kind") or "") == name and name == "floor":
            return int(plane["plane_id"])
    raise KeyError(f"unknown surface {surface!r}")


def load_role_index(room_package_dir: Path) -> dict[str, int]:
    import json

    manifest_path = room_package_dir / "godot" / "paint_manifest.json"
    if not manifest_path.is_file():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in dict(data.get("role_index") or {}).items()}


def surface_bounds(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return inclusive (x0, y0, x1, y1) bounding box or None if empty."""
    ys, xs = np.where(mask)
    if ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


def _resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    return cv2.resize(image, (int(width), int(height)), interpolation=cv2.INTER_AREA)


def build_control_images(
    room_package_dir: str | Path,
    *,
    surface: str | int,
    width: int,
    height: int,
    want_mask: bool = True,
    want_depth: bool = False,
    want_normal: bool = False,
) -> dict[str, np.ndarray]:
    """Build control images for one surface, resized to ``width``×``height``.

    Returns a dict with any of ``mask`` (uint8 HxW), ``depth`` (uint8 HxW),
    ``normal`` (uint8 HxWx3 BGR). Empty surfaces raise ``ValueError``.
    """
    room_package_dir = Path(room_package_dir)
    doc, points, projector_map = load_room_package(room_package_dir)
    role_index = load_role_index(room_package_dir)
    surface_id = resolve_surface_id(doc, surface=surface, role_index=role_index)

    sid_cam = np.asarray(points["surface_id"], dtype=np.int32)
    sid_proj = scatter_surface_id_to_projector(sid_cam, projector_map)
    mask_full = sid_proj == int(surface_id)
    bounds = surface_bounds(mask_full)
    if bounds is None:
        raise ValueError(f"surface {surface!r} (id={surface_id}) has no projector pixels")
    x0, y0, x1, y1 = bounds
    # Pad slightly so resize has context.
    pad = 1
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(mask_full.shape[0] - 1, y1 + pad)
    x1 = min(mask_full.shape[1] - 1, x1 + pad)

    out: dict[str, np.ndarray] = {}
    if want_mask:
        crop = (mask_full[y0 : y1 + 1, x0 : x1 + 1].astype(np.uint8) * 255)
        out["mask"] = _resize(crop, width, height)

    if want_depth:
        depth_cam = np.asarray(points["depth"], dtype=np.float32)
        depth_proj = _scatter_camera_array_to_projector(depth_cam, projector_map, fill=0.0)
        crop = depth_proj[y0 : y1 + 1, x0 : x1 + 1]
        finite = np.isfinite(crop) & (crop > 0) & mask_full[y0 : y1 + 1, x0 : x1 + 1]
        norm = np.zeros(crop.shape, dtype=np.uint8)
        if np.any(finite):
            vals = crop[finite]
            lo, hi = float(np.percentile(vals, 2)), float(np.percentile(vals, 98))
            if hi <= lo:
                hi = lo + 1e-6
            scaled = np.clip((crop - lo) / (hi - lo), 0.0, 1.0)
            norm = np.where(finite, np.rint(scaled * 255.0), 0).astype(np.uint8)
        out["depth"] = _resize(norm, width, height)

    if want_normal:
        normals_cam = np.asarray(points["normals"], dtype=np.float32)
        normals_proj = _scatter_camera_array_to_projector(
            normals_cam, projector_map, fill=0.0
        )
        crop = normals_proj[y0 : y1 + 1, x0 : x1 + 1]
        # Map [-1,1] → [0,255] RGB (OpenCV BGR write later).
        finite = np.isfinite(crop).all(axis=-1)
        mapped = np.nan_to_num(crop, nan=0.0, posinf=0.0, neginf=0.0)
        rgb = np.clip((mapped + 1.0) * 0.5 * 255.0, 0, 255).astype(np.uint8)
        keep = mask_full[y0 : y1 + 1, x0 : x1 + 1] & finite
        rgb[~keep] = 0
        out["normal"] = _resize(rgb, width, height)

    return out


def write_control_images(
    controls: dict[str, np.ndarray],
    out_dir: str | Path,
) -> dict[str, Path]:
    """Write control images as PNGs; normals stored as BGR for OpenCV."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for key, image in controls.items():
        path = out_dir / f"{key}.png"
        if key == "normal":
            # image is RGB; OpenCV expects BGR.
            bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            ok = cv2.imwrite(str(path), bgr)
        else:
            ok = cv2.imwrite(str(path), image)
        if not ok:
            raise OSError(f"failed to write {path}")
        paths[key] = path
    return paths
