"""Room scan: triangulation, planes, package I/O, and sim accuracy checks."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lumur.calibrate.geometry import calibrate_plane_with_measured_distance
from lumur.capture.loop import CaptureLoop
from lumur.decode.graycode import decode_graycode
from lumur.patterns.graycode import generate_graycode_sequence
from lumur.schema.calibration import build_calibration_document, validate_calibration_document
from lumur.schema.room import load_room_package, validate_room_document
from lumur.scan.masks import MASK_VALID
from lumur.scan.pipeline import scan_from_correspondence, write_scan_package
from lumur.scan.planes import fit_plane_ransac, identify_floor_plane
from lumur.sim import SimRig
from lumur.sim.ground_truth import measure_floor_span_pixels


def _calibration_from_gt(rig: SimRig) -> dict:
    """Build a lumur.calibration document using sim ground-truth pose.

    Plane-only calibration translation is weakly constrained; accuracy tests
    that need metric depth use GT stereo (documented limitation).
    """
    gt = rig.ground_truth()
    # Minimal residuals placeholder — not used by the scanner.
    from lumur.calibrate.geometry import (
        CalibrationResult,
        CameraModel,
        StereoExtrinsics,
    )
    from lumur.calibrate.residuals import ResidualReport, WorstRegion

    result = CalibrationResult(
        camera=CameraModel(
            (gt.camera.width, gt.camera.height),
            gt.camera.K.copy(),
            gt.camera.distortion.copy(),
        ),
        projector=CameraModel(
            (gt.projector.width, gt.projector.height),
            gt.projector.K.copy(),
            np.zeros(5, dtype=np.float64),
        ),
        stereo=StereoExtrinsics(
            R=gt.stereo_R.copy(),
            T=gt.stereo_T.copy(),
            scale_source="none",
        ),
        residuals=ResidualReport(
            mean_px=0.0,
            rms_px=0.0,
            median_px=0.0,
            count=0,
            worst_region=WorstRegion(0, 0, 0, 0, 0.0, 0.0, 0),
        ),
        correspondence_valid_fraction=gt.correspondence.valid_fraction,
        method="sim_ground_truth",
    )
    doc = build_calibration_document(result, projector_size=rig.projector_size)
    validate_calibration_document(doc)
    return doc


def _capture_decode(rig: SimRig, *, contrast_threshold: float = 5.0):
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
    return decode_graycode(captures, seq, contrast_threshold=contrast_threshold)


def _plane_angle_deg(n_a: np.ndarray, n_b: np.ndarray) -> float:
    c = float(np.clip(abs(n_a @ n_b), 0.0, 1.0))
    return float(np.degrees(np.arccos(c)))


def _gt_floor_plane_camera(rig: SimRig) -> tuple[np.ndarray, float]:
    """Floor y=0 (world normal +Y) expressed in camera coordinates."""
    cam = rig.scene.camera
    n_w = np.array([0.0, 1.0, 0.0], dtype=np.float64)
    n_c = cam.R @ n_w
    n_c = n_c / np.linalg.norm(n_c)
    # Plane n_w·X_w = 0 → (R n_w)·X_c + d_c = 0 with d_c = -(R n_w)·t? 
    # X_w = R.T (X_c - t) wait: X_c = R X_w + t ⇒ X_w = R.T (X_c - t)
    # n_w · R.T (X_c - t) = 0 ⇒ (R n_w)·X_c - (R n_w)·t = 0
    d_c = float(-(n_c @ cam.t))
    if d_c > 0:
        n_c = -n_c
        d_c = -d_c
    return n_c, d_c


def test_fit_plane_ransac_synthetic():
    rng = np.random.default_rng(0)
    normal = np.array([0.0, 1.0, 0.0])
    pts = rng.normal(size=(500, 3))
    pts[:, 1] = 0.0
    pts += rng.normal(scale=0.005, size=pts.shape)
    # Add outliers.
    pts = np.vstack([pts, rng.normal(size=(40, 3)) * 2.0])
    result = fit_plane_ransac(pts, threshold_m=0.02, min_inliers=100, rng=rng)
    assert result is not None
    n, d, mask, rms = result
    assert abs(n @ normal) > 0.98
    assert rms < 0.01
    assert int(mask.sum()) > 400


def _ray_depth(points: np.ndarray) -> np.ndarray:
    """Ray length from camera origin; matches sim ``ground_truth.depth``."""
    return np.linalg.norm(points, axis=2)


def test_room_scan_depth_accuracy_against_gt(tmp_path: Path):
    """Metric depth with GT pose on room_with_box (non-planar structure).

    Sim presets use a 64×48 projector, so Gray-code quantisation alone yields
    ~5–10% relative ray-depth error; absolute centimetre budgets need higher
    pattern resolution. Pose is taken from sim GT because plane-only
    calibration translation is weakly constrained on near-planar rooms.
    """
    rig = SimRig.from_scene_path("room_with_box")
    gt = rig.ground_truth()
    decoded = _capture_decode(rig, contrast_threshold=5.0)
    calib = _calibration_from_gt(rig)

    result = scan_from_correspondence(decoded, calib, max_reprojection_error_px=4.0)
    both = np.isfinite(result.triangulation.points).all(axis=2) & (gt.depth > 0)
    assert float(both.mean()) > 0.25
    ray = _ray_depth(result.triangulation.points)
    rel = np.abs(ray[both] - gt.depth[both]) / gt.depth[both]
    assert float(np.median(rel)) < 0.10
    assert float(np.percentile(rel, 90)) < 0.20

    out = write_scan_package(
        result, tmp_path / "room", calibration=calib, calibration_ref="gt"
    )
    doc, points, projector_map = load_room_package(out)
    validate_room_document(doc)
    assert points["depth"].shape == gt.depth.shape
    assert "cam_u" in projector_map
    assert doc["floor_plane_id"] is not None


def test_room_scan_recovers_floor_and_walls():
    rig = SimRig.from_scene_path("room_with_box")
    decoded = _capture_decode(rig)
    calib = _calibration_from_gt(rig)
    result = scan_from_correspondence(decoded, calib)
    seg = result.segmentation
    assert seg.floor_plane_id is not None
    floor = next(p for p in seg.planes if p.plane_id == seg.floor_plane_id)
    assert floor.kind == "floor"
    n_gt, d_gt = _gt_floor_plane_camera(rig)
    assert _plane_angle_deg(floor.normal, n_gt) < 12.0
    ys, xs = np.where(seg.surface_id == floor.plane_id)
    pts = result.triangulation.points[ys, xs]
    dist = np.abs(pts @ n_gt + d_gt)
    # Allow quantisation-driven offset at preset resolution.
    assert float(np.median(dist)) < 0.12

    walls = [p for p in seg.planes if p.kind == "wall"]
    assert len(walls) >= 1


def test_room_scan_box_as_non_planar_or_extra_surfaces():
    rig = SimRig.from_scene_path("room_with_box")
    decoded = _capture_decode(rig)
    calib = _calibration_from_gt(rig)
    result = scan_from_correspondence(
        decoded, calib, plane_distance_threshold_m=0.035, max_planes=4
    )
    kinds = {p.kind for p in result.segmentation.planes}
    # Box should appear either as leftover non_planar or as extra surface_* planes.
    non_floor_wall = [
        p
        for p in result.segmentation.planes
        if p.kind in ("non_planar", "surface")
    ]
    assert non_floor_wall, f"expected box residue, got kinds={kinds}"
    assert sum(p.inlier_count for p in non_floor_wall) >= 15


def test_room_scan_noisy_room_degraded_but_sane():
    rig = SimRig.from_scene_path("noisy_room")
    rig.scene.camera.noise_std = 12.0
    rig.scene.camera.ambient = 18.0
    rig.scene.camera.blur_sigma = 0.6
    gt = rig.ground_truth(refresh=True)
    decoded = _capture_decode(rig, contrast_threshold=6.0)
    calib = _calibration_from_gt(rig)
    result = scan_from_correspondence(
        decoded, calib, max_reprojection_error_px=5.0, min_decode_confidence=0.04
    )
    report = result.report
    assert report.covered_fraction > 0.15
    assert report.mean_confidence > 0.0
    # Confidence should be lower than a clean empty_room scan.
    clean = SimRig.from_scene_path("empty_room")
    clean_decoded = _capture_decode(clean, contrast_threshold=5.0)
    clean_calib = _calibration_from_gt(clean)
    clean_result = scan_from_correspondence(clean_decoded, clean_calib)
    assert report.mean_confidence <= clean_result.report.mean_confidence + 0.05
    both = np.isfinite(result.triangulation.points).all(axis=2) & (gt.depth > 0)
    assert float(both.mean()) > 0.15
    ray = _ray_depth(result.triangulation.points)
    rel = np.abs(ray[both] - gt.depth[both]) / gt.depth[both]
    assert float(np.median(rel)) < 0.20
    assert np.isfinite(report.mean_confidence)


def test_room_scan_with_plane_calibration_e2e_room_with_box(tmp_path: Path):
    """End-to-end without GT pose on a non-planar scene (recommended path)."""
    rig = SimRig.from_scene_path("room_with_box")
    gt = rig.ground_truth()
    decoded = _capture_decode(rig)
    world_a = np.array([-0.4, 0.0, 0.55])
    world_b = np.array([0.45, 0.0, 1.15])
    point_a, point_b, distance_m = measure_floor_span_pixels(gt, world_a, world_b)
    calib_result = calibrate_plane_with_measured_distance(
        decoded,
        camera_size=rig.camera_size,
        projector_size=rig.projector_size,
        camera_matrix=rig.scene.camera.K,
        camera_distortion=rig.scene.camera.distortion,
        point_a_cam=point_a,
        point_b_cam=point_b,
        distance_m=distance_m,
    )
    doc = build_calibration_document(calib_result, projector_size=rig.projector_size)
    result = scan_from_correspondence(decoded, doc, max_reprojection_error_px=5.0)
    # Floor should still be recoverable even if metric depth is imperfect.
    assert result.segmentation.floor_plane_id is not None
    assert result.report.covered_fraction > 0.2
    write_scan_package(result, tmp_path / "e2e_room", calibration=doc)
    loaded, _, _ = load_room_package(tmp_path / "e2e_room")
    assert loaded["schema"] == "lumur.room"


def test_identify_floor_prefers_upward_normal():
    from lumur.scan.planes import FittedPlane

    floor = FittedPlane(
        plane_id=1,
        normal=np.array([0.0, -1.0, 0.0]),
        d=1.2,
        inlier_count=400,
        residual_rms_m=0.01,
        kind="surface",
        label="a",
    )
    wall = FittedPlane(
        plane_id=2,
        normal=np.array([0.0, 0.0, -1.0]),
        d=2.0,
        inlier_count=300,
        residual_rms_m=0.01,
        kind="surface",
        label="b",
    )
    assert identify_floor_plane([floor, wall]) == 1


def test_valid_mask_fraction_reported():
    rig = SimRig.from_scene_path("empty_room")
    decoded = _capture_decode(rig)
    calib = _calibration_from_gt(rig)
    result = scan_from_correspondence(decoded, calib)
    assert result.report.valid_fraction > 0.2
    assert result.report.mask_histogram["valid"] == int(
        (result.triangulation.mask == MASK_VALID).sum()
    )
    assert "worst_region" in result.report.to_dict()
