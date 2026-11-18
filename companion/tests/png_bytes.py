"""Shared PNG helper for in-process HTTP mocks."""

from __future__ import annotations

import cv2
import numpy as np


def png_bytes(
    width: int, height: int, color_bgr: tuple[int, int, int] = (40, 90, 200)
) -> bytes:
    img = np.zeros((max(height, 1), max(width, 1), 3), dtype=np.uint8)
    img[:, :] = color_bgr
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("png encode failed")
    return buf.tobytes()
