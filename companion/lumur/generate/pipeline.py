"""High-level: build a surface-aware request and run generation into a room package."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from lumur.generate.comfy_provider import ComfyUISurfaceGenerator
from lumur.generate.controls import (
    build_control_images,
    load_role_index,
    resolve_surface_id,
    write_control_images,
)
from lumur.generate.jobs import GenerationJob, JobRunner
from lumur.generate.patches import size_patches_for_preset
from lumur.generate.presets import discover_presets, preset_tags, select_preset
from lumur.generate.provider import NullSurfaceGenerator, SurfaceGenerator
from lumur.generate.store import ensure_job_dir
from lumur.generate.types import SurfaceRenderRequest, SurfaceTarget
from lumur.schema.room import load_room_package


def surface_pixel_size(
    room_package_dir: Path,
    *,
    surface_id: int,
    default_width: int = 512,
    max_edge: int = 1024,
) -> tuple[int, int]:
    """Estimate a generation size from the surface's projector footprint aspect."""
    from lumur.paint.export import scatter_surface_id_to_projector

    _doc, points, projector_map = load_room_package(room_package_dir)
    sid = scatter_surface_id_to_projector(
        points["surface_id"].astype("int32"), projector_map
    )
    mask = sid == int(surface_id)
    if not mask.any():
        return default_width, default_width
    ys, xs = mask.nonzero()
    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    aspect = float(bw) / float(max(bh, 1))
    if aspect >= 1.0:
        w = int(min(max_edge, max(default_width, bw)))
        h = max(1, int(round(w / aspect)))
    else:
        h = int(min(max_edge, max(default_width, bh)))
        w = max(1, int(round(h * aspect)))
    # Keep even dimensions (latent-friendly).
    w -= w % 2
    h -= h % 2
    return max(w, 2), max(h, 2)


