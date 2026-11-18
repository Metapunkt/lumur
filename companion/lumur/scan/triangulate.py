"""Dense triangulation from Gray-code correspondence + calibration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.decode.graycode import CorrespondenceMap
from lumur.scan.masks import (
    MASK_BAD_TRIANGULATION,
    MASK_INVALID,
    MASK_LOW_CONFIDENCE,
    MASK_OUTLIER,
    MASK_VALID,
)


@dataclass
class TriangulationResult:
    """Per-camera-pixel 3D reconstruction in the camera coordinate frame."""

    points: np.ndarray  # float32 HxWx3, NaN where invalid
    depth: np.ndarray  # float32 HxW, optical-axis Z; NaN where invalid
    confidence: np.ndarray  # float32 HxW in [0, 1]
    mask: np.ndarray  # uint8 HxW (see lumur.scan.masks)
    reprojection_error_px: np.ndarray  # float32 HxW
    triangulation_angle_deg: np.ndarray  # float32 HxW
    # Dense camera→projector correspondence retained for paint-the-room.
    proj_u: np.ndarray  # float32 HxW
    proj_v: np.ndarray  # float32 HxW


def _projection_matrices(
    K_c: np.ndarray,
    K_p: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Camera and projector 3×4 projection matrices (camera-frame points)."""
    P_c = K_c @ np.hstack([np.eye(3), np.zeros((3, 1))])
    P_p = K_p @ np.hstack([R, T.reshape(3, 1)])
    return P_c.astype(np.float64), P_p.astype(np.float64)


def _undistort_pixels(
    u: np.ndarray,
    v: np.ndarray,
    K: np.ndarray,
    dist: np.ndarray | None,
) -> np.ndarray:
    """Return Nx2 normalised / undistorted pixel coords suitable for P = K[R|t].

    When ``dist`` is zero/None, returns the original pixel coordinates (still
    in pixels — they are used with ``P = K @ [R|t]``, not the normalised
    camera matrix).
    """
    import cv2

    pts = np.stack([u, v], axis=1).astype(np.float64).reshape(-1, 1, 2)
    if dist is None or not np.any(np.asarray(dist) != 0):
        return pts.reshape(-1, 2)
    # Undistort to pixel coordinates with the same K (P = K[R|t] still holds).
    undist = cv2.undistortPoints(
        pts,
        K.astype(np.float64),
        np.asarray(dist, dtype=np.float64).reshape(-1),
        P=K.astype(np.float64),
    )
    return undist.reshape(-1, 2)


def _triangulate_linear(
    P_c: np.ndarray,
    P_p: np.ndarray,
    cam_uv: np.ndarray,
    proj_uv: np.ndarray,
) -> np.ndarray:
    """Linear DLT triangulation. Returns Nx3 points in camera coordinates."""
    import cv2

    # cv2.triangulatePoints expects 2xN
    X_h = cv2.triangulatePoints(
        P_c, P_p, cam_uv.T.astype(np.float64), proj_uv.T.astype(np.float64)
    )
    w = X_h[3]
    alive = np.abs(w) > 1e-12
    X = np.full((cam_uv.shape[0], 3), np.nan, dtype=np.float64)
    X[alive] = (X_h[:3, alive] / w[alive]).T
    return X


def _ray_dirs_from_pixels(
    uv: np.ndarray,
    K: np.ndarray,
    R_world_from_device: np.ndarray | None = None,
) -> np.ndarray:
    """Unit ray directions in the device frame (or rotated if R given)."""
    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]
    xn = (uv[:, 0] - cx) / fx
    yn = (uv[:, 1] - cy) / fy
    dirs = np.stack([xn, yn, np.ones_like(xn)], axis=1)
    dirs = dirs / np.linalg.norm(dirs, axis=1, keepdims=True)
    if R_world_from_device is not None:
        dirs = (R_world_from_device @ dirs.T).T
    return dirs


def _triangulation_angles_deg(
    cam_uv: np.ndarray,
    proj_uv: np.ndarray,
    K_c: np.ndarray,
    K_p: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
) -> np.ndarray:
    """Proxy angle between camera and projector ray directions.

    Used before a 3D point exists; refined at the reconstructed point afterward.
    ``T`` is accepted for call-site symmetry with the stereo pose.
    """
    del T  # baseline enters the refined angle once X is known
    d_c = _ray_dirs_from_pixels(cam_uv, K_c)
    d_p_local = _ray_dirs_from_pixels(proj_uv, K_p)
    d_p = (R.T @ d_p_local.T).T
    cos_a = np.clip(np.sum(d_c * d_p, axis=1), -1.0, 1.0)
    angles = np.degrees(np.arccos(cos_a))
    angles = np.minimum(angles, 180.0 - angles)
    return angles.astype(np.float64)


