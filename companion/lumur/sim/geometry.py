"""Geometric primitives and camera math for the simulated room."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Plane:
    """Infinite plane ``normal · X + d = 0`` (``normal`` unit length)."""

    normal: np.ndarray
    d: float
    albedo: float = 0.75
    name: str = "plane"

    @staticmethod
    def from_point_normal(
        point: np.ndarray,
        normal: np.ndarray,
        *,
        albedo: float = 0.75,
        name: str = "plane",
    ) -> Plane:
        n = np.asarray(normal, dtype=np.float64)
        n = n / np.linalg.norm(n)
        p = np.asarray(point, dtype=np.float64)
        return Plane(normal=n, d=float(-n @ p), albedo=float(albedo), name=name)


@dataclass(frozen=True)
class Box:
    """Axis-aligned box used as furniture / occluder geometry."""

    center: np.ndarray
    size: np.ndarray  # full extents (dx, dy, dz)
    albedo: float = 0.55
    name: str = "box"

    @property
    def min_corner(self) -> np.ndarray:
        return self.center - 0.5 * self.size

    @property
    def max_corner(self) -> np.ndarray:
        return self.center + 0.5 * self.size


@dataclass(frozen=True)
class OccupantPlaceholder:
    """Static stand-in for a person (cylinder-ish AABB).

    Pose estimation is intentionally not implemented here; later PRD-001
    work can replace these with animated figures / occluders without
    changing the renderer entry points.
    """

    center: np.ndarray  # base centre at floor height typically
    height: float = 1.7
    radius: float = 0.25
    albedo: float = 0.35
    name: str = "occupant"

    def as_box(self) -> Box:
        return Box(
            center=np.asarray(self.center, dtype=np.float64)
            + np.array([0.0, self.height * 0.5, 0.0]),
            size=np.array([self.radius * 2.0, self.height, self.radius * 2.0]),
            albedo=self.albedo,
            name=self.name,
        )


def make_look_at(
    eye: np.ndarray,
    target: np.ndarray,
    up: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (R, t) for world→device with optical axis toward ``target``.

    OpenCV convention: device looks along +Z after the transform.
    Default ``up`` is ``(0, -1, 0)`` so image +Y points down when world +Y
    is up (typical room coordinates).
    """
    if up is None:
        up = np.array([0.0, -1.0, 0.0], dtype=np.float64)
    eye = np.asarray(eye, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    up = np.asarray(up, dtype=np.float64)
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    z = forward
    x = np.cross(z, up)
    if np.linalg.norm(x) < 1e-8:
        x = np.cross(z, np.array([1.0, 0.0, 0.0]))
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z], axis=0)
    t = -R @ eye
    return R, t


