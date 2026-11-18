"""Pluggable surface-generator interface (ADR 0016)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceRenderResult


ProgressCallback = Callable[[float], None]


class SurfaceGenerator(ABC):
    """Async-friendly provider: submit work, never own the projector path."""

    @abstractmethod
    def generate(
        self,
        request: SurfaceRenderRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> SurfaceRenderResult:
        """Run (or no-op) a surface generation job to completion.

        Implementations may block the *caller thread*; the runtime must
        invoke this off the render / critical path (see ``JobRunner``).
        """

    def ping(self) -> dict[str, Any]:
        """Optional health check. Default: report as unavailable."""
        return {"ok": False, "error": "not_implemented"}


class NullSurfaceGenerator(SurfaceGenerator):
    """Default when nothing is configured: no generation, no render errors."""

    def generate(
        self,
        request: SurfaceRenderRequest,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> SurfaceRenderResult:
        if on_progress:
            on_progress(100.0)
        return SurfaceRenderResult(
            status=JobStatus.SKIPPED,
            job_id=str((request.client or {}).get("request_id") or "null"),
            progress=100.0,
            meta={"provider": "null"},
        )

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "provider": "null", "note": "no generation"}
