"""Synesyn Hub SurfaceGenerator provider (optional; ADR 0015 / 0016)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from lumur.generate.provider import ProgressCallback, SurfaceGenerator
from lumur.generate.store import store_success
from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceRenderResult
from lumur_synesyn.config import HubConfig
from lumur_synesyn.hub_client import (
    HubAuthError,
    HubError,
    HubTimeout,
    SynesynHubClient,
)


SYNESYN_KIND = "synesyn.render_request"
SYNESYN_SCHEMA_VERSION = 1


def to_synesyn_render_request(
    request: SurfaceRenderRequest,
    *,
    hub_base_url: str,
    comfy_base_url: str,
    input_uploads: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a SynesynRenderRequestV1-shaped payload from a Lumur request."""
    client = dict(request.client or {})
    client.setdefault("app_id", "lumur")
    if not client.get("client_id"):
        client["client_id"] = f"lumur_{uuid.uuid4().hex[:12]}"
    if not client.get("request_id"):
        client["request_id"] = f"lr_{uuid.uuid4().hex[:12]}"

    routing = {
        "mode": "hub",
        "provider": "comfyui",
        "comfy_base_url": comfy_base_url.rstrip("/"),
        "hub_base_url": hub_base_url.rstrip("/"),
    }
    # Surface is Lumur-only metadata carried in refs (Hub ignores unknown fields).
    refs = dict(request.refs or {})
    refs["lumur_surface"] = request.surface.to_dict()
    if request.preset_id:
        refs["lumur_preset_id"] = request.preset_id
    if request.preset_tags:
        refs["lumur_preset_tags"] = list(request.preset_tags)

    wf = dict(request.workflow or {})
    out: dict[str, Any] = {
        "schema_version": SYNESYN_SCHEMA_VERSION,
        "kind": SYNESYN_KIND,
        "routing": routing,
        "workflow": wf,
        "patches": list(request.patches or []),
        "client": client,
        "refs": refs,
        "output_routing": {
            "mode": "substrate",
            "render_request_artifact_type": "json.render_request",
            "images": {"artifact_type": "image.generated"},
        },
        "created_at": int(request.created_at),
        "timeout_sec": float((request.routing or {}).get("timeout_sec") or 180.0),
    }
    if input_uploads is not None:
        out["input_uploads"] = list(input_uploads)
    elif isinstance(request.input_uploads, list):
        out["input_uploads"] = list(request.input_uploads)
    elif request.input_uploads:
        # Convert Lumur dict-shaped uploads (slice 1) if already artifact-backed.
        converted: list[dict[str, Any]] = []
        for key, meta in dict(request.input_uploads).items():
            if not isinstance(meta, dict):
                continue
            art_id = str(meta.get("artifact_id") or "").strip()
            node_id = str(meta.get("node_id") or "").strip()
            if not art_id or not node_id:
                continue
            converted.append(
                {
                    "node_id": node_id,
                    "input": str(meta.get("input") or "image"),
                    "artifact_id": art_id,
                    "filename": str(meta.get("filename") or f"{key}.png"),
                    "role": key,
                }
            )
        if converted:
            out["input_uploads"] = converted
    return out


