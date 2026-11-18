"""Surface render request / result shapes (Synesyn-aligned by convention).

Canonical kind is ``lumur.surface_render_request``. Field names mirror
``SynesynRenderRequestV1`` where sensible (``routing``, ``workflow``,
``patches``, ``client``, ``input_uploads``) without importing Synesyn types.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = 1
KIND = "lumur.surface_render_request"
PROVENANCE_SCHEMA = "lumur.generation_provenance"
PROVENANCE_VERSION = "1.0"
GENERATED_MANIFEST_SCHEMA = "lumur.generated"
GENERATED_MANIFEST_VERSION = "1.0"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"  # null provider / no-op


@dataclass
class SurfaceTarget:
    """Target surface addressing + pixel size / aspect for generation."""

    role: str | None = None
    surface_id: int | None = None
    width: int = 512
    height: int = 512

    @property
    def aspect(self) -> float:
        return float(self.width) / float(max(self.height, 1))

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "id": self.surface_id,
            "width": int(self.width),
            "height": int(self.height),
            "aspect": self.aspect,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SurfaceTarget:
        return cls(
            role=(str(data["role"]) if data.get("role") not in (None, "") else None),
            surface_id=(
                int(data["id"])
                if data.get("id") is not None
                else (int(data["surface_id"]) if data.get("surface_id") is not None else None)
            ),
            width=int(data.get("width") or 512),
            height=int(data.get("height") or 512),
        )


@dataclass
class SurfaceRenderRequest:
    """Surface-aware generation request (direct ComfyUI in slice 1)."""

    surface: SurfaceTarget
    routing: dict[str, Any] = field(default_factory=dict)
    workflow: dict[str, Any] = field(default_factory=dict)
    patches: list[dict[str, Any]] = field(default_factory=list)
    input_uploads: dict[str, Any] = field(default_factory=dict)
    client: dict[str, Any] = field(default_factory=dict)
    refs: dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    kind: str = KIND
    created_at: int = field(default_factory=lambda: int(time.time()))
    # Local-only: absolute paths for control images before upload.
    control_paths: dict[str, str] = field(default_factory=dict)
    preset_id: str | None = None
    preset_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        routing = dict(self.routing or {})
        routing.setdefault("mode", "direct")
        routing.setdefault("provider", "comfyui")
        client = dict(self.client or {})
        client.setdefault("app_id", "lumur")
        if not client.get("client_id"):
            client["client_id"] = f"lumur_{uuid.uuid4().hex[:12]}"
        if not client.get("request_id"):
            client["request_id"] = f"lr_{uuid.uuid4().hex[:12]}"
        out: dict[str, Any] = {
            "schema_version": int(self.schema_version),
            "kind": self.kind,
            "routing": routing,
            "surface": self.surface.to_dict(),
            "workflow": dict(self.workflow or {}),
            "patches": list(self.patches or []),
            "input_uploads": dict(self.input_uploads or {}),
            "client": client,
            "refs": dict(self.refs or {}),
            "created_at": int(self.created_at),
        }
        if self.preset_id:
            out["preset_id"] = self.preset_id
        if self.preset_tags:
            out["preset_tags"] = list(self.preset_tags)
        if self.control_paths:
            out["control_paths"] = dict(self.control_paths)
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SurfaceRenderRequest:
        surface = SurfaceTarget.from_dict(dict(data.get("surface") or {}))
        return cls(
            surface=surface,
            routing=dict(data.get("routing") or {}),
            workflow=dict(data.get("workflow") or {}),
            patches=list(data.get("patches") or []),
            input_uploads=dict(data.get("input_uploads") or {}),
            client=dict(data.get("client") or {}),
            refs=dict(data.get("refs") or {}),
            schema_version=int(data.get("schema_version") or SCHEMA_VERSION),
            kind=str(data.get("kind") or KIND),
            created_at=int(data.get("created_at") or time.time()),
            control_paths={
                str(k): str(v) for k, v in dict(data.get("control_paths") or {}).items()
            },
            preset_id=(str(data["preset_id"]) if data.get("preset_id") else None),
            preset_tags=[str(t) for t in list(data.get("preset_tags") or [])],
        )

    def validate(self) -> None:
        if int(self.schema_version) != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version}")
        if self.kind != KIND:
            raise ValueError(f"invalid kind {self.kind!r}")
        routing = self.routing or {}
        mode = str(routing.get("mode") or "direct").lower()
        provider = str(routing.get("provider") or "comfyui").lower()
        # Align with SynesynRenderRequestV1: direct | hub; provider stays comfyui.
        # Hub submit lives in optional ``lumur_synesyn`` — core only validates shape.
        if mode not in ("direct", "hub"):
            raise ValueError(f"unsupported routing.mode {mode!r} (direct|hub)")
        if provider != "comfyui":
            raise ValueError("routing.provider must be comfyui")
        if mode == "direct" and not str(routing.get("comfy_base_url") or "").strip():
            raise ValueError("comfy_base_url required for direct ComfyUI")
        if mode == "hub" and not str(routing.get("hub_base_url") or "").strip():
            raise ValueError("hub_base_url required for hub routing")
        wf = self.workflow or {}
        has_inline = isinstance(wf.get("inline"), dict) and bool(wf.get("inline"))
        has_art = bool(str(wf.get("artifact_id") or "").strip())
        if not has_inline and not has_art:
            raise ValueError("workflow.inline or workflow.artifact_id required")
        if self.surface.width < 1 or self.surface.height < 1:
            raise ValueError("surface width/height must be positive")


@dataclass
class SurfaceRenderResult:
    """Successful (or terminal) generation result with optional provenance."""

    status: JobStatus
    job_id: str
    image_path: str | None = None
    provenance_path: str | None = None
    prompt_id: str | None = None
    progress: float = 0.0
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d
