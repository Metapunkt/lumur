"""Reprojection residual report: mean and worst region."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class WorstRegion:
    """Axis-aligned tile of the camera image with the highest mean residual."""

    x0: int
    y0: int
    x1: int
    y1: int
    mean_px: float
    rms_px: float
    count: int

    def to_dict(self) -> dict:
        return {
            "bbox": [self.x0, self.y0, self.x1, self.y1],
            "mean_px": self.mean_px,
            "rms_px": self.rms_px,
            "count": self.count,
        }


@dataclass(frozen=True)
class ResidualReport:
    mean_px: float
    rms_px: float
    median_px: float
    count: int
    worst_region: WorstRegion

    def to_dict(self) -> dict:
        return {
            "mean_px": self.mean_px,
            "rms_px": self.rms_px,
            "median_px": self.median_px,
            "count": self.count,
            "worst_region": self.worst_region.to_dict(),
        }


def report_residuals(
    residual_image: np.ndarray,
    valid: np.ndarray,
    *,
    tile: int = 32,
) -> ResidualReport:
    """Summarise a per-pixel residual magnitude image.

    ``residual_image`` holds non-negative residual magnitudes in pixels.
    Only ``valid`` pixels contribute. The worst region is the ``tile``×``tile``
    window (clipped at borders) with the highest mean residual among windows
    that contain enough valid pixels.
    """
    if residual_image.shape != valid.shape:
        raise ValueError("residual_image and valid must share shape")
    vals = residual_image[valid]
    if vals.size == 0:
        empty = WorstRegion(0, 0, 0, 0, mean_px=0.0, rms_px=0.0, count=0)
        return ResidualReport(
            mean_px=0.0, rms_px=0.0, median_px=0.0, count=0, worst_region=empty
        )

    mean_px = float(vals.mean())
    rms_px = float(np.sqrt(np.mean(np.square(vals))))
    median_px = float(np.median(vals))

    h, w = valid.shape
    tile = max(1, min(tile, h, w))
    best: WorstRegion | None = None
    min_count = max(1, (tile * tile) // 8)

    for y0 in range(0, h, tile):
        for x0 in range(0, w, tile):
            y1 = min(h, y0 + tile)
            x1 = min(w, x0 + tile)
            region_valid = valid[y0:y1, x0:x1]
            count = int(region_valid.sum())
            if count < min_count:
                continue
            region_vals = residual_image[y0:y1, x0:x1][region_valid]
            region_mean = float(region_vals.mean())
            region_rms = float(np.sqrt(np.mean(np.square(region_vals))))
            candidate = WorstRegion(
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
                mean_px=region_mean,
                rms_px=region_rms,
                count=count,
            )
            if best is None or candidate.mean_px > best.mean_px:
                best = candidate

    if best is None:
        best = WorstRegion(0, 0, w, h, mean_px=mean_px, rms_px=rms_px, count=int(vals.size))

    return ResidualReport(
        mean_px=mean_px,
        rms_px=rms_px,
        median_px=median_px,
        count=int(vals.size),
        worst_region=best,
    )