class SynesynHubSurfaceGenerator(SurfaceGenerator):
    """Submit surface renders via Hub ``/render/submit``; poll for ``image.generated``."""

    def __init__(
        self,
        config: HubConfig,
        *,
        room_package_dir: str | Path | None = None,
        client: SynesynHubClient | None = None,
    ) -> None:
        self.config = config
        self.client = client or SynesynHubClient(config)
        self.room_package_dir = Path(room_package_dir) if room_package_dir else None

    def ping(self) -> dict[str, Any]:
        return self.client.ping()

    def generate(
        self,
        request: SurfaceRenderRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> SurfaceRenderResult:
        routing = dict(request.routing or {})
        routing.setdefault("mode", "hub")
        routing.setdefault("provider", "comfyui")
        routing.setdefault("hub_base_url", self.config.normalized_url())
        if not routing.get("comfy_base_url"):
            routing["comfy_base_url"] = self.config.comfy_base_url
        routing.setdefault("timeout_sec", self.config.timeout_sec)
        request.routing = routing

        job_id = str((request.client or {}).get("request_id") or f"gen_{uuid.uuid4().hex[:12]}")
        try:
            request.validate()
        except ValueError as exc:
            return SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=job_id,
                error=str(exc),
                meta={"provider": "synesyn_hub"},
            )

        try:
            if on_progress:
                on_progress(1.0)

            # Upload control images as Hub artifacts for input_uploads.
            uploads = self._upload_controls(request)
            if on_progress:
                on_progress(5.0)

            syn_req = to_synesyn_render_request(
                request,
                hub_base_url=self.config.normalized_url(),
                comfy_base_url=str(routing["comfy_base_url"]),
                input_uploads=uploads or None,
            )
            hub_job_id = self.client.submit_render(syn_req)
            if on_progress:
                on_progress(10.0)

            try:
                job = self.client.poll_render_until_done(
                    hub_job_id,
                    timeout_sec=float(self.config.timeout_sec),
                    poll_interval_sec=float(self.config.poll_interval_sec),
                    on_progress=on_progress,
                )
            except HubTimeout as exc:
                return SurfaceRenderResult(
                    status=JobStatus.TIMEOUT,
                    job_id=job_id,
                    progress=getattr(exc, "progress", 0.0) or 0.0,
                    error=str(exc),
                    meta={
                        "provider": "synesyn_hub",
                        "synesyn_job_id": hub_job_id,
                    },
                )

            status = str(job.get("status") or "").strip().lower()
            if status not in ("completed", "succeeded", "success"):
                return SurfaceRenderResult(
                    status=JobStatus.FAILED,
                    job_id=job_id,
                    error=str(job.get("error") or f"hub job {status}"),
                    meta={
                        "provider": "synesyn_hub",
                        "synesyn_job_id": hub_job_id,
                        "hub_job": job,
                    },
                )

            image_ids = _image_artifact_ids(job)
            if not image_ids:
                return SurfaceRenderResult(
                    status=JobStatus.FAILED,
                    job_id=job_id,
                    error="hub job completed without image.generated artifacts",
                    meta={
                        "provider": "synesyn_hub",
                        "synesyn_job_id": hub_job_id,
                        "hub_job": job,
                    },
                )

            image_bytes = self.client.get_artifact_bytes(image_ids[0])
            output = job.get("output") if isinstance(job.get("output"), dict) else {}
            rr_art = str(
                job.get("render_request_artifact_id")
                or output.get("render_request_artifact_id")
                or ""
            )
            prompt_id = str(job.get("prompt_id") or output.get("prompt_id") or "") or None
            syn_extra = {
                "synesyn_job_id": hub_job_id,
                "synesyn_render_request_artifact_id": rr_art or None,
                "synesyn_image_artifact_ids": image_ids,
                "synesyn_workflow_artifact_id": str(
                    (request.workflow or {}).get("artifact_id") or ""
                )
                or None,
                "synesyn_prompt_id": prompt_id,
            }
            # Drop Nones for cleaner provenance.
            syn_extra = {k: v for k, v in syn_extra.items() if v is not None}

            result = SurfaceRenderResult(
                status=JobStatus.SUCCEEDED,
                job_id=job_id,
                prompt_id=prompt_id,
                progress=100.0,
                meta={"provider": "synesyn_hub", **syn_extra},
            )
            # Keep Hub-shaped input_uploads on the request for provenance.
            if uploads:
                request.input_uploads = {
                    str(u.get("role") or u.get("filename") or i): u
                    for i, u in enumerate(uploads)
                }

            if self.room_package_dir is not None:
                result = store_success(
                    self.room_package_dir,
                    request=request,
                    result=result,
                    image_bytes=image_bytes,
                    extra_provenance=syn_extra,
                )
            else:
                result.meta["image_bytes"] = image_bytes
            return result
        except HubAuthError as exc:
            return SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=job_id,
                error=f"auth: {exc}",
                meta={"provider": "synesyn_hub", "auth_error": True},
            )
        except HubError as exc:
            return SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=job_id,
                error=str(exc),
                meta={"provider": "synesyn_hub"},
            )

    def _upload_controls(self, request: SurfaceRenderRequest) -> list[dict[str, Any]]:
        uploads: list[dict[str, Any]] = []
        # Prefer already-list-shaped Hub uploads.
        if isinstance(request.input_uploads, list):
            return list(request.input_uploads)

        control_paths = dict(request.control_paths or {})
        upload_meta = dict(request.input_uploads or {})
        for key, path_str in control_paths.items():
            path = Path(path_str)
            if not path.is_file():
                raise HubError(f"control image missing: {path}")
            meta = upload_meta.get(key) if isinstance(upload_meta.get(key), dict) else {}
            node_id = str(meta.get("node_id") or "").strip()
            # Hub ``apply_input_uploads`` requires node_id + input + artifact_id.
            # Without a LoadImage (or similar) node target, skip wiring — still
            # register the control as an artifact for provenance when possible.
            art_id = self.client.create_artifact_bytes(
                "image.control",
                path.read_bytes(),
                ext=path.suffix.lstrip(".") or "png",
                metadata={
                    "provenance": {
                        "generated_by": "lumur_synesyn.hub_provider",
                        "role": key,
                        "surface": request.surface.to_dict(),
                    },
                    "ui": {"display_name": f"lumur control {key}"},
                },
            )
            if not node_id:
                continue
            uploads.append(
                {
                    "node_id": node_id,
                    "input": str(meta.get("input") or "image"),
                    "artifact_id": art_id,
                    "filename": path.name,
                    "role": key,
                }
            )
        return uploads


def _image_artifact_ids(job: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    output = job.get("output") if isinstance(job.get("output"), dict) else {}
    for key in ("final_image_artifact_ids", "image_artifact_ids"):
        vals = output.get(key) or job.get(key)
        if isinstance(vals, list):
            for v in vals:
                s = str(v).strip()
                if s and s not in ids:
                    ids.append(s)
    artifacts = job.get("artifacts") or []
    if isinstance(artifacts, list):
        for a in artifacts:
            if not isinstance(a, dict):
                continue
            at = str(a.get("artifact_type") or "")
            if at != "image.generated":
                continue
            aid = str(a.get("artifact_id") or a.get("id") or "").strip()
            if aid and aid not in ids:
                ids.append(aid)
    return ids
