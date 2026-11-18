"""Per-pixel mask codes for the room scan."""

from __future__ import annotations

# uint8 codes written into the room package ``mask`` array.
MASK_VALID = 0
MASK_INVALID = 1  # no Gray-code correspondence / shadowed
MASK_LOW_CONFIDENCE = 2
MASK_BAD_TRIANGULATION = 3  # behind camera, non-finite, or degenerate
MASK_OUTLIER = 4  # high reprojection residual

MASK_NAMES = {
    MASK_VALID: "valid",
    MASK_INVALID: "invalid",
    MASK_LOW_CONFIDENCE: "low_confidence",
    MASK_BAD_TRIANGULATION: "bad_triangulation",
    MASK_OUTLIER: "outlier",
}