def _reprojection_errors(
    points: np.ndarray,
    cam_uv: np.ndarray,
    proj_uv: np.ndarray,
    K_c: np.ndarray,
    K_p: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
    dist_c: np.ndarray | None,
) -> np.ndarray:
    """Max of camera and projector reprojection errors (pixels)."""
    import cv2

    err = np.full(points.shape[0], np.inf, dtype=np.float64)
    finite = np.isfinite(points).all(axis=1)
    if not np.any(finite):
        return err

    X = points[finite].astype(np.float64).reshape(-1, 1, 3)
    rvec = np.zeros(3, dtype=np.float64)
    tvec = np.zeros(3, dtype=np.float64)
    dist = (
        np.asarray(dist_c, dtype=np.float64).reshape(-1)
        if dist_c is not None
        else np.zeros(5, dtype=np.float64)
    )
    cam_proj, _ = cv2.projectPoints(X, rvec, tvec, K_c.astype(np.float64), dist)
    cam_proj = cam_proj.reshape(-1, 2)
    e_c = np.linalg.norm(cam_proj - cam_uv[finite], axis=1)

    rvec_p, _ = cv2.Rodrigues(R.astype(np.float64))
    proj_proj, _ = cv2.projectPoints(
        X, rvec_p, T.reshape(3).astype(np.float64), K_p.astype(np.float64), None
    )
    proj_proj = proj_proj.reshape(-1, 2)
    e_p = np.linalg.norm(proj_proj - proj_uv[finite], axis=1)
    err[finite] = np.maximum(e_c, e_p)
    return err


def triangulate_correspondences(
    corr: CorrespondenceMap,
    *,
    camera_matrix: np.ndarray,
    camera_distortion: np.ndarray | None,
    projector_matrix: np.ndarray,
    stereo_R: np.ndarray,
    stereo_T: np.ndarray,
    min_decode_confidence: float = 0.05,
    min_triangulation_angle_deg: float = 1.5,
    max_reprojection_error_px: float = 3.0,
    confidence_angle_ref_deg: float = 8.0,
    projector_coords_are_indices: bool = True,
) -> TriangulationResult:
    """Triangulate a dense point map from a correspondence map + stereo pose.

    Points are in the **camera** coordinate frame. Confidence combines Gray-code
    decode contrast, triangulation angle, and reprojection residual.
    """
    h, w = corr.shape
    points = np.full((h, w, 3), np.nan, dtype=np.float32)
    depth = np.full((h, w), np.nan, dtype=np.float32)
    confidence = np.zeros((h, w), dtype=np.float32)
    mask = np.full((h, w), MASK_INVALID, dtype=np.uint8)
    reproj = np.full((h, w), np.nan, dtype=np.float32)
    angles = np.full((h, w), np.nan, dtype=np.float32)
    proj_u = corr.proj_u.astype(np.float32).copy()
    proj_v = corr.proj_v.astype(np.float32).copy()

    K_c = np.asarray(camera_matrix, dtype=np.float64)
    K_p = np.asarray(projector_matrix, dtype=np.float64)
    R = np.asarray(stereo_R, dtype=np.float64)
    T = np.asarray(stereo_T, dtype=np.float64).reshape(3)
    P_c, P_p = _projection_matrices(K_c, K_p, R, T)

    ys, xs = np.where(corr.valid & (corr.confidence >= min_decode_confidence))
    if ys.size == 0:
        return TriangulationResult(
            points=points,
            depth=depth,
            confidence=confidence,
            mask=mask,
            reprojection_error_px=reproj,
            triangulation_angle_deg=angles,
            proj_u=proj_u,
            proj_v=proj_v,
        )

    # Camera rays are through pixel centres (u+0.5, v+0.5), matching the sim
    # renderer and OpenCV's half-pixel convention.
    cam_raw = np.stack(
        [xs.astype(np.float64) + 0.5, ys.astype(np.float64) + 0.5], axis=1
    )
    # Gray-code decode yields integer projector indices; geometric centres sit
    # at index+0.5. Continuous maps (sim ground truth from project_points) are
    # already geometric — pass projector_coords_are_indices=False for those.
    pu = corr.proj_u[ys, xs].astype(np.float64)
    pv = corr.proj_v[ys, xs].astype(np.float64)
    if projector_coords_are_indices:
        pu = np.rint(pu) + 0.5
        pv = np.rint(pv) + 0.5
    proj_raw = np.stack([pu, pv], axis=1)
    cam_uv = _undistort_pixels(cam_raw[:, 0], cam_raw[:, 1], K_c, camera_distortion)
    # Projector is modelled without distortion in the companion calibration.
    proj_uv = proj_raw

    X = _triangulate_linear(P_c, P_p, cam_uv, proj_uv)
    ang = _triangulation_angles_deg(cam_uv, proj_uv, K_c, K_p, R, T)
    # Refine angle at the reconstructed point when available.
    finite = np.isfinite(X).all(axis=1) & (X[:, 2] > 1e-6)
    C_p = -R.T @ T
    if np.any(finite):
        v_c = X[finite]
        norms_c = np.linalg.norm(v_c, axis=1, keepdims=True)
        v_p = X[finite] - C_p
        norms_p = np.linalg.norm(v_p, axis=1, keepdims=True)
        ok = (norms_c[:, 0] > 1e-12) & (norms_p[:, 0] > 1e-12)
        to_c = np.zeros_like(v_c)
        to_p = np.zeros_like(v_p)
        to_c[ok] = -v_c[ok] / norms_c[ok]
        to_p[ok] = -v_p[ok] / norms_p[ok]
        cos_pt = np.clip(np.sum(to_c * to_p, axis=1), -1.0, 1.0)
        ang_pt = np.degrees(np.arccos(cos_pt))
        ang = ang.copy()
        idx = np.where(finite)[0]
        ang[idx[ok]] = ang_pt[ok]

    err = _reprojection_errors(
        X, cam_uv, proj_uv, K_c, K_p, R, T, camera_distortion
    )
    decode_conf = corr.confidence[ys, xs].astype(np.float64)

    angle_factor = np.clip(ang / float(confidence_angle_ref_deg), 0.0, 1.0)
    residual_factor = np.clip(
        1.0 - err / float(max_reprojection_error_px), 0.0, 1.0
    )
    conf = (decode_conf * angle_factor * residual_factor).astype(np.float32)

    bad_geom = (~np.isfinite(X).all(axis=1)) | (X[:, 2] <= 1e-6)
    small_angle = (~bad_geom) & (ang < min_triangulation_angle_deg)
    outlier = (~bad_geom) & (~small_angle) & (err > max_reprojection_error_px)
    usable = (~bad_geom) & (~small_angle) & (~outlier)
    low_conf = usable & (conf < min_decode_confidence)
    high_conf = usable & ~low_conf

    def _scatter(sel: np.ndarray, code: int, *, store_points: bool) -> None:
        if not np.any(sel):
            return
        yy, xx = ys[sel], xs[sel]
        mask[yy, xx] = code
        if store_points:
            points[yy, xx] = X[sel].astype(np.float32)
            depth[yy, xx] = X[sel, 2].astype(np.float32)
            angles[yy, xx] = ang[sel].astype(np.float32)
            reproj[yy, xx] = err[sel].astype(np.float32)
            confidence[yy, xx] = conf[sel]

    _scatter(bad_geom, MASK_BAD_TRIANGULATION, store_points=False)
    _scatter(small_angle, MASK_BAD_TRIANGULATION, store_points=True)
    _scatter(outlier, MASK_OUTLIER, store_points=True)
    _scatter(low_conf, MASK_LOW_CONFIDENCE, store_points=True)
    _scatter(high_conf, MASK_VALID, store_points=True)

    return TriangulationResult(
        points=points,
        depth=depth,
        confidence=confidence,
        mask=mask,
        reprojection_error_px=reproj,
        triangulation_angle_deg=angles,
        proj_u=proj_u,
        proj_v=proj_v,
    )


