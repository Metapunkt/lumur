"""End-to-end: Gray-code capture → decode → calibrate on the simulated rig."""

from __future__ import annotations

import numpy as np
import pytest

from lumur.calibrate.geometry import calibrate_plane_with_measured_distance
from lumur.capture.backends import open_devices
from lumur.capture.loop import CaptureLoop
from lumur.decode.graycode import decode_graycode
from lumur.patterns.graycode import generate_graycode_sequence
from lumur.schema.calibration import build_calibration_document, validate_calibration_document
from lumur.sim import SimRig, list_presets
from lumur.sim.ground_truth import measure_floor_span_pixels


def _rotation_angle_deg(Ra: np.ndarray, Rb: np.ndarray) -> float:
    R = Ra @ Rb.T
    cos_theta = float(np.clip((np.trace(R) - 1.0) * 0.5, -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_theta)))


def _recover_relative_pose(corr, camera, projector):
    """Essential-matrix pose from decoded correspondences + known intrinsics."""
    import cv2

    ys, xs = np.where(corr.valid)
    assert ys.size > 50
    rng = np.random.default_rng(0)
    pick = rng.choice(ys.size, size=min(2500, ys.size), replace=False)
    ys, xs = ys[pick], xs[pick]
    cam_pts = np.stack([xs, ys], axis=1).astype(np.float64)
    proj_pts = np.stack(
        [corr.proj_u[ys, xs], corr.proj_v[ys, xs]], axis=1
    ).astype(np.float64)
    cam_n = cv2.undistortPoints(
        cam_pts.reshape(-1, 1, 2), camera.K, camera.distortion
    ).reshape(-1, 2)
    proj_n = cv2.undistortPoints(
        proj_pts.reshape(-1, 1, 2), projector.K, None
    ).reshape(-1, 2)
    E, mask = cv2.findEssentialMat(
        cam_n, proj_n, focal=1.0, pp=(0.0, 0.0), method=cv2.RANSAC, threshold=0.02
    )
    assert E is not None
    _, R, T, _ = cv2.recoverPose(
        E, cam_n, proj_n, cameraMatrix=np.eye(3), mask=mask
    )
    return R, T.reshape(3)


def _run_capture_decode(rig: SimRig, *, contrast_threshold: float = 5.0):
    seq = generate_graycode_sequence(*rig.projector_size)
    loop = CaptureLoop(
        rig.camera,
        rig.display,
        settle_s=0.0,
        discard_warmup_grabs=0,
        validate_identity=True,
        identity_min_diff=0.5,
    )
    captures = loop.capture_sequence(seq)
    decoded = decode_graycode(
        captures, seq, contrast_threshold=contrast_threshold
    )
    return captures, decoded


def test_presets_available():
    names = list_presets()
    assert "empty_room" in names
    assert "room_with_box" in names
    assert "noisy_room" in names


def test_sim_backend_opens_via_factory():
    devices = open_devices("sim", scene="empty_room")
    try:
        assert devices.backend == "sim"
        assert devices.projector_size == (64, 48)
        assert devices.camera_size == (80, 60)
        devices.display.show(np.full((48, 64), 255, dtype=np.uint8))
        frame = devices.camera.grab()
        assert frame.shape == (60, 80, 3)
        assert frame.dtype == np.uint8
        lock = devices.lock_exposure_and_wb()
        assert lock.exposure_locked
    finally:
        devices.close()


