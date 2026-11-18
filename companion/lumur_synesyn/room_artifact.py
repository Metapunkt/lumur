"""Register a Lumur room package as a Hub artifact (REQ-002-014).

The public Synesyn Hub accepts arbitrary ``artifact_type`` strings via
``POST /substrate/artifacts`` with ``inline_json`` / ``inline_bytes_base64``.
There is **no** first-class ``lumur.room`` type in ``Metapunkt/Synesyn`` yet —
this bridge uses ``json.lumur_room`` by convention and documents the Synesyn-side
touchpoint (document/accept the type beside workshop artifacts).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from lumur_synesyn.hub_client import HubError, SynesynHubClient

# Convention until Synesyn documents an official type (PRD-002 touchpoint).
ROOM_ARTIFACT_TYPE = "json.lumur_room"
ROOM_ARCHIVE_ARTIFACT_TYPE = "bytes.lumur_room_package"


def register_room_package(
    client: SynesynHubClient,
    room_package_dir: str | Path,
    *,
    room_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish ``room.json`` (+ light index) as a Hub ``json.lumur_room`` artifact.

    Returns ``{"ok": True, "artifact_id": ..., "artifact_type": ...}`` on success.
    Does not archive the full directory (paint PNGs / point clouds); that remains
    a Synesyn-side packaging decision (see docs/bridge/synesyn.md).
    """
    room_package_dir = Path(room_package_dir)
    room_json = room_package_dir / "room.json"
    if not room_json.is_file():
        raise HubError(f"room.json not found under {room_package_dir}")

    doc = json.loads(room_json.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise HubError("room.json must be a JSON object")

    paint_manifest = room_package_dir / "godot" / "paint_manifest.json"
    paint: dict[str, Any] | None = None
    if paint_manifest.is_file():
        try:
            paint = json.loads(paint_manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            paint = None

    payload = {
        "schema": "lumur.room_hub_registration",
        "schema_version": "1.0",
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "room_id": room_id or str(doc.get("id") or room_package_dir.name),
        "room": doc,
        "paint_manifest_summary": _paint_summary(paint) if paint else None,
        "package_path_hint": str(room_package_dir),
    }
    meta = {
        "provenance": {
            "generated_by": "lumur_synesyn.room_artifact",
            "room_id": payload["room_id"],
        },
        "ui": {"display_name": f"Lumur room {payload['room_id']}"},
        "lumur": {"kind": "room_package", "touchpoint": "json.lumur_room"},
    }
    if metadata:
        meta.update(metadata)

    art_id = client.create_artifact_json(ROOM_ARTIFACT_TYPE, payload, metadata=meta)
    return {
        "ok": True,
        "artifact_id": art_id,
        "artifact_type": ROOM_ARTIFACT_TYPE,
        "room_id": payload["room_id"],
        "note": (
            "Registered via generic substrate artifact API. "
            "Official lumur.room type acceptance is a Synesyn-side touchpoint "
            "(docs + optional workshop_artifacts allowlist)."
        ),
    }


def _paint_summary(paint: dict[str, Any]) -> dict[str, Any]:
    roles = list((paint.get("role_index") or {}).keys())
    generated = list((paint.get("generated_textures") or {}).keys())
    return {
        "roles": roles[:32],
        "generated_texture_keys": generated[:32],
        "surface_count": len(roles),
    }
