"""Capture loop: show pattern, settle, grab, validate identity."""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from lumur.capture.camera import FrameSource, to_gray
from lumur.capture.display import PatternDisplay
from lumur.patterns.graycode import GrayCodeSequence, PatternFrame


@dataclass
class CapturedFrame:
    pattern: PatternFrame
    image: np.ndarray  # grayscale uint8
    pattern_id: str


@dataclass
class CaptureValidation:
    ok: bool
    mean_abs_diff_from_previous: float | None = None
    message: str = ""


class CaptureError(RuntimeError):
    pass


def _mean_abs_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))


class CaptureLoop:
    """Drive a display + camera through a Gray-code sequence."""

    def __init__(
        self,
        camera: FrameSource,
        display: PatternDisplay,
        *,
        settle_s: float = 0.2,
        identity_min_diff: float = 3.0,
        validate_identity: bool = True,
        discard_warmup_grabs: int = 1,
    ):
        self.camera = camera
        self.display = display
        self.settle_s = settle_s
        self.identity_min_diff = identity_min_diff
        self.validate_identity = validate_identity
        self.discard_warmup_grabs = discard_warmup_grabs

    def _grab_settled(self) -> np.ndarray:
        for _ in range(self.discard_warmup_grabs):
            self.camera.grab()
        return to_gray(self.camera.grab())

    def capture_sequence(
        self,
        sequence: GrayCodeSequence,
        *,
        frames: tuple[PatternFrame, ...] | None = None,
    ) -> list[CapturedFrame]:
        selected = frames if frames is not None else sequence.frames
        captured: list[CapturedFrame] = []
        prev_gray: np.ndarray | None = None
        prev_pattern: PatternFrame | None = None

        for pattern in selected:
            self.display.show(pattern.image)
            if self.settle_s > 0:
                time.sleep(self.settle_s)
            image = self._grab_settled()
            pattern_id = f"{pattern.axis}{pattern.bit}{'i' if pattern.inverted else ''}"

            if self.validate_identity and prev_gray is not None and prev_pattern is not None:
                validation = self._validate(prev_pattern, pattern, prev_gray, image)
                if not validation.ok:
                    raise CaptureError(validation.message)

            captured.append(
                CapturedFrame(pattern=pattern, image=image, pattern_id=pattern_id)
            )
            prev_gray = image
            prev_pattern = pattern

        return captured

    def _validate(
        self,
        prev_pattern: PatternFrame,
        pattern: PatternFrame,
        prev_image: np.ndarray,
        image: np.ndarray,
    ) -> CaptureValidation:
        # Patterns that are bitwise complements of each other should differ
        # strongly in the observed frame; identical logical content should not.
        patterns_differ = not np.array_equal(prev_pattern.image, pattern.image)
        mad = _mean_abs_diff(prev_image, image)
        if patterns_differ and mad < self.identity_min_diff:
            return CaptureValidation(
                ok=False,
                mean_abs_diff_from_previous=mad,
                message=(
                    f"pattern identity check failed: expected scene change after "
                    f"{prev_pattern.axis}{prev_pattern.bit}→"
                    f"{pattern.axis}{pattern.bit}{'i' if pattern.inverted else ''}, "
                    f"mean abs diff={mad:.2f} < {self.identity_min_diff}"
                ),
            )
        return CaptureValidation(ok=True, mean_abs_diff_from_previous=mad)