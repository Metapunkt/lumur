"""Build a Hub-routed surface request and run generation into a room package."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from lumur.generate.controls import (
    build_control_images,
    load_role_index,
    resolve_surface_id,
    write_control_images,
)
from lumur.generate.jobs import GenerationJob, JobRunner
from lumur.generate.patches import size_patches_for_preset
from lumur.generate.pipeline import surface_pixel_size
from lumur.generate.presets import preset_tags
from lumur.generate.store import ensure_job_dir
from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceRenderResult, SurfaceTarget
from lumur.schema.room import load_room_package
from lumur_synesyn.config import HubConfig
from lumur_synesyn.hub_client import HubAuthError, HubError, SynesynHubClient
from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator
from lumur_synesyn.presets import (
    discover_hub_workflow_presets,
    resolve_workflow_inline,
    select_hub_preset,
)
from lumur_synesyn.room_artifact import register_room_package


def build_hub_surface_request(
    room_package_dir: str | Path,
    *,
    surface: str | int,
    config: HubConfig,
    client: SynesynHubClient | None = None,
    preset_id: str | None = None,
    room_id: str | None = None,
    scenario_key: str | None = None,
    width: int | None = None,
    height: int | None = None,
    include_controls: bool | None = None,
    session_id: str | None = None,
    fallback_local_presets: bool = True,
) -> tuple[SurfaceRenderRequest, dict[str, Any]]:
    """Select a Hub ``json.workflow`` preset (or local fallback) and assemble a request."""
    room_package_dir = Path(room_package_dir)
    doc, _points, _pmap = load_room_package(room_package_dir)
    role_index = load_role_index(room_package_dir)
    surface_id = resolve_surface_id(doc, surface=surface, role_index=role_index)

    role: str | None = None
    if not (isinstance(surface, int) or str(surface).isdigit()):
        role = str(surface)
    else:
        for name, sid in role_index.items():
            if int(sid) == int(surface_id) and not name.startswith("label:"):
                role = name
                break
    if role is None:
        role = f"id:{surface_id}"

    hub = client or SynesynHubClient(config)
    hub_presets = discover_hub_workflow_presets(hub)
    select_role = role if not role.startswith("id:") else "surface"
    preset = select_hub_preset(
        hub_presets,
        surface_role=select_role,
        room_id=room_id,
        scenario_key=scenario_key,
        preset_id=preset_id,
    )

    local_fallback = False
    if preset is None and fallback_local_presets:
        from lumur.generate.presets import discover_presets, select_preset

        local = discover_presets()
        preset = select_preset(
            local,
            surface_role=select_role,
            room_id=room_id,
            scenario_key=scenario_key,
            preset_id=preset_id,
        )
        local_fallback = preset is not None

    if preset is None:
        raise FileNotFoundError(
            f"no Hub json.workflow preset tagged lumur:surface_role for "
            f"surface_role={role!r} (preset_id={preset_id!r}); "
            "save a SynPunkt workflow with that tag, or enable local fallback"
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
    input_uploads: dict[str, Any] = {}
    for key, node_meta in dict(preset.get("control_nodes") or {}).items():
        if key not in control_paths:
            continue
        input_uploads[key] = {
            "node_id": str(node_meta.get("node_id") or ""),
            "input": str(node_meta.get("input") or "image"),
        }

    if local_fallback:
        workflow: dict[str, Any] = {"inline": dict(preset.get("workflow") or {})}
        preset_path = preset.get("_path")
    else:
        # Prefer artifact_id so Hub reuses the SynPunkt preset; inline as backup.
        art_id = str(preset.get("artifact_id") or preset.get("id") or "")
        try:
            inline = resolve_workflow_inline(hub, preset)
        except Exception:  # noqa: BLE001 — fall back to empty; Hub will fetch by id
            inline = dict(preset.get("workflow") or {})
        workflow = {"artifact_id": art_id}
        if inline:
            workflow["inline"] = inline
        preset_path = None

    request = SurfaceRenderRequest(
        surface=SurfaceTarget(role=role, surface_id=surface_id, width=width, height=height),
        routing={
            "mode": "hub",
            "provider": "comfyui",
            "hub_base_url": config.normalized_url(),
            "comfy_base_url": config.comfy_base_url,
            "timeout_sec": config.timeout_sec,
        },
        workflow=workflow,
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
        refs={
            "room_package": str(room_package_dir),
            "preset_path": preset_path,
            "workflow_artifact_id": workflow.get("artifact_id"),
            "local_fallback": local_fallback,
        },
    )
    meta = {
        "preset": {"id": preset.get("id"), "tags": preset_tags(preset)},
        "job_dir": str(jdir),
        "local_fallback": local_fallback,
    }
    return request, meta


def run_hub_generation(
    room_package_dir: str | Path,
    *,
    surface: str | int,
    config: HubConfig,
    preset_id: str | None = None,
    width: int | None = None,
    height: int | None = None,
    wait: bool = True,
    include_controls: bool | None = None,
    room_id: str | None = None,
    scenario_key: str | None = None,
    register_room: bool = False,
    fallback_local_presets: bool = True,
) -> GenerationJob:
    """Build request, submit via JobRunner + Hub provider, optionally wait."""
    room_package_dir = Path(room_package_dir)
    client = SynesynHubClient(config)
    try:
        room_reg: dict[str, Any] | None = None
        if register_room:
            room_reg = register_room_package(client, room_package_dir, room_id=room_id)

        request, _meta = build_hub_surface_request(
            room_package_dir,
            surface=surface,
            config=config,
            client=client,
            preset_id=preset_id,
            room_id=room_id,
            scenario_key=scenario_key,
            width=width,
            height=height,
            include_controls=include_controls,
            fallback_local_presets=fallback_local_presets,
        )
        if room_reg and room_reg.get("artifact_id"):
            refs = dict(request.refs or {})
            refs["room_package_artifact_id"] = room_reg["artifact_id"]
            request.refs = refs
    except HubAuthError as exc:
        jid = f"gen_auth_{uuid.uuid4().hex[:8]}"
        return GenerationJob(
            job_id=jid,
            status=JobStatus.FAILED,
            error=f"auth: {exc}",
            result=SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=jid,
                error=f"auth: {exc}",
                meta={"provider": "synesyn_hub", "auth_error": True},
            ),
        )
    except HubError as exc:
        jid = f"gen_hub_{uuid.uuid4().hex[:8]}"
        return GenerationJob(
            job_id=jid,
            status=JobStatus.FAILED,
            error=str(exc),
            result=SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=jid,
                error=str(exc),
                meta={"provider": "synesyn_hub"},
            ),
        )

    provider = SynesynHubSurfaceGenerator(
        config, room_package_dir=room_package_dir, client=client
    )
    runner = JobRunner(provider)
    job_id = runner.submit(request)
    if not wait:
        return runner.get(job_id)  # type: ignore[return-value]
    try:
        return runner.wait(job_id, timeout_sec=float(config.timeout_sec) + 30.0)
    finally:
        runner.shutdown(wait=True)