def pinhole_K(width: int, height: int, fov_y_deg: float = 50.0) -> np.ndarray:
    f = 0.5 * height / np.tan(np.deg2rad(fov_y_deg) / 2.0)
    return np.array(
        [[f, 0.0, width / 2.0], [0.0, f, height / 2.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )


def device_center(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    return -R.T @ t


def intersect_rays_plane(
    origins: np.ndarray,
    directions: np.ndarray,
    plane: Plane,
) -> tuple[np.ndarray, np.ndarray]:
    """Intersect rays with a plane.

    Returns ``(points, t)`` where invalid hits have ``t = inf`` and
    ``points`` are NaN.
    """
    n = plane.normal
    denom = directions @ n
    t = np.full(origins.shape[0], np.inf, dtype=np.float64)
    valid = np.abs(denom) > 1e-10
    t_cand = -(origins @ n + plane.d) / np.where(valid, denom, 1.0)
    keep = valid & (t_cand > 1e-8)
    t = np.where(keep, t_cand, np.inf)
    points = origins + directions * t[:, None]
    points = np.where(np.isfinite(t)[:, None], points, np.nan)
    return points, t


def intersect_rays_box(
    origins: np.ndarray,
    directions: np.ndarray,
    box: Box,
) -> tuple[np.ndarray, np.ndarray]:
    """Slab-method AABB intersection. Returns ``(points, t)``."""
    inv = np.where(np.abs(directions) > 1e-12, 1.0 / directions, 1e12)
    t0 = (box.min_corner - origins) * inv
    t1 = (box.max_corner - origins) * inv
    tmin = np.minimum(t0, t1)
    tmax = np.maximum(t0, t1)
    t_enter = np.max(tmin, axis=1)
    t_exit = np.min(tmax, axis=1)
    hit = (t_exit >= t_enter) & (t_enter > 1e-8)
    t = np.where(hit, t_enter, np.inf)
    points = origins + directions * t[:, None]
    points = np.where(np.isfinite(t)[:, None], points, np.nan)
    return points, t


def project_points(
    points: np.ndarray,
    K: np.ndarray,
    R: np.ndarray,
    t: np.ndarray,
    *,
    distortion: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project world points into a device. Returns ``(u, v, depth)``.

    Invalid / behind-camera points get NaN ``u,v`` and non-positive depth.
    """
    Xd = (R @ points.T).T + t
    depth = Xd[:, 2]
    alive = depth > 1e-8
    x = np.full(points.shape[0], np.nan, dtype=np.float64)
    y = np.full(points.shape[0], np.nan, dtype=np.float64)
    xn = np.zeros(points.shape[0], dtype=np.float64)
    yn = np.zeros(points.shape[0], dtype=np.float64)
    xn[alive] = Xd[alive, 0] / depth[alive]
    yn[alive] = Xd[alive, 1] / depth[alive]

    if distortion is not None and np.any(np.asarray(distortion) != 0):
        dist = np.asarray(distortion, dtype=np.float64).reshape(-1)
        k1 = dist[0] if dist.size > 0 else 0.0
        k2 = dist[1] if dist.size > 1 else 0.0
        p1 = dist[2] if dist.size > 2 else 0.0
        p2 = dist[3] if dist.size > 3 else 0.0
        k3 = dist[4] if dist.size > 4 else 0.0
        r2 = xn * xn + yn * yn
        radial = 1.0 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
        x_dist = xn * radial + 2.0 * p1 * xn * yn + p2 * (r2 + 2.0 * xn * xn)
        y_dist = yn * radial + p1 * (r2 + 2.0 * yn * yn) + 2.0 * p2 * xn * yn
        xn, yn = x_dist, y_dist

    x[alive] = K[0, 0] * xn[alive] + K[0, 2]
    y[alive] = K[1, 1] * yn[alive] + K[1, 2]
    depth_out = np.where(alive, depth, -1.0)
    return x, y, depth_out


def pixel_rays(
    width: int,
    height: int,
    K: np.ndarray,
    R: np.ndarray,
    *,
    distortion: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Camera-centre origin (in device frame is 0) and world-space ray dirs.

    Returns ``(origin_world_unused_shape, directions HxWx3)`` — callers use
    ``device_center`` for the shared origin. Directions are unit length.
    """
    us = np.arange(width, dtype=np.float64) + 0.5
    vs = np.arange(height, dtype=np.float64) + 0.5
    uu, vv = np.meshgrid(us, vs)
    if distortion is not None and np.any(np.asarray(distortion) != 0):
        import cv2

        pts = np.stack([uu.ravel(), vv.ravel()], axis=1).astype(np.float64)
        undist = cv2.undistortPoints(
            pts.reshape(-1, 1, 2),
            K,
            np.asarray(distortion, dtype=np.float64).reshape(-1),
        ).reshape(-1, 2)
        xn = undist[:, 0]
        yn = undist[:, 1]
    else:
        fx, fy = K[0, 0], K[1, 1]
        cx, cy = K[0, 2], K[1, 2]
        xn = ((uu - cx) / fx).ravel()
        yn = ((vv - cy) / fy).ravel()
    dirs_cam = np.stack([xn, yn, np.ones_like(xn)], axis=1)
    dirs_cam = dirs_cam / np.linalg.norm(dirs_cam, axis=1, keepdims=True)
    dirs_world = (R.T @ dirs_cam.T).T
    return dirs_world.reshape(height, width, 3)
