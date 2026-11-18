"""Robust plane fitting and surface segmentation for a room scan."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.scan.masks import MASK_LOW_CONFIDENCE, MASK_VALID


@dataclass(frozen=True)
class FittedPlane:
    """Plane ``normal · X + d = 0`` in camera coordinates (unit normal)."""

    plane_id: int
    normal: np.ndarray  # (3,)
    d: float
    inlier_count: int
    residual_rms_m: float
    kind: str  # "floor" | "wall" | "surface" | "non_planar"
    label: str

    def to_dict(self) -> dict:
        return {
            "plane_id": int(self.plane_id),
            "normal": self.normal.astype(float).tolist(),
            "d": float(self.d),
            "inlier_count": int(self.inlier_count),
            "residual_rms_m": float(self.residual_rms_m),
            "kind": self.kind,
            "label": self.label,
        }

    def signed_distance(self, points: np.ndarray) -> np.ndarray:
        return points @ self.normal + self.d


@dataclass
class PlaneSegmentation:
    planes: list[FittedPlane]
    surface_id: np.ndarray  # int32 HxW; 0 = none / non-planar leftover
    floor_plane_id: int | None
    non_planar_count: int

    def to_dict(self) -> dict:
        return {
            "planes": [p.to_dict() for p in self.planes],
            "floor_plane_id": self.floor_plane_id,
            "non_planar_count": int(self.non_planar_count),
            "surface_count": int(len(self.planes)),
        }


def _fit_plane_svd(points: np.ndarray) -> tuple[np.ndarray, float]:
    centroid = points.mean(axis=0)
    _, _, vh = np.linalg.svd(points - centroid, full_matrices=False)
    normal = vh[-1]
    normal = normal / np.linalg.norm(normal)
    d = float(-normal @ centroid)
    return normal.astype(np.float64), d


def fit_plane_ransac(
    points: np.ndarray,
    *,
    threshold_m: float = 0.03,
    max_iterations: int = 400,
    min_inliers: int = 50,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, float, np.ndarray, float] | None:
    """RANSAC plane fit. Returns ``(normal, d, inlier_mask, rms)`` or None."""
    if points.shape[0] < max(3, min_inliers):
        return None
    rng = rng or np.random.default_rng(0)
    n = points.shape[0]
    best_mask: np.ndarray | None = None
    best_count = 0

    for _ in range(max_iterations):
        idx = rng.choice(n, size=3, replace=False)
        sample = points[idx]
        v1 = sample[1] - sample[0]
        v2 = sample[2] - sample[0]
        normal = np.cross(v1, v2)
        norm = np.linalg.norm(normal)
        if norm < 1e-10:
            continue
        normal = normal / norm
        d = float(-normal @ sample[0])
        dist = np.abs(points @ normal + d)
        mask = dist <= threshold_m
        count = int(mask.sum())
        if count > best_count:
            best_count = count
            best_mask = mask

    if best_mask is None or best_count < min_inliers:
        return None

    normal, d = _fit_plane_svd(points[best_mask])
    dist = np.abs(points @ normal + d)
    # Re-evaluate inliers after refit.
    inliers = dist <= threshold_m
    if int(inliers.sum()) < min_inliers:
        return None
    normal, d = _fit_plane_svd(points[inliers])
    resid = points[inliers] @ normal + d
    rms = float(np.sqrt(np.mean(np.square(resid))))
    return normal, d, inliers, rms


def _orient_normal_toward_camera(normal: np.ndarray, d: float) -> tuple[np.ndarray, float]:
    """Flip so the camera origin sees a negative signed distance (n·0+d < 0)
    only when needed for a consistent outward-ish convention: prefer normals
    that point roughly toward the camera (n·origin_to_plane).

    Camera at origin: signed distance of origin is ``d``. Surfaces in front of
    the camera have points with Z>0. Prefer the normal that points toward the
    camera from the plane (so for a floor below/in front, normal points "up"
    toward free space including the camera when possible).
    """
    # If the origin's signed distance is positive, flip so camera is on the
    # negative side of the plane (common: n·X + d = 0 with camera in free space).
    if d > 0:
        return -normal, -d
    return normal, d


def identify_floor_plane(
    planes: list[FittedPlane],
    *,
    gravity_camera: np.ndarray | None = None,
) -> int | None:
    """Pick the floor among fitted planes.

    Assumes an approximately upright OpenCV camera: image +Y points with
    gravity, so gravity in camera coordinates defaults to ``(0, 1, 0)``.
    The floor is the plane whose normal is most anti-parallel to gravity
    (points "up" into the room) among candidates with enough inliers.
    """
    if not planes:
        return None
    g = (
        np.asarray(gravity_camera, dtype=np.float64)
        if gravity_camera is not None
        else np.array([0.0, 1.0, 0.0], dtype=np.float64)
    )
    g = g / np.linalg.norm(g)
    best_id = None
    best_score = -np.inf
    for p in planes:
        if p.kind == "non_planar":
            continue
        # Up-pointing normal anti-parallel to gravity → score = -n·g
        alignment = float(-p.normal @ g)
        # Prefer larger support when alignment is comparable.
        score = alignment * 10.0 + np.log1p(p.inlier_count)
        if alignment > 0.35 and score > best_score:
            best_score = score
            best_id = p.plane_id
    if best_id is None:
        # Fall back: plane with normal most aligned to ±gravity.
        for p in planes:
            if p.kind == "non_planar":
                continue
            alignment = abs(float(p.normal @ g))
            score = alignment * 10.0 + np.log1p(p.inlier_count)
            if score > best_score:
                best_score = score
                best_id = p.plane_id
    return best_id


def segment_planes(
    points: np.ndarray,
    mask: np.ndarray,
    *,
    max_planes: int = 5,
    distance_threshold_m: float = 0.04,
    min_inlier_fraction: float = 0.04,
    min_inliers: int = 40,
    residual_rms_wall_m: float = 0.05,
    rng: np.random.Generator | None = None,
    gravity_camera: np.ndarray | None = None,
) -> PlaneSegmentation:
    """Sequential RANSAC plane extraction + floor / wall labelling.

    ``surface_id`` is 0 for unassigned pixels; otherwise a stable positive
    ``plane_id``. Leftover valid points after plane extraction are labelled
    as a single ``non_planar`` surface so furniture (e.g. a box) is retained
    without inventing bridging triangles.
    """
    h, w = mask.shape
    surface_id = np.zeros((h, w), dtype=np.int32)
    usable = np.isin(mask, np.asarray([MASK_VALID, MASK_LOW_CONFIDENCE], dtype=np.uint8))
    usable &= np.isfinite(points).all(axis=2)
    ys, xs = np.where(usable)
    if ys.size == 0:
        return PlaneSegmentation(
            planes=[], surface_id=surface_id, floor_plane_id=None, non_planar_count=0
        )

    remaining = np.ones(ys.size, dtype=bool)
    pts_all = points[ys, xs].astype(np.float64)
    rng = rng or np.random.default_rng(0)
    fitted: list[FittedPlane] = []
    next_id = 1
    min_inl = max(min_inliers, int(min_inlier_fraction * ys.size))

    for _ in range(max_planes):
        idx = np.where(remaining)[0]
        if idx.size < min_inl:
            break
        result = fit_plane_ransac(
            pts_all[idx],
            threshold_m=distance_threshold_m,
            min_inliers=min_inl,
            rng=rng,
        )
        if result is None:
            break
        normal, d, local_inliers, rms = result
        if rms > residual_rms_wall_m * 2.5:
            break
        normal, d = _orient_normal_toward_camera(normal, d)
        global_inliers = np.zeros(ys.size, dtype=bool)
        global_inliers[idx[local_inliers]] = True
        # Assign pixels.
        plane = FittedPlane(
            plane_id=next_id,
            normal=normal,
            d=d,
            inlier_count=int(global_inliers.sum()),
            residual_rms_m=rms,
            kind="surface",
            label=f"surface_{next_id}",
        )
        fitted.append(plane)
        surface_id[ys[global_inliers], xs[global_inliers]] = next_id
        remaining[global_inliers] = False
        next_id += 1
        # Tighten minimum as points dwindle.
        min_inl = max(min_inliers, int(min_inlier_fraction * int(remaining.sum())))

    floor_id = identify_floor_plane(fitted, gravity_camera=gravity_camera)
    g = (
        np.asarray(gravity_camera, dtype=np.float64)
        if gravity_camera is not None
        else np.array([0.0, 1.0, 0.0], dtype=np.float64)
    )
    g = g / np.linalg.norm(g)

    relabelled: list[FittedPlane] = []
    for p in fitted:
        if floor_id is not None and p.plane_id == floor_id:
            kind, label = "floor", "floor"
        else:
            horizontal = abs(float(p.normal @ g))
            if horizontal < 0.35:
                kind, label = "wall", f"wall_{p.plane_id}"
            else:
                kind, label = "surface", f"surface_{p.plane_id}"
        relabelled.append(
            FittedPlane(
                plane_id=p.plane_id,
                normal=p.normal,
                d=p.d,
                inlier_count=p.inlier_count,
                residual_rms_m=p.residual_rms_m,
                kind=kind,
                label=label,
            )
        )

    leftover = remaining.copy()
    # A few extra small planar patches (e.g. box faces), then a single
    # non_planar bucket for the rest — do not invent a mesh across gaps.
    extra_budget = 3
    while extra_budget > 0:
        idx = np.where(leftover)[0]
        if idx.size < max(25, min_inliers // 2):
            break
        result = fit_plane_ransac(
            pts_all[idx],
            threshold_m=distance_threshold_m,
            min_inliers=max(25, min_inliers // 2),
            max_iterations=200,
            rng=rng,
        )
        if result is None:
            break
        normal, d, local_inliers, rms = result
        if int(local_inliers.sum()) < max(25, min_inliers // 2):
            break
        normal, d = _orient_normal_toward_camera(normal, d)
        global_inliers = np.zeros(ys.size, dtype=bool)
        global_inliers[idx[local_inliers]] = True
        relabelled.append(
            FittedPlane(
                plane_id=next_id,
                normal=normal,
                d=d,
                inlier_count=int(global_inliers.sum()),
                residual_rms_m=rms,
                kind="surface",
                label=f"surface_{next_id}",
            )
        )
        surface_id[ys[global_inliers], xs[global_inliers]] = next_id
        leftover[global_inliers] = False
        next_id += 1
        extra_budget -= 1

    non_planar_count = int(leftover.sum())
    if non_planar_count > 0:
        relabelled.append(
            FittedPlane(
                plane_id=next_id,
                normal=np.array([0.0, 0.0, 0.0]),
                d=0.0,
                inlier_count=non_planar_count,
                residual_rms_m=float("nan"),
                kind="non_planar",
                label="non_planar",
            )
        )
        surface_id[ys[leftover], xs[leftover]] = next_id

    return PlaneSegmentation(
        planes=relabelled,
        surface_id=surface_id,
        floor_plane_id=floor_id,
        non_planar_count=non_planar_count,
    )


def estimate_normals_from_planes(
    surface_id: np.ndarray,
    planes: list[FittedPlane],
) -> np.ndarray:
    """Per-pixel normals from plane assignments (NaN where unassigned)."""
    normals = np.full(surface_id.shape + (3,), np.nan, dtype=np.float32)
    by_id = {p.plane_id: p for p in planes if p.kind != "non_planar"}
    for pid, plane in by_id.items():
        sel = surface_id == pid
        normals[sel] = plane.normal.astype(np.float32)
    return normals
