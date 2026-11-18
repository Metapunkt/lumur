"""Versioned room package schema and I/O (``lumur.room`` v1.0)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA_ID = "lumur.room"
SCHEMA_VERSION = "1.0"

# Sidecar array files relative to the package directory.
POINTS_FILENAME = "points.npz"
PROJECTOR_MAP_FILENAME = "projector_map.npz"
MANIFEST_FILENAME = "room.json"


def build_room_document(
    *,
    calibration_ref: str | None,
    calibration: dict[str, Any] | None,
    projector_size: tuple[int, int],
    camera_size: tuple[int, int],
    planes: list[dict[str, Any]],
    floor_plane_id: int | None,
    report: dict[str, Any],
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the JSON manifest for a room package."""
    doc: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "projector_resolution": [int(projector_size[0]), int(projector_size[1])],
        "camera_resolution": [int(camera_size[0]), int(camera_size[1])],
        "calibration_ref": calibration_ref,
        "arrays": {
            "points": POINTS_FILENAME,
            "projector_map": PROJECTOR_MAP_FILENAME,
        },
        "planes": planes,
        "floor_plane_id": floor_plane_id,
        "report": report,
        "coordinate_frame": "camera",
        "mask_codes": {
            "0": "valid",
            "1": "invalid",
            "2": "low_confidence",
            "3": "bad_triangulation",
            "4": "outlier",
        },
    }
    if calibration is not None:
        doc["calibration"] = {
            "schema": calibration.get("schema"),
            "schema_version": calibration.get("schema_version"),
            "camera": calibration.get("camera"),
            "projector": calibration.get("projector"),
            "stereo": calibration.get("stereo"),
            "method": calibration.get("method"),
        }
    if notes:
        doc["notes"] = notes
    return doc


def validate_room_document(doc: dict[str, Any]) -> None:
    if doc.get("schema") != SCHEMA_ID:
        raise ValueError(f"expected schema {SCHEMA_ID!r}, got {doc.get('schema')!r}")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {doc.get('schema_version')!r}; "
            f"this build understands {SCHEMA_VERSION!r}"
        )
    for key in (
        "created_at",
        "projector_resolution",
        "camera_resolution",
        "arrays",
        "planes",
        "floor_plane_id",
        "report",
        "coordinate_frame",
    ):
        if key not in doc:
            raise ValueError(f"room document missing {key!r}")
    arrays = doc["arrays"]
    for key in ("points", "projector_map"):
        if key not in arrays:
            raise ValueError(f"arrays missing {key!r}")


def save_room_package(
    directory: str | Path,
    document: dict[str, Any],
    *,
    points: dict[str, np.ndarray],
    projector_map: dict[str, np.ndarray],
) -> Path:
    """Write ``room.json`` + ``points.npz`` + ``projector_map.npz``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    validate_room_document(document)
    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(document, indent=2) + "\n", encoding="utf-8"
    )
    np.savez_compressed(directory / POINTS_FILENAME, **points)
    np.savez_compressed(directory / PROJECTOR_MAP_FILENAME, **projector_map)
    return directory


def load_room_package(directory: str | Path) -> tuple[dict[str, Any], dict, dict]:
    """Load a room package. Returns ``(document, points, projector_map)``."""
    directory = Path(directory)
    doc = json.loads((directory / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    validate_room_document(doc)
    points = dict(np.load(directory / doc["arrays"]["points"]))
    projector_map = dict(np.load(directory / doc["arrays"]["projector_map"]))
    return doc, points, projector_map