def build_surface_request(
    room_package_dir: str | Path,
    *,
    surface: str | int,
    comfy_base_url: str,
    preset_id: str | None = None,
    preset_dirs: list[str | Path] | None = None,
    room_id: str | None = None,
    scenario_key: str | None = None,
    width: int | None = None,
    height: int | None = None,
    include_controls: bool | None = None,
    session_id: str | None = None,
) -> tuple[SurfaceRenderRequest, dict[str, Any]]:
    """Select a preset, derive controls, and assemble a surface render request."""
    room_package_dir = Path(room_package_dir)
    doc, _points, _pmap = load_room_package(room_package_dir)
    role_index = load_role_index(room_package_dir)
    surface_id = resolve_surface_id(doc, surface=surface, role_index=role_index)

    role: str | None = None
    if not (isinstance(surface, int) or str(surface).isdigit()):
        role = str(surface)
    else:
        # Prefer a primary role from paint manifest.
        for name, sid in role_index.items():
            if int(sid) == int(surface_id) and not name.startswith("label:"):
                role = name
                break
    if role is None:
        role = f"id:{surface_id}"

    presets = discover_presets(preset_dirs)
    preset = select_preset(
        presets,
        surface_role=role if not role.startswith("id:") else "surface",
        room_id=room_id,
        scenario_key=scenario_key,
        preset_id=preset_id,
    )
    # If role was id:N and no preset_id, try common roles for this id via tags on any preset — already handled.
    if preset is None and not role.startswith("id:"):
        # Also try selecting with the raw role string variants.
        preset = select_preset(presets, surface_role=role, preset_id=preset_id)
    if preset is None:
        raise FileNotFoundError(
            f"no workflow preset for surface_role={role!r} "
            f"(preset_id={preset_id!r}); place JSON under presets/workflows/"
        )

    if width is None or height is None:
        est_w, est_h = surface_pixel_size(room_package_dir, surface_id=surface_id)
        width = int(width or est_w)
        height = int(height or est_h)

    controls_meta = dict(preset.get("controls") or {})
    want_mask = bool(controls_meta.get("mask", False))
    want_depth = bool(controls_meta.get("depth", False))
    want_normal = bool(controls_meta.get("normal", False))
    if include_controls is True:
        want_mask = want_depth = want_normal = True
    elif include_controls is False:
        want_mask = want_depth = want_normal = False

    job_id = f"gen_{uuid.uuid4().hex[:12]}"
    _, jdir = ensure_job_dir(room_package_dir, job_id)
    control_paths: dict[str, str] = {}
    if want_mask or want_depth or want_normal:
        images = build_control_images(
            room_package_dir,
            surface=surface_id,
            width=width,
            height=height,
            want_mask=want_mask,
            want_depth=want_depth,
            want_normal=want_normal,
        )
        written = write_control_images(images, jdir / "controls")
        control_paths = {k: str(v) for k, v in written.items()}

    patches = size_patches_for_preset(preset, width=width, height=height)
    # Optional control → LoadImage node wiring from preset metadata.
    input_uploads: dict[str, Any] = {}
    for key, node_meta in dict(preset.get("control_nodes") or {}).items():
        if key not in control_paths:
            continue
        input_uploads[key] = {
            "node_id": str(node_meta.get("node_id") or ""),
            "input": str(node_meta.get("input") or "image"),
        }

    request = SurfaceRenderRequest(
        surface=SurfaceTarget(role=role, surface_id=surface_id, width=width, height=height),
        routing={
            "mode": "direct",
            "provider": "comfyui",
            "comfy_base_url": comfy_base_url,
        },
        workflow={"inline": dict(preset.get("workflow") or {})},
        patches=patches,
        input_uploads=input_uploads,
        client={
            "app_id": "lumur",
            "client_id": f"lumur_{uuid.uuid4().hex[:10]}",
            "request_id": job_id,
            "session_id": session_id or "",
        },
        control_paths=control_paths,
        preset_id=str(preset.get("id") or ""),
        preset_tags=preset_tags(preset),
        refs={"room_package": str(room_package_dir), "preset_path": preset.get("_path")},
    )
    meta = {"preset": {"id": preset.get("id"), "tags": preset_tags(preset)}, "job_dir": str(jdir)}
    return request, meta


def make_provider(
    *,
    comfy_base_url: str | None,
    room_package_dir: str | Path | None,
    timeout_sec: float = 180.0,
    null: bool = False,
) -> SurfaceGenerator:
    if null or not comfy_base_url:
        return NullSurfaceGenerator()
    return ComfyUISurfaceGenerator(
        base_url=comfy_base_url,
        timeout_sec=timeout_sec,
        room_package_dir=room_package_dir,
    )


def run_generation(
    room_package_dir: str | Path,
    *,
    surface: str | int,
    comfy_base_url: str,
    preset_id: str | None = None,
    preset_dirs: list[str | Path] | None = None,
    width: int | None = None,
    height: int | None = None,
    timeout_sec: float = 180.0,
    wait: bool = True,
    include_controls: bool | None = None,
    room_id: str | None = None,
    scenario_key: str | None = None,
) -> GenerationJob:
    """Build request, submit via JobRunner, optionally wait for completion."""
    room_package_dir = Path(room_package_dir)
    request, _meta = build_surface_request(
        room_package_dir,
        surface=surface,
        comfy_base_url=comfy_base_url,
        preset_id=preset_id,
        preset_dirs=preset_dirs,
        room_id=room_id,
        scenario_key=scenario_key,
        width=width,
        height=height,
        include_controls=include_controls,
    )
    provider = ComfyUISurfaceGenerator(
        base_url=comfy_base_url,
        timeout_sec=timeout_sec,
        room_package_dir=room_package_dir,
    )
    runner = JobRunner(provider)
    job_id = runner.submit(request)
    if not wait:
        return runner.get(job_id)  # type: ignore[return-value]
    try:
        return runner.wait(job_id, timeout_sec=timeout_sec + 30.0)
    finally:
        runner.shutdown(wait=True)
