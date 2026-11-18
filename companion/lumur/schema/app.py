"""Versioned app manifest schema and validation (``lumur.app`` v1.0).

See ADR 0017 and PRD-003 REQ-003-001 / REQ-003-002.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_ID = "lumur.app"
SCHEMA_VERSION = "1.0"
MANIFEST_FILENAME = "lumur.app.json"

# ADR 0019 vocabulary — unknown names fail validation (slice 1 contract).
KNOWN_INPUTS = frozenset(
    {"footstep", "presence", "zone_enter", "zone_leave", "gathering"}
)

# Surface requests must never carry projector/UV placement (ADR 0017).
_FORBIDDEN_SURFACE_KEYS = frozenset(
    {
        "plane_id",
        "surface_id",
        "pixel_rect",
        "projector_rect",
        "rect",
        "uv",
        "uvs",
        "uv_quad",
        "projector_uv",
        "pixels",
        "x",
        "y",
        "width_px",
        "height_px",
    }
)

_REQUIRED_TOP_LEVEL = (
    "schema",
    "schema_version",
    "id",
    "name",
    "version",
    "scene",
    "surfaces",
    "inputs",
)


def build_app_manifest(
    *,
    app_id: str,
    name: str,
    version: str,
    scene: str,
    surfaces: list[dict[str, Any]],
    inputs: list[str] | None = None,
    generation: bool = False,
    bridge: str | None = None,
    shares: list[str] | None = None,
    schema_version: str = SCHEMA_VERSION,
) -> dict[str, Any]:
    """Assemble a ``lumur.app`` document (does not write disk)."""
    doc: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "schema_version": schema_version,
        "id": app_id,
        "name": name,
        "version": version,
        "scene": scene,
        "surfaces": surfaces,
        "inputs": list(inputs or []),
        "generation": bool(generation),
        "bridge": bridge,
    }
    if shares is not None:
        doc["shares"] = list(shares)
    return doc


def validate_app_manifest(doc: dict[str, Any]) -> None:
    """Validate a ``lumur.app`` document.

    Unknown top-level and surface fields are ignored (append-friendly), except
    forbidden placement keys which always raise. Breaking schema versions raise.
    """
    if not isinstance(doc, dict):
        raise ValueError("app manifest must be a JSON object")
    if doc.get("schema") != SCHEMA_ID:
        raise ValueError(f"expected schema {SCHEMA_ID!r}, got {doc.get('schema')!r}")
    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {version!r}; "
            f"this build understands {SCHEMA_VERSION!r}"
        )
    for key in _REQUIRED_TOP_LEVEL:
        if key not in doc:
            raise ValueError(f"app manifest missing {key!r}")

    for field in ("id", "name", "version", "scene"):
        value = doc[field]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"app manifest {field!r} must be a non-empty string")

    surfaces = doc["surfaces"]
    if not isinstance(surfaces, list):
        raise ValueError("surfaces must be a list")
    keys_seen: set[str] = set()
    for i, req in enumerate(surfaces):
        _validate_surface_request(req, index=i, keys_seen=keys_seen)

    inputs = doc["inputs"]
    if not isinstance(inputs, list):
        raise ValueError("inputs must be a list")
    for item in inputs:
        if not isinstance(item, str) or not item:
            raise ValueError("inputs entries must be non-empty strings")
        if item not in KNOWN_INPUTS:
            raise ValueError(
                f"unknown input permission {item!r}; "
                f"known: {sorted(KNOWN_INPUTS)}"
            )

    if "generation" in doc and not isinstance(doc["generation"], bool):
        raise ValueError("generation must be a boolean")
    if "bridge" in doc and doc["bridge"] is not None:
        if not isinstance(doc["bridge"], str) or not doc["bridge"]:
            raise ValueError("bridge must be null or a non-empty string")
    if "shares" in doc:
        shares = doc["shares"]
        if not isinstance(shares, list) or not all(isinstance(s, str) for s in shares):
            raise ValueError("shares must be a list of strings")


def _validate_surface_request(
    req: Any, *, index: int, keys_seen: set[str]
) -> None:
    if not isinstance(req, dict):
        raise ValueError(f"surfaces[{index}] must be an object")
    forbidden = sorted(set(req) & _FORBIDDEN_SURFACE_KEYS)
    if forbidden:
        raise ValueError(
            f"surfaces[{index}] must not include placement fields {forbidden}; "
            "request surfaces by role/size/confidence only (ADR 0017)"
        )
    key = req.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValueError(f"surfaces[{index}].key must be a non-empty string")
    if key in keys_seen:
        raise ValueError(f"duplicate surface key {key!r}")
    keys_seen.add(key)

    role = req.get("role")
    if not isinstance(role, str) or not role.strip():
        raise ValueError(f"surfaces[{index}].role must be a non-empty string")

    if "min_width_m" in req:
        width = req["min_width_m"]
        if not isinstance(width, (int, float)) or isinstance(width, bool):
            raise ValueError(f"surfaces[{index}].min_width_m must be a number")
        if float(width) < 0:
            raise ValueError(f"surfaces[{index}].min_width_m must be >= 0")

    if "min_confidence" in req:
        conf = req["min_confidence"]
        if not isinstance(conf, (int, float)) or isinstance(conf, bool):
            raise ValueError(f"surfaces[{index}].min_confidence must be a number")
        if not 0.0 <= float(conf) <= 1.0:
            raise ValueError(f"surfaces[{index}].min_confidence must be in [0, 1]")

    if "count" in req:
        count = req["count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"surfaces[{index}].count must be an integer >= 1")

    if "required" in req and not isinstance(req["required"], bool):
        raise ValueError(f"surfaces[{index}].required must be a boolean")


def load_app_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate a ``lumur.app`` JSON file."""
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    validate_app_manifest(doc)
    return doc


def save_app_manifest(path: str | Path, document: dict[str, Any]) -> Path:
    """Validate and write a ``lumur.app`` JSON file."""
    path = Path(path)
    validate_app_manifest(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return path
