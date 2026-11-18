"""Orchestrate triangulation → plane segmentation → room package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from lumur.decode.graycode import CorrespondenceMap
from lumur.scan.planes import PlaneSegmentation, estimate_normals_from_planes, segment_planes
from lumur.scan.report import ScanReport, summarize_scan
from lumur.scan.triangulate import (
    TriangulationResult,
    build_projector_correspondence_map,
    triangulate_correspondences,
)
from lumur.schema.room import build_room_document, save_room_package


@dataclass
class ScanResult:
    triangulation: TriangulationResult
    segmentation: PlaneSegmentation
    report: ScanReport
    projector_map: dict[str, np.ndarray]
    normals: np.ndarray


def calibration_arrays(calibration: dict[str, Any]) -> dict[str, np.ndarray]:
    """Extract matrices needed for triangulation from a calibration document."""
    return {
        "camera_matrix": np.asarray(calibration["camera"]["matrix"], dtype=np.float64),
        "camera_distortion": np.asarray(
            calibration["camera"]["distortion"], dtype=np.float64
        ),
        "projector_matrix": np.asarray(
            calibration["projector"]["matrix"], dtype=np.float64
        ),
        "stereo_R": np.asarray(calibration["stereo"]["R"], dtype=np.float64),
        "stereo_T": np.asarray(calibration["stereo"]["T"], dtype=np.float64).reshape(3),
    }


def scan_from_correspondence(
    corr: CorrespondenceMap,
    calibration: dict[str, Any],
    *,
    min_decode_confidence: float = 0.05,
    max_reprojection_error_px: float = 3.0,
    plane_distance_threshold_m: float = 0.04,
    max_planes: int = 5,
    rng: np.random.Generator | None = None,
) -> ScanResult:
    """Run a full room scan from a decoded correspondence map + calibration."""
    mats = calibration_arrays(calibration)
    tri = triangulate_correspondences(
        corr,
        camera_matrix=mats["camera_matrix"],
        camera_distortion=mats["camera_distortion"],
        projector_matrix=mats["projector_matrix"],
        stereo_R=mats["stereo_R"],
        stereo_T=mats["stereo_T"],
        min_decode_confidence=min_decode_confidence,
        max_reprojection_error_px=max_reprojection_error_px,
    )
    seg = segment_planes(
        tri.points,
        tri.mask,
        max_planes=max_planes,
        distance_threshold_m=plane_distance_threshold_m,
        rng=rng,
    )
    normals = estimate_normals_from_planes(seg.surface_id, seg.planes)
    proj_size = tuple(int(x) for x in calibration["projector"]["image_size"])
    # Prefer projector_resolution from the document when present.
    if "projector_resolution" in calibration:
        proj_size = (
            int(calibration["projector_resolution"][0]),
            int(calibration["projector_resolution"][1]),
        )
    projector_map = build_projector_correspondence_map(
        tri.proj_u,
        tri.proj_v,
        tri.mask,
        tri.confidence,
        proj_size,
    )
    report = summarize_scan(tri, seg)
    return ScanResult(
        triangulation=tri,
        segmentation=seg,
        report=report,
        projector_map=projector_map,
        normals=normals,
    )


def write_scan_package(
    result: ScanResult,
    output_dir: str | Path,
    *,
    calibration: dict[str, Any],
    calibration_ref: str | None = None,
    notes: dict[str, Any] | None = None,
) -> Path:
    """Persist a ``ScanResult`` as a versioned room package directory."""
    tri = result.triangulation
    cam_h, cam_w = tri.mask.shape
    if "projector_resolution" in calibration:
        proj_w, proj_h = (
            int(calibration["projector_resolution"][0]),
            int(calibration["projector_resolution"][1]),
        )
    else:
        proj_w, proj_h = (
            int(calibration["projector"]["image_size"][0]),
            int(calibration["projector"]["image_size"][1]),
        )

    doc = build_room_document(
        calibration_ref=calibration_ref,
        calibration=calibration,
        projector_size=(proj_w, proj_h),
        camera_size=(cam_w, cam_h),
        planes=result.segmentation.to_dict()["planes"],
        floor_plane_id=result.segmentation.floor_plane_id,
        report=result.report.to_dict(),
        notes=notes,
    )
    points = {
        "points": tri.points,
        "depth": tri.depth,
        "normals": result.normals,
        "confidence": tri.confidence,
        "mask": tri.mask,
        "surface_id": result.segmentation.surface_id,
        "proj_u": tri.proj_u,
        "proj_v": tri.proj_v,
        "reprojection_error_px": tri.reprojection_error_px,
        "triangulation_angle_deg": tri.triangulation_angle_deg,
    }
    return save_room_package(
        output_dir, doc, points=points, projector_map=result.projector_map
    )
