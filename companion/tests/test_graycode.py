"""Unit tests for Gray-code encode/decode helpers."""

from __future__ import annotations

import numpy as np

from lumur.patterns.graycode import (
    binary_to_gray,
    bit_count,
    generate_graycode_sequence,
    gray_to_binary,
)


def test_gray_roundtrip_scalars():
    for n in range(256):
        assert gray_to_binary(binary_to_gray(n)) == n


def test_gray_roundtrip_vectorised():
    vals = np.arange(1024, dtype=np.uint32)
    assert np.array_equal(gray_to_binary(binary_to_gray(vals)), vals)


def test_bit_count():
    assert bit_count(1) == 1
    assert bit_count(2) == 1
    assert bit_count(3) == 2
    assert bit_count(1920) == 11


def test_sequence_shapes_and_inverses():
    seq = generate_graycode_sequence(64, 48)
    assert seq.col_bits == 6
    assert seq.row_bits == 6
    # Each bit has pattern + inverse for both axes.
    assert len(seq.frames) == (6 + 6) * 2
    for i in range(0, len(seq.frames), 2):
        primary = seq.frames[i]
        inverse = seq.frames[i + 1]
        assert primary.inverted is False
        assert inverse.inverted is True
        assert primary.image.shape == (48, 64)
        assert np.array_equal(primary.image + inverse.image, np.full((48, 64), 255))


def test_column_pattern_unique_codes():
    seq = generate_graycode_sequence(16, 8, axes=("col",))
    # Reconstruct gray codes from primary frames only.
    codes = np.zeros(16, dtype=np.uint32)
    primaries = [f for f in seq.frames if not f.inverted]
    for frame in primaries:
        shift = seq.col_bits - 1 - frame.bit
        on = (frame.image[0] > 0).astype(np.uint32)
        codes |= on << shift
    binary = gray_to_binary(codes)
    assert np.array_equal(binary, np.arange(16))