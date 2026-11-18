"""Camera–projector intrinsics / extrinsics estimation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from lumur.calibrate.residuals import ResidualReport, report_residuals
from lumur.decode.graycode import CorrespondenceMap


ScaleSource = Literal["checkerboard", "measured_distance", "none"]


@dataclass
class CameraModel:
    image_size: tuple[int, int]  # (width, height)
    matrix: np.ndarray  # 3x3
    distortion: np.ndarray  # (N,)

    def to_dict(self) -> dict:
        return {
            "image_size": [int(self.image_size[0]), int(self.image_size[1])],
            "matrix": self.matrix.tolist(),
            "distortion": self.distortion.reshape(-1).tolist(),
        }


@dataclass
class StereoExtrinsics:
    R: np.ndarray  # 3x3, camera → projector
    T: np.ndarray  # (3,), camera → projector translation
    scale_source: ScaleSource
    measured_distance_m: float | None = None

    def to_dict(self) -> dict:
        return {
            "R": self.R.tolist(),
            "T": self.T.reshape(-1).tolist(),
            "scale_source": self.scale_source,
            "measured_distance_m": self.measured_distance_m,
        }


@dataclass
class CalibrationResult:
    camera: CameraModel
    projector: CameraModel
    stereo: StereoExtrinsics
    residuals: ResidualReport
    correspondence_valid_fraction: float
    method: str

    def to_dict(self) -> dict:
        return {
            "camera": self.camera.to_dict(),
            "projector": self.projector.to_dict(),
            "stereo": self.stereo.to_dict(),
            "residuals": self.residuals.to_dict(),
            "correspondence_valid_fraction": self.correspondence_valid_fraction,
            "method": self.method,
        }


def _sample_correspondences(
    corr: CorrespondenceMap,
    *,
    max_points: int = 5000,
    min_confidence: float = 0.05,
    rng: np.random.Generator | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (camera_pts Nx2, projector_pts Nx2) in pixel coordinates."""
    ys, xs = np.where(corr.valid & (corr.confidence >= min_confidence))
    if ys.size == 0:
        raise ValueError("no valid correspondences for calibration")
    if ys.size > max_points:
        rng = rng or np.random.default_rng(0)
        pick = rng.choice(ys.size, size=max_points, replace=False)
        ys, xs = ys[pick], xs[pick]
    cam = np.stack([xs.astype(np.float64), ys.astype(np.float64)], axis=1)
    proj = np.stack(
        [corr.proj_u[ys, xs].astype(np.float64), corr.proj_v[ys, xs].astype(np.float64)],
        axis=1,
    )
    return cam, proj


def _default_distortion() -> np.ndarray:
    return np.zeros(5, dtype=np.float64)


def estimate_pinhole(
    image_size: tuple[int, int], *, focal_scale: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """Reasonable pinhole prior when no board is available."""
    w, h = image_size
    f = focal_scale * max(w, h)
    K = np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]], dtype=np.float64)
    return K, _default_distortion()


