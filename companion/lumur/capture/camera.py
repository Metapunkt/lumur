"""Webcam capture with best-effort exposure and white-balance lock."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass
class CameraLockStatus:
    """What the backend actually accepted when locking AE / AWB."""

    exposure_locked: bool = False
    white_balance_locked: bool = False
    notes: list[str] = field(default_factory=list)


class FrameSource(Protocol):
    def grab(self) -> np.ndarray: ...

    def release(self) -> None: ...


class OpenCVCamera:
    """Thin OpenCV VideoCapture wrapper with optional AE/AWB lock."""

    def __init__(self, device: int | str = 0, *, width: int | None = None, height: int | None = None):
        import cv2

        self._cv2 = cv2
        self.cap = cv2.VideoCapture(device)
        if not self.cap.isOpened():
            raise RuntimeError(f"could not open camera {device!r}")
        if width is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        if height is not None:
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.lock_status = CameraLockStatus()

    def lock_exposure_and_wb(self) -> CameraLockStatus:
        """Disable auto-exposure and auto white-balance where the backend allows.

        USB webcam backends differ; failures are recorded rather than raised so
        an installer can still proceed and inspect residuals.
        """
        cv2 = self._cv2
        notes: list[str] = []

        # Common convention: 0.25 / 1 means manual on V4L2; CAP_PROP_AUTO_EXPOSURE
        # semantics vary — try both manual values then pin absolute exposure.
        ae_ok = False
        for value in (0.25, 1.0, 0.0):
            if self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, value):
                ae_ok = True
                break
        if not ae_ok:
            notes.append("CAP_PROP_AUTO_EXPOSURE not accepted by backend")

        # Re-read current exposure and write it back to pin the value.
        exposure = self.cap.get(cv2.CAP_PROP_EXPOSURE)
        exp_ok = self.cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        if not exp_ok:
            notes.append("CAP_PROP_EXPOSURE pin failed")

        awb_ok = self.cap.set(cv2.CAP_PROP_AUTO_WB, 0)
        if not awb_ok:
            notes.append("CAP_PROP_AUTO_WB not accepted by backend")

        self.lock_status = CameraLockStatus(
            exposure_locked=ae_ok and exp_ok,
            white_balance_locked=awb_ok,
            notes=notes,
        )
        return self.lock_status

    def grab(self) -> np.ndarray:
        ok, frame = self.cap.read()
        if not ok or frame is None:
            raise RuntimeError("camera grab failed")
        return frame

    def release(self) -> None:
        self.cap.release()


class SyntheticCamera:
    """In-memory frame source for tests and dry runs."""

    def __init__(self, frames: list[np.ndarray] | None = None):
        self._frames = list(frames or [])
        self._index = 0
        self.lock_status = CameraLockStatus(
            exposure_locked=True, white_balance_locked=True, notes=["synthetic"]
        )

    def push(self, frame: np.ndarray) -> None:
        self._frames.append(frame)

    def lock_exposure_and_wb(self) -> CameraLockStatus:
        return self.lock_status

    def grab(self) -> np.ndarray:
        if self._index >= len(self._frames):
            raise RuntimeError("synthetic camera exhausted")
        frame = self._frames[self._index]
        self._index += 1
        return frame

    def release(self) -> None:
        self._frames.clear()
        self._index = 0


def to_gray(frame: np.ndarray) -> np.ndarray:
    """Convert BGR or gray frame to uint8 grayscale."""
    if frame.ndim == 2:
        return frame
    if frame.ndim == 3 and frame.shape[2] == 1:
        return frame[:, :, 0]
    import cv2

    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)