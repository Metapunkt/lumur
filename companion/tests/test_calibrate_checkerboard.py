"""Synthetic checkerboard path: OpenCV corner detect + Gray-code coords."""

from __future__ import annotations

import numpy as np

from lumur.calibrate.geometry import calibrate_with_checkerboard
from lumur.decode.graycode import CorrespondenceMap
from lumur.schema.calibration import build_calibration_document, validate_calibration_document


def _synthetic_board_image(
    board_size: tuple[int, int], square_px: int = 40, margin: int = 40
) -> tuple[np.ndarray, np.ndarray]:
    """Return (gray image, object-point-friendly corner pixel coords)."""
    cols, rows = board_size
    w = margin * 2 + square_px * (cols + 1)
    h = margin * 2 + square_px * (rows + 1)
    img = np.full((h, w), 220, dtype=np.uint8)
    for ry in range(rows + 1):
        for cx in range(cols + 1):
            if (cx + ry) % 2 == 0:
                x0 = margin + cx * square_px
                y0 = margin + ry * square_px
                img[y0 : y0 + square_px, x0 : x0 + square_px] = 20
    return img


def _corr_from_affine(
    image_shape: tuple[int, int],
    projector_size: tuple[int, int],
    A: np.ndarray,
) -> CorrespondenceMap:
    """Build a dense correspondence map from a 2x3 affine cam→proj map."""
    h, w = image_shape
    ys, xs = np.mgrid[0:h, 0:w]
    ones = np.ones_like(xs, dtype=np.float64)
    pts = np.stack([xs.ravel(), ys.ravel(), ones.ravel()], axis=0)
    mapped = (A @ pts).T.reshape(h, w, 2)
    proj_u = mapped[:, :, 0].astype(np.float32)
    proj_v = mapped[:, :, 1].astype(np.float32)
    valid = (
        (proj_u >= 0)
        & (proj_u < projector_size[0])
        & (proj_v >= 0)
        & (proj_v < projector_size[1])
    )
    return CorrespondenceMap(
        proj_u=np.where(valid, proj_u, -1).astype(np.float32),
        proj_v=np.where(valid, proj_v, -1).astype(np.float32),
        confidence=valid.astype(np.float32),
        valid=valid,
    )


def test_checkerboard_calibration_roundtrip():
    board_size = (9, 6)
    square_m = 0.025
    img = _synthetic_board_image(board_size)
    proj_size = (800, 600)

    # Mild affine: scale + translation into projector space.
    A = np.array([[1.6, 0.02, 40.0], [0.01, 1.5, 30.0]], dtype=np.float64)
    corr = _corr_from_affine(img.shape, proj_size, A)

    result = calibrate_with_checkerboard(
        corr,
        img,
        board_size=board_size,
        square_size_m=square_m,
        projector_size=proj_size,
    )

    assert result.method == "checkerboard"
    assert result.stereo.scale_source == "checkerboard"
    assert result.residuals.count >= 9 * 6 * 0.5
    assert result.residuals.mean_px < 2.0
    assert result.residuals.worst_region.count > 0

    # Focal lengths should be finite and positive.
    assert result.camera.matrix[0, 0] > 0
    assert result.projector.matrix[0, 0] > 0

    doc = build_calibration_document(result, projector_size=proj_size)
    validate_calibration_document(doc)
    assert doc["stereo"]["scale_source"] == "checkerboard"