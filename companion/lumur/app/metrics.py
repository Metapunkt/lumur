"""Surface extent / confidence metrics derived from a room package."""

from __future__ import annotations

from typing import Any

import numpy as np


def compute_surface_metrics(
    points: dict[str, np.ndarray],
    planes: list[dict[str, Any]],
    floor_plane_id: int | None,
) -> dict[int, dict[str, float]]:
    """Compute ``width_m`` and ``mean_confidence`` per plane from dense maps."""
    xyz = np.asarray(points["points"], dtype=np.float64)
    conf = np.asarray(points["confidence"], dtype=np.float64)
    sid = np.asarray(points["surface_id"], dtype=np.int32)

    up = _gravity_up(planes, floor_plane_id)
    out: dict[int, dict[str, float]] = {}
    for plane in planes:
        pid = int(plane["plane_id"])
        if str(plane.get("kind")) == "non_planar":
            continue
        mask = (sid == pid) & np.isfinite(xyz).all(axis=-1)
        if not np.any(mask):
            out[pid] = {"width_m": 0.0, "mean_confidence": 0.0}
            continue
        pts = xyz[mask]
        normal = np.asarray(plane.get("normal") or [0.0, 1.0, 0.0], dtype=np.float64)
        width = major_horizontal_extent_m(pts, normal, up)
        mean_c = float(np.nanmean(conf[mask])) if np.any(mask) else 0.0
        if not np.isfinite(mean_c):
            mean_c = 0.0
        out[pid] = {"width_m": float(width), "mean_confidence": float(mean_c)}
    return out


def major_horizontal_extent_m(
    points_xyz: np.ndarray,
    normal: np.ndarray,
    up: np.ndarray,
) -> float:
    """Extent (metres) along the surface's major horizontal in-plane axis."""
    if points_xyz.size == 0:
        return 0.0
    n = np.asarray(normal, dtype=np.float64)
    n_norm = np.linalg.norm(n)
    if n_norm < 1e-12:
        return 0.0
    n = n / n_norm
    up = np.asarray(up, dtype=np.float64)
    up = up / max(np.linalg.norm(up), 1e-12)

    ref = up if abs(float(n @ up)) < 0.95 else np.array([1.0, 0.0, 0.0])
    a = np.cross(n, ref)
    a_norm = np.linalg.norm(a)
    if a_norm < 1e-12:
        ref = np.array([0.0, 0.0, 1.0])
        a = np.cross(n, ref)
        a_norm = np.linalg.norm(a)
        if a_norm < 1e-12:
            return 0.0
    a = a / a_norm
    b = np.cross(n, a)
    b = b / max(np.linalg.norm(b), 1e-12)

    centered = points_xyz - points_xyz.mean(axis=0)
    ea = float(np.ptp(centered @ a))
    eb = float(np.ptp(centered @ b))
    if not np.isfinite(ea):
        ea = 0.0
    if not np.isfinite(eb):
        eb = 0.0

    ha = 1.0 - abs(float(a @ up))
    hb = 1.0 - abs(float(b @ up))
    if ha >= 0.5 and hb >= 0.5:
        return max(ea, eb)
    return ea if ha >= hb else eb


def _gravity_up(
    planes: list[dict[str, Any]], floor_plane_id: int | None
) -> np.ndarray:
    if floor_plane_id is not None:
        for plane in planes:
            if int(plane["plane_id"]) == int(floor_plane_id):
                n = np.asarray(plane.get("normal") or [0.0, 1.0, 0.0], dtype=np.float64)
                n_norm = np.linalg.norm(n)
                if n_norm > 1e-12:
                    return n / n_norm
    return np.array([0.0, 1.0, 0.0], dtype=np.float64)
