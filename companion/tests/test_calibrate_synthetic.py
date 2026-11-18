"""Synthetic calibration: recover pose / scale within tolerances."""

from __future__ import annotations

import numpy as np
import pytest

from lumur.calibrate.geometry import (
    calibrate_plane_with_measured_distance,
    estimate_pinhole,
)
from lumur.calibrate.residuals import report_residuals
from lumur.decode.graycode import decode_graycode
from lumur.patterns.graycode import generate_graycode_sequence
from lumur.schema.calibration import (
    SCHEMA_VERSION,
    build_calibration_document,
    validate_calibration_document,
)
from tests.synthetic.renderer import (
    default_scene,
    ground_truth_correspondence,
    project_point,
    synthetic_captures,
)


def test_plane_calibration_recovers_scale_and_reports_worst_region():
    camera, projector, plane = default_scene((120, 90), (80, 60))
    gt = ground_truth_correspondence(camera, projector, plane)

    seq = generate_graycode_sequence(projector.width, projector.height)
    captures = synthetic_captures(seq, gt, noise_std=1.5, seed=2)
    decoded = decode_graycode(captures, seq, contrast_threshold=5.0)

    # Two world points on the plane → camera pixels + true metric distance.
    world_a = np.array([-0.25, -0.15, 2.0])
    world_b = np.array([0.30, 0.10, 2.0])
    true_dist = float(np.linalg.norm(world_a - world_b))
    pa = project_point(camera, world_a)
    pb = project_point(camera, world_b)
    assert pa is not None and pb is not None

    result = calibrate_plane_with_measured_distance(
        decoded,
        camera_size=(camera.width, camera.height),
        projector_size=(projector.width, projector.height),
        camera_matrix=camera.K,
        point_a_cam=(pa[0], pa[1]),
        point_b_cam=(pb[0], pb[1]),
        distance_m=true_dist,
    )

    assert result.stereo.scale_source == "measured_distance"
    assert result.stereo.measured_distance_m == pytest.approx(true_dist)
    assert result.residuals.count > 50
    assert result.residuals.mean_px < 3.0
    assert result.residuals.worst_region.mean_px >= result.residuals.mean_px - 1e-6
    bbox = result.residuals.worst_region.to_dict()["bbox"]
    assert len(bbox) == 4
    assert bbox[2] > bbox[0] and bbox[3] > bbox[1]

    # Scaled translation must be non-zero and finite after the tape measure.
    t_est = result.stereo.T.reshape(3)
    assert np.isfinite(t_est).all()
    assert np.linalg.norm(t_est) > 0

    doc = build_calibration_document(
        result, projector_size=(projector.width, projector.height)
    )
    validate_calibration_document(doc)
    assert doc["schema_version"] == SCHEMA_VERSION
    assert "worst_region" in doc["residuals"]


def test_residual_report_finds_worst_tile():
    residual = np.zeros((64, 64), dtype=np.float32)
    valid = np.ones((64, 64), dtype=bool)
    # Align the hot region to the 16×16 tile grid used by the reporter.
    residual[48:64, 48:64] = 10.0
    residual[0:16, 0:16] = 1.0
    report = report_residuals(residual, valid, tile=16)
    assert report.mean_px < 10.0
    assert report.worst_region.mean_px == 10.0
    assert report.worst_region.x0 == 48
    assert report.worst_region.y0 == 48


def test_estimate_pinhole_centred():
    K, dist = estimate_pinhole((200, 100))
    assert K[0, 2] == 100
    assert K[1, 2] == 50
    assert dist.shape == (5,)