def test_sim_e2e_decode_and_calibrate_against_ground_truth():
    rig = SimRig.from_scene_path("empty_room")
    gt = rig.ground_truth()
    assert gt.correspondence.valid_fraction > 0.35

    _, decoded = _run_capture_decode(rig, contrast_threshold=5.0)

    # Decode accuracy vs ground-truth projector coordinates.
    both = gt.correspondence.valid & decoded.valid
    assert float(both.mean()) > 0.35
    du = np.abs(decoded.proj_u[both] - np.rint(gt.correspondence.proj_u[both]))
    dv = np.abs(decoded.proj_v[both] - np.rint(gt.correspondence.proj_v[both]))
    decode_acc = float(((du <= 1) & (dv <= 1)).mean())
    assert decode_acc > 0.98

    # Measured-distance endpoints on the floor plane (y=0).
    world_a = np.array([-0.4, 0.0, 0.6])
    world_b = np.array([0.5, 0.0, 1.2])
    point_a, point_b, distance_m = measure_floor_span_pixels(gt, world_a, world_b)

    result = calibrate_plane_with_measured_distance(
        decoded,
        camera_size=rig.camera_size,
        projector_size=rig.projector_size,
        camera_matrix=rig.scene.camera.K,
        camera_distortion=rig.scene.camera.distortion,
        point_a_cam=point_a,
        point_b_cam=point_b,
        distance_m=distance_m,
    )

    # Reprojection / residual quality.
    assert result.residuals.mean_px < 2.0
    assert result.residuals.count > 50

    # Intrinsics: calibration keeps the supplied GT camera matrix.
    gt_K = rig.scene.camera.K
    assert result.camera.matrix[0, 0] == pytest.approx(gt_K[0, 0], rel=1e-9)
    assert result.camera.matrix[1, 1] == pytest.approx(gt_K[1, 1], rel=1e-9)
    assert result.camera.matrix[0, 2] == pytest.approx(gt_K[0, 2], rel=1e-9)
    assert result.camera.matrix[1, 2] == pytest.approx(gt_K[1, 2], rel=1e-9)

    # Pose: essential-matrix recovery against true stereo extrinsics.
    # Translation direction is only weakly constrained on a mostly planar
    # room; require a clear acute match (or its chirality flip).
    R_est, T_est = _recover_relative_pose(
        decoded, rig.scene.camera, rig.scene.projector
    )
    assert _rotation_angle_deg(R_est, gt.stereo_R) < 8.0
    t_est = T_est / np.linalg.norm(T_est)
    t_gt = gt.stereo_T / np.linalg.norm(gt.stereo_T)
    assert max(float(t_est @ t_gt), float((-t_est) @ t_gt)) > 0.65

    # Ground-truth stereo must match the device centres' baseline length.
    baseline = float(np.linalg.norm(rig.scene.camera.center - rig.scene.projector.center))
    assert float(np.linalg.norm(gt.stereo_T)) == pytest.approx(baseline, rel=1e-6)

    # Scaled translation from plane calibration is finite and non-trivial.
    assert np.isfinite(result.stereo.T).all()
    assert np.linalg.norm(result.stereo.T) > 0.05

    doc = build_calibration_document(result, projector_size=rig.projector_size)
    validate_calibration_document(doc)


def test_sim_room_with_box_still_decodes():
    rig = SimRig.from_scene_path("room_with_box")
    gt = rig.ground_truth()
    assert len(rig.scene.room.boxes) == 1
    assert len(rig.scene.room.occupants) == 1
    _, decoded = _run_capture_decode(rig, contrast_threshold=5.0)
    both = gt.correspondence.valid & decoded.valid
    assert float(both.mean()) > 0.25
    du = np.abs(decoded.proj_u[both] - np.rint(gt.correspondence.proj_u[both]))
    dv = np.abs(decoded.proj_v[both] - np.rint(gt.correspondence.proj_v[both]))
    assert float(((du <= 1) & (dv <= 1)).mean()) > 0.95


def test_sim_noise_ambient_stress():
    """Harsh sensor noise + ambient + blur still yields usable decode/calibration."""
    rig = SimRig.from_scene_path("noisy_room")
    # Push the stress case further than the preset defaults.
    rig.scene.camera.noise_std = 14.0
    rig.scene.camera.ambient = 22.0
    rig.scene.camera.blur_sigma = 0.8
    gt = rig.ground_truth(refresh=True)

    _, decoded = _run_capture_decode(rig, contrast_threshold=6.0)
    both = gt.correspondence.valid & decoded.valid
    assert float(both.mean()) > 0.25
    du = np.abs(decoded.proj_u[both] - np.rint(gt.correspondence.proj_u[both]))
    dv = np.abs(decoded.proj_v[both] - np.rint(gt.correspondence.proj_v[both]))
    decode_acc = float(((du <= 1) & (dv <= 1)).mean())
    assert decode_acc > 0.90

    world_a = np.array([-0.35, 0.0, 0.55])
    world_b = np.array([0.45, 0.0, 1.15])
    point_a, point_b, distance_m = measure_floor_span_pixels(gt, world_a, world_b)
    result = calibrate_plane_with_measured_distance(
        decoded,
        camera_size=rig.camera_size,
        projector_size=rig.projector_size,
        camera_matrix=rig.scene.camera.K,
        camera_distortion=rig.scene.camera.distortion,
        point_a_cam=point_a,
        point_b_cam=point_b,
        distance_m=distance_m,
    )
    assert result.residuals.mean_px < 4.0
    assert result.correspondence_valid_fraction > 0.25
