"""Fullscreen pattern display driven by the companion.

Uses OpenCV's native fullscreen window. Calibration does not need Godot:
the companion already owns pattern generation and capture, and OpenCV
fullscreen is the smallest cross-platform path that can fill a projector
output without a second runtime. See ADR 0010.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class PatternDisplay(Protocol):
    def show(self, image: np.ndarray) -> None: ...

    def close(self) -> None: ...


class OpenCVFullscreenDisplay:
    """Show uint8 images fullscreen on a chosen monitor index when possible."""

    def __init__(self, window_name: str = "lumur-pattern", monitor_index: int = 0):
        # Import locally so headless synthetic tests need not open a GUI.
        import cv2

        self._cv2 = cv2
        self.window_name = window_name
        self.monitor_index = monitor_index
        self._opened = False

    def _ensure_window(self, image: np.ndarray) -> None:
        cv2 = self._cv2
        if not self._opened:
            cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
            # Best-effort: move to the requested screen before fullscreen.
            # Exact multi-monitor placement is backend-dependent.
            if self.monitor_index > 0:
                cv2.moveWindow(self.window_name, self.monitor_index * image.shape[1], 0)
            cv2.setWindowProperty(
                self.window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN
            )
            self._opened = True

    def show(self, image: np.ndarray) -> None:
        if image.dtype != np.uint8:
            raise TypeError("pattern image must be uint8")
        if image.ndim == 2:
            bgr = np.stack([image, image, image], axis=-1)
        elif image.ndim == 3 and image.shape[2] in (1, 3):
            bgr = image if image.shape[2] == 3 else np.repeat(image, 3, axis=2)
        else:
            raise ValueError("pattern image must be HxW or HxWx{1,3}")
        self._ensure_window(bgr)
        self._cv2.imshow(self.window_name, bgr)
        self._cv2.waitKey(1)

    def close(self) -> None:
        if self._opened:
            self._cv2.destroyWindow(self.window_name)
            self._opened = False


class NullDisplay:
    """No-op display for synthetic / headless runs."""

    def show(self, image: np.ndarray) -> None:
        return None

    def close(self) -> None:
        return None