def build_projector_correspondence_map(
    proj_u: np.ndarray,
    proj_v: np.ndarray,
    mask: np.ndarray,
    confidence: np.ndarray,
    projector_size: tuple[int, int],
    *,
    valid_masks: tuple[int, ...] = (MASK_VALID, MASK_LOW_CONFIDENCE),
) -> dict[str, np.ndarray]:
    """Scatter camera→projector samples into a dense projector→camera map.

    Returns arrays shaped ``(proj_h, proj_w)``: ``cam_u``, ``cam_v``,
    ``confidence``, ``valid``. When multiple camera pixels map to the same
    projector pixel, the highest-confidence sample wins.
    """
    proj_w, proj_h = projector_size
    cam_u = np.full((proj_h, proj_w), np.nan, dtype=np.float32)
    cam_v = np.full((proj_h, proj_w), np.nan, dtype=np.float32)
    conf_out = np.zeros((proj_h, proj_w), dtype=np.float32)
    valid = np.zeros((proj_h, proj_w), dtype=bool)

    h, w = mask.shape
    keep = np.isin(mask, np.asarray(valid_masks, dtype=np.uint8))
    ys, xs = np.where(keep)
    if ys.size == 0:
        return {
            "cam_u": cam_u,
            "cam_v": cam_v,
            "confidence": conf_out,
            "valid": valid,
        }

    pu = np.rint(proj_u[ys, xs]).astype(np.int32)
    pv = np.rint(proj_v[ys, xs]).astype(np.int32)
    in_bounds = (pu >= 0) & (pu < proj_w) & (pv >= 0) & (pv < proj_h)
    ys, xs, pu, pv = ys[in_bounds], xs[in_bounds], pu[in_bounds], pv[in_bounds]
    conf = confidence[ys, xs]

    # Sort ascending so the last write is the highest confidence.
    order = np.argsort(conf)
    ys, xs, pu, pv, conf = ys[order], xs[order], pu[order], pv[order], conf[order]
    cam_u[pv, pu] = xs.astype(np.float32) + 0.5
    cam_v[pv, pu] = ys.astype(np.float32) + 0.5
    conf_out[pv, pu] = conf
    valid[pv, pu] = True
    return {
        "cam_u": cam_u,
        "cam_v": cam_v,
        "confidence": conf_out,
        "valid": valid,
    }