def calibrate_with_checkerboard(
    corr: CorrespondenceMap,
    camera_image_gray: np.ndarray,
    *,
    board_size: tuple[int, int],
    square_size_m: float,
    projector_size: tuple[int, int],
) -> CalibrationResult:
    """Calibrate camera and projector from one checkerboard view + Gray-code map.

    ``board_size`` is interior corners (cols, rows). Projector coordinates at
    each detected corner are bilinear-sampled from ``corr``.
    """
    import cv2

    if camera_image_gray.ndim != 2:
        raise ValueError("camera_image_gray must be grayscale")

    cols, rows = board_size
    objp = np.zeros((rows * cols, 3), np.float32)
    objp[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2)
    objp *= float(square_size_m)

    found, corners = cv2.findChessboardCorners(
        camera_image_gray, board_size, flags=cv2.CALIB_CB_ADAPTIVE_THRESH
    )
    if not found:
        raise ValueError("checkerboard not found in camera image")

    corners = cv2.cornerSubPix(
        camera_image_gray,
        corners,
        (11, 11),
        (-1, -1),
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
    )
    cam_pts = corners.reshape(-1, 2)

    # Sample projector coords at sub-pixel camera locations.
    proj_pts = []
    kept_obj = []
    kept_cam = []
    h, w = corr.shape
    for i, (u, v) in enumerate(cam_pts):
        x, y = float(u), float(v)
        if x < 0 or y < 0 or x >= w - 1 or y >= h - 1:
            continue
        x0, y0 = int(np.floor(x)), int(np.floor(y))
        x1, y1 = x0 + 1, y0 + 1
        if not (
            corr.valid[y0, x0]
            and corr.valid[y0, x1]
            and corr.valid[y1, x0]
            and corr.valid[y1, x1]
        ):
            continue
        wx, wy = x - x0, y - y0
        pu = (
            corr.proj_u[y0, x0] * (1 - wx) * (1 - wy)
            + corr.proj_u[y0, x1] * wx * (1 - wy)
            + corr.proj_u[y1, x0] * (1 - wx) * wy
            + corr.proj_u[y1, x1] * wx * wy
        )
        pv = (
            corr.proj_v[y0, x0] * (1 - wx) * (1 - wy)
            + corr.proj_v[y0, x1] * wx * (1 - wy)
            + corr.proj_v[y1, x0] * (1 - wx) * wy
            + corr.proj_v[y1, x1] * wx * wy
        )
        proj_pts.append([pu, pv])
        kept_obj.append(objp[i])
        kept_cam.append([u, v])

    if len(proj_pts) < 8:
        raise ValueError(
            f"only {len(proj_pts)} board corners have valid projector coords"
        )

    obj_points = [np.asarray(kept_obj, dtype=np.float32)]
    cam_points = [np.asarray(kept_cam, dtype=np.float32)]
    proj_points = [np.asarray(proj_pts, dtype=np.float32)]

    cam_h, cam_w = camera_image_gray.shape
    proj_w, proj_h = projector_size

    _, K_c, dist_c, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, cam_points, (cam_w, cam_h), None, None
    )
    _, K_p, dist_p, _, _ = cv2.calibrateCamera(
        obj_points, proj_points, (proj_w, proj_h), None, None
    )

    stereo_rms, K_c, dist_c, K_p, dist_p, R, T, _, _ = cv2.stereoCalibrate(
        obj_points,
        cam_points,
        proj_points,
        K_c,
        dist_c,
        K_p,
        dist_p,
        (cam_w, cam_h),
        flags=cv2.CALIB_FIX_INTRINSIC,
        criteria=(cv2.TERM_CRITERIA_MAX_ITER + cv2.TERM_CRITERIA_EPS, 100, 1e-6),
    )

    # Per-corner residual magnitude in camera pixels after stereo.
    projected, _ = cv2.projectPoints(
        obj_points[0], rvecs[0], tvecs[0], K_c, dist_c
    )
    err = np.linalg.norm(projected.reshape(-1, 2) - cam_points[0], axis=1)

    residual_image = np.zeros((cam_h, cam_w), dtype=np.float32)
    valid = np.zeros((cam_h, cam_w), dtype=bool)
    for (u, v), e in zip(cam_points[0], err):
        ui, vi = int(round(u)), int(round(v))
        if 0 <= ui < cam_w and 0 <= vi < cam_h:
            residual_image[vi, ui] = float(e)
            valid[vi, ui] = True

    residuals = report_residuals(residual_image, valid, tile=max(16, min(cam_w, cam_h) // 8))
    # Prefer stereo RMS as the headline mean when denser map residuals are sparse.
    residuals = ResidualReport(
        mean_px=float(stereo_rms),
        rms_px=float(np.sqrt(np.mean(np.square(err)))),
        median_px=float(np.median(err)),
        count=int(err.size),
        worst_region=residuals.worst_region,
    )

    return CalibrationResult(
        camera=CameraModel((cam_w, cam_h), np.asarray(K_c), np.asarray(dist_c)),
        projector=CameraModel((proj_w, proj_h), np.asarray(K_p), np.asarray(dist_p)),
        stereo=StereoExtrinsics(
            R=np.asarray(R), T=np.asarray(T).reshape(3), scale_source="checkerboard"
        ),
        residuals=residuals,
        correspondence_valid_fraction=corr.valid_fraction,
        method="checkerboard",
    )


def _refine_projector_pinhole(
    cam_pts: np.ndarray,
    proj_pts: np.ndarray,
    K_c: np.ndarray,
    dist_c: np.ndarray,
    projector_size: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Search a projector focal length that maximises essential-matrix support.

    Returns ``(K_p, R_e, T_e, pose_mask)`` where ``R_e``/``T_e`` come from
    ``recoverPose`` (unit translation). Used to pick a Euclidean homography
    solution that agrees with the stereo motion.
    """
    import cv2

    proj_w, proj_h = projector_size
    prior_f = float(max(proj_w, proj_h))
    cam_n = cv2.undistortPoints(
        cam_pts.reshape(-1, 1, 2), K_c, dist_c
    ).reshape(-1, 2)
    best: tuple | None = None
    for f in np.linspace(0.7 * prior_f, 1.4 * prior_f, 36):
        K_p = np.array(
            [[f, 0.0, proj_w / 2.0], [0.0, f, proj_h / 2.0], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )
        proj_n = cv2.undistortPoints(
            proj_pts.reshape(-1, 1, 2), K_p, None
        ).reshape(-1, 2)
        E, mask = cv2.findEssentialMat(
            cam_n,
            proj_n,
            focal=1.0,
            pp=(0.0, 0.0),
            method=cv2.RANSAC,
            threshold=0.01,
            prob=0.999,
        )
        if E is None or mask is None:
            continue
        _, R, T, mask_pose = cv2.recoverPose(
            E, cam_n, proj_n, cameraMatrix=np.eye(3), mask=mask.copy()
        )
        pose_inl = int((mask_pose.ravel() > 0).sum()) if mask_pose is not None else 0
        score = (pose_inl, int(mask.sum()), -abs(float(f) - prior_f))
        if best is None or score > best[0]:
            best = (
                score,
                K_p,
                np.asarray(R, dtype=np.float64),
                np.asarray(T, dtype=np.float64).reshape(3),
                mask_pose,
            )
    if best is None:
        K_p, _ = estimate_pinhole(projector_size)
        return K_p, np.eye(3), np.array([0.0, 0.0, 1.0]), np.ones(len(cam_pts), dtype=np.uint8)
    return best[1], best[2], best[3], best[4]


def _undistorted_ray(
    uv: tuple[float, float], K_c: np.ndarray, dist_c: np.ndarray
) -> np.ndarray:
    import cv2

    und = cv2.undistortPoints(
        np.array([[[float(uv[0]), float(uv[1])]]], dtype=np.float64),
        K_c,
        dist_c,
    ).reshape(2)
    ray = np.array([und[0], und[1], 1.0], dtype=np.float64)
    return ray / np.linalg.norm(ray)


def calibrate_plane_with_measured_distance(
    corr: CorrespondenceMap,
    *,
    camera_size: tuple[int, int],
    projector_size: tuple[int, int],
    camera_matrix: np.ndarray | None = None,
    camera_distortion: np.ndarray | None = None,
    point_a_cam: tuple[float, float],
    point_b_cam: tuple[float, float],
    distance_m: float,
    projector_matrix: np.ndarray | None = None,
) -> CalibrationResult:
    """Plane-based calibration: projective pose, metric scale from one distance.

    Assumes the decoded scene is dominated by one plane. Camera intrinsics may
    be supplied; otherwise a pinhole prior is used. Projector intrinsics are
    refined from correspondence support (focal search) unless
    ``projector_matrix`` is given. Translation is scaled so the 3D distance
    between the rays through ``point_a_cam`` and ``point_b_cam`` (intersected
    with the recovered plane ``N·X = 1``) matches ``distance_m``.

    Uses a Euclidean homography ``inv(K_p) H K_c`` (OpenCV convention
    ``H_e ≈ R + T Nᵀ``) and selects the chirality-consistent solution whose
    rotation best matches an essential-matrix pose. The previous
    ``decomposeHomographyMat(inv(H), K_c)`` + max-``N_z`` path systematically
    picked a wrong scale (~2.5×) on the sim presets.
    """
    import cv2

    cam_w, cam_h = camera_size
    proj_w, proj_h = projector_size

    if camera_matrix is None:
        K_c, dist_c = estimate_pinhole(camera_size)
    else:
        K_c = np.asarray(camera_matrix, dtype=np.float64)
        dist_c = (
            np.asarray(camera_distortion, dtype=np.float64)
            if camera_distortion is not None
            else _default_distortion()
        )

    cam_pts, proj_pts = _sample_correspondences(corr)
    H, inliers = cv2.findHomography(cam_pts, proj_pts, cv2.RANSAC, 3.0)
    if H is None:
        raise ValueError("homography estimation failed")

    if projector_matrix is not None:
        K_p = np.asarray(projector_matrix, dtype=np.float64)
        # Still recover an E pose to score homography solutions.
        cam_n = cv2.undistortPoints(
            cam_pts.reshape(-1, 1, 2), K_c, dist_c
        ).reshape(-1, 2)
        proj_n = cv2.undistortPoints(
            proj_pts.reshape(-1, 1, 2), K_p, None
        ).reshape(-1, 2)
        E, mask = cv2.findEssentialMat(
            cam_n, proj_n, focal=1.0, pp=(0.0, 0.0), method=cv2.RANSAC, threshold=0.01
        )
        if E is not None:
            _, R_e, T_e, _ = cv2.recoverPose(
                E, cam_n, proj_n, cameraMatrix=np.eye(3), mask=mask
            )
            R_e = np.asarray(R_e, dtype=np.float64)
            T_e = np.asarray(T_e, dtype=np.float64).reshape(3)
        else:
            R_e, T_e = np.eye(3), np.array([0.0, 0.0, 1.0])
    else:
        K_p, R_e, T_e, _ = _refine_projector_pinhole(
            cam_pts, proj_pts, K_c, dist_c, projector_size
        )
    dist_p = _default_distortion()

    # Euclidean homography in normalised coordinates (OpenCV: H_e = R + T Nᵀ,
    # plane N·X = 1 in the unscaled reconstruction).
    H_e = np.linalg.inv(K_p) @ H @ K_c
    n_solutions, Rs, Ts, Ns = cv2.decomposeHomographyMat(H_e, np.eye(3))

    best = None
    best_key: tuple | None = None
    for i in range(n_solutions):
        R_i = np.asarray(Rs[i], dtype=np.float64)
        T_i = np.asarray(Ts[i], dtype=np.float64).reshape(3)
        N_i = np.asarray(Ns[i], dtype=np.float64).reshape(3)
        try:
            ray_a = _undistorted_ray(point_a_cam, K_c, dist_c)
            ray_b = _undistorted_ray(point_b_cam, K_c, dist_c)
            denom_a = float(N_i @ ray_a)
            denom_b = float(N_i @ ray_b)
            if abs(denom_a) < 1e-9 or abs(denom_b) < 1e-9:
                continue
            Xa = ray_a / denom_a
            Xb = ray_b / denom_b
        except Exception:
            continue
        # Chirality: measured points must lie in front of the camera.
        if Xa[2] <= 0.0 or Xb[2] <= 0.0:
            continue
        current = float(np.linalg.norm(Xa - Xb))
        if current < 1e-12:
            continue
        # Rotation agreement with essential-matrix pose.
        cos_r = float(np.clip((np.trace(R_i @ R_e.T) - 1.0) * 0.5, -1.0, 1.0))
        ang = float(np.degrees(np.arccos(cos_r)))
        T_scaled = T_i * (float(distance_m) / current)
        t_dir = T_scaled / max(np.linalg.norm(T_scaled), 1e-12)
        e_dir = T_e / max(np.linalg.norm(T_e), 1e-12)
        align = abs(float(t_dir @ e_dir))
        key = (-ang, align)
        if best_key is None or key > best_key:
            best_key = key
            best = (R_i, T_scaled, N_i)

    if best is None:
        raise ValueError(
            "no chirality-consistent homography solution for measured-distance points"
        )
    _R_h, T_h, _N = best
    # Hybrid pose: essential-matrix rotation + translation *direction* (stronger
    # on near-planar rooms) with metric *magnitude* from the homography plane
    # scale. Pure H rotation left wall normals tilted on room_with_box.
    scale_m = float(np.linalg.norm(T_h))
    e_dir = T_e / max(np.linalg.norm(T_e), 1e-12)
    T = e_dir * scale_m
    if float(T @ T_h) < 0.0:
        T = -T
    R = R_e

    # Build residual image from homography reprojection on inliers.
    residual_image = np.zeros((cam_h, cam_w), dtype=np.float32)
    valid = np.zeros((cam_h, cam_w), dtype=bool)
    if inliers is not None:
        mask = inliers.ravel().astype(bool)
    else:
        mask = np.ones(cam_pts.shape[0], dtype=bool)
    cam_h_pts = np.hstack([cam_pts, np.ones((cam_pts.shape[0], 1))])
    reproj = (H @ cam_h_pts.T).T
    reproj = reproj[:, :2] / reproj[:, 2:3]
    err = np.linalg.norm(reproj - proj_pts, axis=1)
    for (u, v), e, keep in zip(cam_pts, err, mask):
        if not keep:
            continue
        ui, vi = int(round(u)), int(round(v))
        if 0 <= ui < cam_w and 0 <= vi < cam_h:
            residual_image[vi, ui] = float(e)
            valid[vi, ui] = True

    residuals = report_residuals(
        residual_image, valid, tile=max(16, min(cam_w, cam_h) // 8)
    )

    return CalibrationResult(
        camera=CameraModel((cam_w, cam_h), K_c, dist_c),
        projector=CameraModel((proj_w, proj_h), K_p, dist_p),
        stereo=StereoExtrinsics(
            R=np.asarray(R, dtype=np.float64),
            T=np.asarray(T, dtype=np.float64).reshape(3),
            scale_source="measured_distance",
            measured_distance_m=float(distance_m),
        ),
        residuals=residuals,
        correspondence_valid_fraction=corr.valid_fraction,
        method="plane_measured_distance",
    )


def correspondence_reprojection_residuals(
    corr: CorrespondenceMap,
    H: np.ndarray,
) -> ResidualReport:
    """Residual of a camera→projector homography against the correspondence map."""
    h, w = corr.shape
    residual = np.zeros((h, w), dtype=np.float32)
    ys, xs = np.where(corr.valid)
    if ys.size == 0:
        return report_residuals(residual, corr.valid)
    pts = np.stack([xs, ys, np.ones(xs.shape[0])], axis=1).astype(np.float64)
    reproj = (H @ pts.T).T
    reproj = reproj[:, :2] / reproj[:, 2:3]
    target = np.stack([corr.proj_u[ys, xs], corr.proj_v[ys, xs]], axis=1)
    err = np.linalg.norm(reproj - target, axis=1).astype(np.float32)
    residual[ys, xs] = err
    return report_residuals(residual, corr.valid)