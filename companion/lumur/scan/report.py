"""Coverage / confidence summary for a room scan."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.calibrate.residuals import WorstRegion, report_residuals
from lumur.scan.masks import MASK_NAMES, MASK_VALID
from lumur.scan.planes import PlaneSegmentation
from lumur.scan.triangulate import TriangulationResult


@dataclass(frozen=True)
class ScanReport:
    covered_fraction: float
    valid_fraction: float
    mean_confidence: float
    median_confidence: float
    mask_histogram: dict[str, int]
    worst_region: dict
    plane_residuals: list[dict]
    floor_plane_id: int | None
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "covered_fraction": self.covered_fraction,
            "valid_fraction": self.valid_fraction,
            "mean_confidence": self.mean_confidence,
            "median_confidence": self.median_confidence,
            "mask_histogram": self.mask_histogram,
            "worst_region": self.worst_region,
            "plane_residuals": self.plane_residuals,
            "floor_plane_id": self.floor_plane_id,
            "notes": list(self.notes),
        }


def summarize_scan(
    triangulation: TriangulationResult,
    segmentation: PlaneSegmentation,
    *,
    tile: int = 16,
) -> ScanReport:
    """Build a confidence / coverage report for CLI and the room package."""
    mask = triangulation.mask
    conf = triangulation.confidence
    h, w = mask.shape
    total = float(h * w)
    valid = mask == MASK_VALID
    covered = np.isfinite(triangulation.depth)
    hist = {
        MASK_NAMES[code]: int((mask == code).sum())
        for code in sorted(MASK_NAMES.keys())
    }

    # Worst region = lowest mean confidence among tiles with enough coverage.
    # Reuse residual reporter by inverting confidence into a "cost".
    cost = np.where(covered, 1.0 - conf, 0.0).astype(np.float32)
    residual_report = report_residuals(cost, covered, tile=tile)
    worst = residual_report.worst_region.to_dict()
    # Reinterpret mean_px as mean confidence deficit for the tile.
    if residual_report.worst_region.count > 0:
        bbox = residual_report.worst_region
        region = conf[bbox.y0 : bbox.y1, bbox.x0 : bbox.x1]
        region_cov = covered[bbox.y0 : bbox.y1, bbox.x0 : bbox.x1]
        mean_conf = float(region[region_cov].mean()) if region_cov.any() else 0.0
        worst = {
            "bbox": [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
            "mean_confidence": mean_conf,
            "mean_confidence_deficit": float(bbox.mean_px),
            "count": int(bbox.count),
        }
    else:
        worst = WorstRegion(0, 0, 0, 0, 0.0, 0.0, 0).to_dict()

    plane_residuals = [
        {
            "plane_id": p.plane_id,
            "kind": p.kind,
            "label": p.label,
            "residual_rms_m": p.residual_rms_m,
            "inlier_count": p.inlier_count,
        }
        for p in segmentation.planes
        if p.kind != "non_planar"
    ]

    notes: list[str] = []
    if segmentation.floor_plane_id is None:
        notes.append("floor plane was not identified")
    if float(covered.mean()) < 0.2:
        notes.append("low geometric coverage; check decode contrast and pose")
    notes.append(
        "pose/translation direction is weakly constrained in purely planar "
        "scenes; prefer room_with_box (or non-planar structure) when judging "
        "metric depth accuracy"
    )

    conf_vals = conf[valid]
    return ScanReport(
        covered_fraction=float(covered.mean()) if total else 0.0,
        valid_fraction=float(valid.mean()) if total else 0.0,
        mean_confidence=float(conf_vals.mean()) if conf_vals.size else 0.0,
        median_confidence=float(np.median(conf_vals)) if conf_vals.size else 0.0,
        mask_histogram=hist,
        worst_region=worst,
        plane_residuals=plane_residuals,
        floor_plane_id=segmentation.floor_plane_id,
        notes=notes,
    )
