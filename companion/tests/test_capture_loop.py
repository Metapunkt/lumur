"""Capture loop identity validation with a synthetic camera."""

from __future__ import annotations

import numpy as np
import pytest

from lumur.capture.camera import SyntheticCamera
from lumur.capture.display import NullDisplay
from lumur.capture.loop import CaptureError, CaptureLoop
from lumur.patterns.graycode import generate_graycode_sequence


def test_capture_loop_identity_check():
    seq = generate_graycode_sequence(16, 8)
    # Camera returns images identical to the projected patterns (perfect scene).
    frames = [f.image.copy() for f in seq.frames]
    camera = SyntheticCamera(frames)
    loop = CaptureLoop(
        camera,
        NullDisplay(),
        settle_s=0.0,
        discard_warmup_grabs=0,
        identity_min_diff=1.0,
        validate_identity=True,
    )
    captured = loop.capture_sequence(seq)
    assert len(captured) == len(seq.frames)
    assert captured[0].pattern_id == "col0"


def test_capture_loop_rejects_stuck_frame():
    seq = generate_graycode_sequence(16, 8)
    # All grabs return the same image → identity check must fail.
    stuck = np.full((8, 16), 128, dtype=np.uint8)
    camera = SyntheticCamera([stuck for _ in seq.frames])
    loop = CaptureLoop(
        camera,
        NullDisplay(),
        settle_s=0.0,
        discard_warmup_grabs=0,
        identity_min_diff=1.0,
        validate_identity=True,
    )
    with pytest.raises(CaptureError, match="pattern identity"):
        loop.capture_sequence(seq)