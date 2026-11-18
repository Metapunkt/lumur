"""Standalone ComfyUI surface generator (no Synesyn dependency)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from lumur.generate.comfy_client import (
    ComfyUIClient,
    ComfyUIError,
    ComfyUIProgressSocket,
    ComfyUITimeout,
)
from lumur.generate.patches import apply_patches
from lumur.generate.provider import ProgressCallback, SurfaceGenerator
from lumur.generate.store import store_success
from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceRenderResult


class ComfyUISurfaceGenerator(SurfaceGenerator):
    """Direct ComfyUI HTTP provider with optional WebSocket progress."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_sec: float = 180.0,
        poll_interval_sec: float = 0.25,
        room_package_dir: str | Path | None = None,
        use_websocket_progress: bool = True,
    ) -> None:
        self.default_base_url = (base_url or "").strip().rstrip("/") or None
        self.timeout_sec = float(timeout_sec)
        self.poll_interval_sec = float(poll_interval_sec)
        self.room_package_dir = Path(room_package_dir) if room_package_dir else None
        self.use_websocket_progress = bool(use_websocket_progress)

    def ping(self) -> dict[str, Any]:
        url = self.default_base_url
        if not url:
            return {"ok": False, "error": "comfy_base_url_not_configured"}
        return ComfyUIClient(url).ping()

    def generate(
        self,
        request: SurfaceRenderRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> SurfaceRenderResult:
        # Fill routing URL from constructor when omitted.
        routing = dict(request.routing or {})
        if not routing.get("comfy_base_url") and self.default_base_url:
            routing["comfy_base_url"] = self.default_base_url
            request.routing = routing
        try:
            request.validate()
        except ValueError as exc:
            return SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=str((request.client or {}).get("request_id") or uuid.uuid4().hex),
                error=str(exc),
            )

        client_id = str((request.client or {}).get("client_id") or f"lumur_{uuid.uuid4().hex[:12]}")
        job_id = str((request.client or {}).get("request_id") or f"gen_{uuid.uuid4().hex[:12]}")
        base_url = str(request.routing["comfy_base_url"]).strip().rstrip("/")
        client = ComfyUIClient(base_url, client_id=client_id)

        ws: ComfyUIProgressSocket | None = None
        if self.use_websocket_progress:
            ws = ComfyUIProgressSocket(base_url, client_id)
            ws.start()

        def _progress(value: float) -> None:
            if ws is not None and ws.progress > value:
                value = ws.progress
            if on_progress:
                on_progress(value)

        try:
            # Upload control images first (mask / depth / normal).
            input_uploads: dict[str, Any] = dict(request.input_uploads or {})
            for key, path_str in dict(request.control_paths or {}).items():
                path = Path(path_str)
                if not path.is_file():
                    raise ComfyUIError(f"control image missing: {path}")
                comfy_name = client.upload_image(
                    path.read_bytes(),
                    filename=path.name,
                    subfolder="lumur",
                )
                input_uploads[key] = {
                    "filename": path.name,
                    "comfy_name": comfy_name,
                    "role": key,
                }
            request.input_uploads = input_uploads

            workflow_inline = dict((request.workflow or {}).get("inline") or {})
            # Wire LoadImage-style patches when control uploads declare node targets.
            upload_patches: list[dict[str, Any]] = []
            for key, meta in input_uploads.items():
                if not isinstance(meta, dict):
                    continue
                node_id = str(meta.get("node_id") or "").strip()
                input_name = str(meta.get("input") or "image")
                comfy_name = str(meta.get("comfy_name") or "").strip()
                if node_id and comfy_name:
                    upload_patches.append(
                        {"node_id": node_id, "input": input_name, "value": comfy_name}
                    )
            workflow = apply_patches(
                workflow_inline, list(request.patches or []) + upload_patches
            )

            _progress(2.0)
            prompt_id = client.queue_prompt(workflow)
            _progress(5.0)

            try:
                history = client.poll_until_done(
                    prompt_id,
                    timeout_sec=self.timeout_sec,
                    poll_interval_sec=self.poll_interval_sec,
                    on_progress=_progress,
                )
            except ComfyUITimeout as exc:
                return SurfaceRenderResult(
                    status=JobStatus.TIMEOUT,
                    job_id=job_id,
                    prompt_id=prompt_id,
                    progress=getattr(ws, "progress", 0.0) if ws else 0.0,
                    error=str(exc),
                )

            if ws is not None and ws.error:
                return SurfaceRenderResult(
                    status=JobStatus.FAILED,
                    job_id=job_id,
                    prompt_id=prompt_id,
                    error=ws.error,
                )

            ref = client.first_image_ref(history)
            image_bytes = client.fetch_image(
                filename=ref["filename"],
                subfolder=ref.get("subfolder") or "",
                typ=ref.get("type") or "output",
            )
            result = SurfaceRenderResult(
                status=JobStatus.SUCCEEDED,
                job_id=job_id,
                prompt_id=prompt_id,
                progress=100.0,
                meta={"image_ref": ref, "provider": "comfyui"},
            )
            if self.room_package_dir is not None:
                result = store_success(
                    self.room_package_dir,
                    request=request,
                    result=result,
                    image_bytes=image_bytes,
                    extra_provenance={"image_ref": ref},
                )
            else:
                # Still expose bytes via a temp-less meta for callers that store themselves.
                result.meta["image_bytes"] = image_bytes
            return result
        except ComfyUIError as exc:
            return SurfaceRenderResult(
                status=JobStatus.FAILED,
                job_id=job_id,
                error=str(exc),
            )
        finally:
            if ws is not None:
                ws.stop()
