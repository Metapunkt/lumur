"""Decode Gray-code captures into a camera→projector correspondence map."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.capture.loop import CapturedFrame
from lumur.patterns.graycode import GrayCodeSequence, gray_to_binary


@dataclass
class CorrespondenceMap:
    """Dense camera-pixel → projector-pixel map with confidence.

    Arrays are shaped like the camera image (H_cam, W_cam).
    ``proj_u`` / ``proj_v`` are projector column / row indices.
    Pixels with ``valid == False`` are unknown (low contrast or out of range).
    """

    proj_u: np.ndarray  # float32
    proj_v: np.ndarray  # float32
    confidence: np.ndarray  # float32 in [0, 1]
    valid: np.ndarray  # bool

    @property
    def shape(self) -> tuple[int, int]:
        return self.valid.shape  # type: ignore[return-value]

    @property
    def valid_fraction(self) -> float:
        return float(self.valid.mean()) if self.valid.size else 0.0


def _decode_axis(
    frames_by_bit: dict[int, tuple[np.ndarray, np.ndarray | None]],
    n_bits: int,
    resolution: int,
    *,
    contrast_threshold: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (coord, confidence, valid) for one axis."""
    sample = next(iter(frames_by_bit.values()))[0]
    h, w = sample.shape
    gray_code = np.zeros((h, w), dtype=np.uint32)
    min_contrast = np.full((h, w), np.inf, dtype=np.float32)

    for bit in range(n_bits):
        if bit not in frames_by_bit:
            raise ValueError(f"missing capture for bit {bit}")
        primary, inverse = frames_by_bit[bit]
        primary_f = primary.astype(np.float32)
        if inverse is not None:
            inverse_f = inverse.astype(np.float32)
            contrast = np.abs(primary_f - inverse_f)
            on = primary_f > inverse_f
        else:
            # Fallback without inverse: threshold against mid-gray.
            contrast = np.abs(primary_f - 127.5) * 2.0
            on = primary_f >= 127.5
        min_contrast = np.minimum(min_contrast, contrast)
        shift = n_bits - 1 - bit
        gray_code |= on.astype(np.uint32) << shift

    binary = gray_to_binary(gray_code).astype(np.int32)
    confidence = np.clip(min_contrast / 255.0, 0.0, 1.0).astype(np.float32)
    valid = (min_contrast >= contrast_threshold) & (binary >= 0) & (binary < resolution)
    coord = binary.astype(np.float32)
    coord = np.where(valid, coord, -1.0).astype(np.float32)
    return coord, confidence, valid


def decode_graycode(
    captures: list[CapturedFrame],
    sequence: GrayCodeSequence,
    *,
    contrast_threshold: float = 15.0,
) -> CorrespondenceMap:
    """Decode a captured Gray-code sequence into a correspondence map.

    ``contrast_threshold`` is the minimum |pattern − inverse| intensity
    difference (0–255) required for a pixel to be marked valid.
    """
    if not captures:
        raise ValueError("no captures to decode")

    shape = captures[0].image.shape
    col_bits: dict[int, tuple[np.ndarray, np.ndarray | None]] = {}
    row_bits: dict[int, tuple[np.ndarray, np.ndarray | None]] = {}

    # Index captures by (axis, bit); pair primary with inverse when present.
    indexed: dict[tuple[str, int], dict[str, np.ndarray]] = {}
    for cap in captures:
        if cap.image.shape != shape:
            raise ValueError("all captures must share the same resolution")
        key = (cap.pattern.axis, cap.pattern.bit)
        slot = indexed.setdefault(key, {})
        slot["inv" if cap.pattern.inverted else "prim"] = cap.image

    for (axis, bit), slot in indexed.items():
        if "prim" not in slot:
            raise ValueError(f"missing primary pattern for {axis} bit {bit}")
        pair = (slot["prim"], slot.get("inv"))
        if axis == "col":
            col_bits[bit] = pair
        elif axis == "row":
            row_bits[bit] = pair
        else:
            raise ValueError(f"unknown axis {axis!r}")

    h, w = shape
    if sequence.col_bits:
        proj_u, conf_u, valid_u = _decode_axis(
            col_bits,
            sequence.col_bits,
            sequence.width,
            contrast_threshold=contrast_threshold,
        )
    else:
        proj_u = np.zeros((h, w), dtype=np.float32)
        conf_u = np.ones((h, w), dtype=np.float32)
        valid_u = np.ones((h, w), dtype=bool)

    if sequence.row_bits:
        proj_v, conf_v, valid_v = _decode_axis(
            row_bits,
            sequence.row_bits,
            sequence.height,
            contrast_threshold=contrast_threshold,
        )
    else:
        proj_v = np.zeros((h, w), dtype=np.float32)
        conf_v = np.ones((h, w), dtype=np.float32)
        valid_v = np.ones((h, w), dtype=bool)

    confidence = np.minimum(conf_u, conf_v)
    valid = valid_u & valid_v
    proj_u = np.where(valid, proj_u, -1.0).astype(np.float32)
    proj_v = np.where(valid, proj_v, -1.0).astype(np.float32)
    confidence = np.where(valid, confidence, 0.0).astype(np.float32)
    return CorrespondenceMap(
        proj_u=proj_u, proj_v=proj_v, confidence=confidence, valid=valid
    )