"""Synthetic decode: known geometry → Gray-code captures → correspondence."""

from __future__ import annotations

import numpy as np

from lumur.decode.graycode import decode_graycode
from lumur.patterns.graycode import generate_graycode_sequence
from tests.synthetic.renderer import (
    default_scene,
    ground_truth_correspondence,
    synthetic_captures,
)


def test_decode_recovers_projector_coords():
    camera, projector, plane = default_scene((96, 72), (64, 48))
    gt = ground_truth_correspondence(camera, projector, plane)
    assert gt.valid_fraction > 0.5

    seq = generate_graycode_sequence(projector.width, projector.height)
    captures = synthetic_captures(seq, gt, noise_std=2.0, seed=1)
    decoded = decode_graycode(captures, seq, contrast_threshold=5.0)

    # Compare on pixels valid in both maps; allow 1-pixel quantisation.
    both = gt.valid & decoded.valid
    assert both.mean() > 0.45
    du = np.abs(decoded.proj_u[both] - np.rint(gt.proj_u[both]))
    dv = np.abs(decoded.proj_v[both] - np.rint(gt.proj_v[both]))
    assert float(np.median(du)) <= 0.5
    assert float(np.median(dv)) <= 0.5
    assert float((du <= 1).mean()) > 0.95
    assert float((dv <= 1).mean()) > 0.95


def test_low_contrast_marked_unknown():
    camera, projector, plane = default_scene((64, 48), (32, 24))
    gt = ground_truth_correspondence(camera, projector, plane)
    seq = generate_graycode_sequence(projector.width, projector.height)
    captures = synthetic_captures(seq, gt, noise_std=0.0, seed=0)

    # Crush contrast on a region by copying primary onto inverse for one bit.
    for cap in captures:
        if cap.pattern.axis == "col" and cap.pattern.bit == 0 and cap.pattern.inverted:
            cap.image[:] = next(
                c.image
                for c in captures
                if c.pattern.axis == "col"
                and c.pattern.bit == 0
                and not c.pattern.inverted
            )
            break

    decoded = decode_graycode(captures, seq, contrast_threshold=10.0)
    # Most of the illuminated region should now be invalid for that axis.
    assert decoded.valid_fraction < gt.valid_fraction * 0.5