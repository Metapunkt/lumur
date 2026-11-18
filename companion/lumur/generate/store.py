"""Persist generation results + provenance into a room / session folder."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from lumur.generate.types import (
    GENERATED_MANIFEST_SCHEMA,
    GENERATED_MANIFEST_VERSION,
    PROVENANCE_SCHEMA,
    PROVENANCE_VERSION,
    SurfaceRenderRequest,
    SurfaceRenderResult,
)

GENERATED_SUBDIR = "generated"
GENERATED_MANIFEST = "manifest.json"


def new_job_id() -> str:
    return f"gen_{uuid.uuid4().hex[:12]}"


def job_dir(room_package_dir: str | Path, job_id: str) -> Path:
    return Path(room_package_dir) / GENERATED_SUBDIR / job_id


def ensure_job_dir(room_package_dir: str | Path, job_id: str | None = None) -> tuple[str, Path]:
    jid = job_id or new_job_id()
    path = job_dir(room_package_dir, jid)
    path.mkdir(parents=True, exist_ok=True)
    (path / "controls").mkdir(exist_ok=True)
    return jid, path


def write_request_snapshot(path: Path, request: SurfaceRenderRequest) -> Path:
    out = path / "request.json"
    # Drop bulky inline workflow duplication when writing? Keep full snapshot.
    data = request.to_dict()
    # Avoid embedding absolute host-only paths as required fields.
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return out


def write_provenance(
    path: Path,
    *,
    request: SurfaceRenderRequest,
    result: SurfaceRenderResult,
    extra: dict[str, Any] | None = None,
) -> Path:
    doc: dict[str, Any] = {
        "schema": PROVENANCE_SCHEMA,
        "schema_version": PROVENANCE_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "job_id": result.job_id,
        "status": result.status.value,
        "provider": "comfyui",
        "prompt_id": result.prompt_id,
        "surface": request.surface.to_dict(),
        "preset_id": request.preset_id,
        "preset_tags": list(request.preset_tags or []),
        "routing": dict(request.routing or {}),
        "client": dict(request.client or {}),
        "refs": dict(request.refs or {}),
        "input_uploads": dict(request.input_uploads or {}),
        "image": Path(result.image_path).name if result.image_path else None,
        "error": result.error,
    }
    if extra:
        doc["extra"] = extra
    out = path / "provenance.json"
    out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return out


def write_result_image(path: Path, image_bytes: bytes, filename: str = "result.png") -> Path:
    out = path / filename
    out.write_bytes(image_bytes)
    return out


def _load_generated_manifest(room_package_dir: Path) -> dict[str, Any]:
    path = room_package_dir / GENERATED_SUBDIR / GENERATED_MANIFEST
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema": GENERATED_MANIFEST_SCHEMA,
        "schema_version": GENERATED_MANIFEST_VERSION,
        "surfaces": {},
        "jobs": [],
    }


def update_generated_manifest(
    room_package_dir: str | Path,
    *,
    request: SurfaceRenderRequest,
    result: SurfaceRenderResult,
    relative_image: str,
    relative_provenance: str,
) -> Path:
    room_package_dir = Path(room_package_dir)
    gen_dir = room_package_dir / GENERATED_SUBDIR
    gen_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_generated_manifest(room_package_dir)
    surfaces = dict(manifest.get("surfaces") or {})
    key = request.surface.role or (
        f"id:{request.surface.surface_id}" if request.surface.surface_id is not None else result.job_id
    )
    entry = {
        "surface_role": request.surface.role,
        "surface_id": request.surface.surface_id,
        "job_id": result.job_id,
        "status": result.status.value,
        "texture": relative_image,
        "provenance": relative_provenance,
        "width": request.surface.width,
        "height": request.surface.height,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    surfaces[str(key)] = entry
    # Also index by surface id when known.
    if request.surface.surface_id is not None:
        surfaces[f"id:{int(request.surface.surface_id)}"] = entry
    manifest["surfaces"] = surfaces
    jobs = list(manifest.get("jobs") or [])
    jobs.append(
        {
            "job_id": result.job_id,
            "status": result.status.value,
            "surface_role": request.surface.role,
            "surface_id": request.surface.surface_id,
            "texture": relative_image,
            "provenance": relative_provenance,
        }
    )
    manifest["jobs"] = jobs[-50:]  # keep a short recent history
    out = gen_dir / GENERATED_MANIFEST
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out


def update_paint_manifest_generated(
    room_package_dir: str | Path,
    *,
    surface_id: int | None,
    surface_role: str | None,
    relative_texture: str,
    job_id: str,
) -> Path | None:
    """Patch ``godot/paint_manifest.json`` with a generated texture pointer.

    Returns the manifest path, or ``None`` if Godot assets are not exported yet.
    """
    room_package_dir = Path(room_package_dir)
    manifest_path = room_package_dir / "godot" / "paint_manifest.json"
    if not manifest_path.is_file():
        return None
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    generated = dict(data.get("generated_textures") or {})
    if surface_id is not None:
        generated[str(int(surface_id))] = {
            "path": relative_texture,
            "role": surface_role,
            "job_id": job_id,
        }
    if surface_role:
        generated[str(surface_role)] = {
            "path": relative_texture,
            "surface_id": surface_id,
            "job_id": job_id,
        }
    data["generated_textures"] = generated
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def store_success(
    room_package_dir: str | Path,
    *,
    request: SurfaceRenderRequest,
    result: SurfaceRenderResult,
    image_bytes: bytes,
    extra_provenance: dict[str, Any] | None = None,
) -> SurfaceRenderResult:
    """Write image + provenance and update manifests; return updated result."""
    room_package_dir = Path(room_package_dir)
    jid, path = ensure_job_dir(room_package_dir, result.job_id)
    result.job_id = jid
    write_request_snapshot(path, request)
    image_path = write_result_image(path, image_bytes)
    result.image_path = str(image_path)
    prov_path = write_provenance(
        path, request=request, result=result, extra=extra_provenance
    )
    result.provenance_path = str(prov_path)
    rel_image = f"{GENERATED_SUBDIR}/{jid}/{image_path.name}"
    rel_prov = f"{GENERATED_SUBDIR}/{jid}/{prov_path.name}"
    update_generated_manifest(
        room_package_dir,
        request=request,
        result=result,
        relative_image=rel_image,
        relative_provenance=rel_prov,
    )
    # paint_manifest paths are relative to godot/, so climb one level.
    paint_rel = f"../{rel_image}"
    update_paint_manifest_generated(
        room_package_dir,
        surface_id=request.surface.surface_id,
        surface_role=request.surface.role,
        relative_texture=paint_rel,
        job_id=jid,
    )
    return result
