"""Gray-code structured-light pattern generation."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log2

import numpy as np


def bit_count(resolution: int) -> int:
    """Number of Gray-code bits needed to address ``resolution`` bins."""
    if resolution < 1:
        raise ValueError("resolution must be >= 1")
    if resolution == 1:
        return 1
    return int(ceil(log2(resolution)))


def binary_to_gray(n: np.ndarray | int) -> np.ndarray | int:
    return n ^ (n >> 1)


def gray_to_binary(gray: np.ndarray | int) -> np.ndarray | int:
    """Convert Gray code back to binary (vectorised for arrays)."""
    if isinstance(gray, (int, np.integer)):
        n = int(gray)
        mask = n >> 1
        while mask:
            n ^= mask
            mask >>= 1
        return n

    gray = np.asarray(gray, dtype=np.uint32)
    n = gray.copy()
    shift = 1
    max_bits = int(n.max()).bit_length() if n.size else 0
    while shift < max_bits:
        n ^= n >> shift
        shift <<= 1
    return n


@dataclass(frozen=True)
class PatternFrame:
    """One projected frame in a Gray-code sequence."""

    axis: str  # "col" or "row"
    bit: int
    inverted: bool
    image: np.ndarray  # uint8 HxW, 0 or 255


@dataclass(frozen=True)
class GrayCodeSequence:
    """Full Gray-code + inverse sequence for a projector resolution."""

    width: int
    height: int
    col_bits: int
    row_bits: int
    frames: tuple[PatternFrame, ...]

    @property
    def pattern_ids(self) -> tuple[str, ...]:
        return tuple(
            f"{f.axis}{f.bit}{'i' if f.inverted else ''}" for f in self.frames
        )


def _axis_pattern(
    length: int, bit: int, *, inverted: bool, vertical: bool, other: int
) -> np.ndarray:
    """Build one Gray-code stripe image.

    ``bit`` indexes from MSB (0) toward LSB so coarser stripes come first.
    """
    n_bits = bit_count(length)
    if bit < 0 or bit >= n_bits:
        raise ValueError(f"bit {bit} out of range for length {length}")

    coords = np.arange(length, dtype=np.uint32)
    gray = binary_to_gray(coords)
    shift = n_bits - 1 - bit
    on = ((gray >> shift) & 1).astype(np.uint8) * 255
    if inverted:
        on = 255 - on

    if vertical:
        # Columns vary → vertical stripes
        return np.tile(on[np.newaxis, :], (other, 1))
    # Rows vary → horizontal stripes
    return np.tile(on[:, np.newaxis], (1, other))


def generate_graycode_sequence(
    width: int,
    height: int,
    *,
    include_inverse: bool = True,
    axes: tuple[str, ...] = ("col", "row"),
) -> GrayCodeSequence:
    """Generate Gray-code (and optional inverse) patterns for a projector.

    Order: for each axis, for each bit from MSB to LSB, pattern then inverse.
    """
    if width < 1 or height < 1:
        raise ValueError("width and height must be >= 1")

    col_bits = bit_count(width) if "col" in axes else 0
    row_bits = bit_count(height) if "row" in axes else 0
    frames: list[PatternFrame] = []

    for axis in axes:
        if axis == "col":
            n_bits, length, vertical, other = col_bits, width, True, height
        elif axis == "row":
            n_bits, length, vertical, other = row_bits, height, False, width
        else:
            raise ValueError(f"unknown axis {axis!r}")

        for bit in range(n_bits):
            img = _axis_pattern(length, bit, inverted=False, vertical=vertical, other=other)
            frames.append(PatternFrame(axis=axis, bit=bit, inverted=False, image=img))
            if include_inverse:
                inv = _axis_pattern(
                    length, bit, inverted=True, vertical=vertical, other=other
                )
                frames.append(
                    PatternFrame(axis=axis, bit=bit, inverted=True, image=inv)
                )

    return GrayCodeSequence(
        width=width,
        height=height,
        col_bits=col_bits,
        row_bits=row_bits,
        frames=tuple(frames),
    )