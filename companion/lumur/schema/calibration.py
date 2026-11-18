"""Versioned calibration JSON schema and I/O."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lumur.calibrate.geometry import CalibrationResult

SCHEMA_VERSION = "1.0"
SCHEMA_ID = "lumur.calibration"


def build_calibration_document(
    result: CalibrationResult,
    *,
    projector_size: tuple[int, int],
    notes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a versioned calibration document from a ``CalibrationResult``."""
    doc: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "projector_resolution": [int(projector_size[0]), int(projector_size[1])],
        **result.to_dict(),
    }
    if notes:
        doc["notes"] = notes
    return doc


def save_calibration(doc: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def load_calibration(path: str | Path) -> dict[str, Any]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_calibration_document(doc)
    return doc


def validate_calibration_document(doc: dict[str, Any]) -> None:
    """Raise ``ValueError`` if required keys / version are missing."""
    if doc.get("schema") != SCHEMA_ID:
        raise ValueError(f"expected schema {SCHEMA_ID!r}, got {doc.get('schema')!r}")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {doc.get('schema_version')!r}; "
            f"this build understands {SCHEMA_VERSION!r}"
        )
    for key in ("camera", "projector", "stereo", "residuals", "created_at"):
        if key not in doc:
            raise ValueError(f"calibration document missing {key!r}")
    for device in ("camera", "projector"):
        block = doc[device]
        for field in ("image_size", "matrix", "distortion"):
            if field not in block:
                raise ValueError(f"{device} missing {field!r}")
    stereo = doc["stereo"]
    for field in ("R", "T", "scale_source"):
        if field not in stereo:
            raise ValueError(f"stereo missing {field!r}")
    residuals = doc["residuals"]
    for field in ("mean_px", "rms_px", "worst_region"):
        if field not in residuals:
            raise ValueError(f"residuals missing {field!r}")
    worst = residuals["worst_region"]
    if "bbox" not in worst or "mean_px" not in worst:
        raise ValueError("residuals.worst_region must include bbox and mean_px")