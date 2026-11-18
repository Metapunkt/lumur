"""Asynchronous job runner so callers never block the projector path (ADR 0008)."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from lumur.generate.provider import SurfaceGenerator
from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceRenderResult


@dataclass
class GenerationJob:
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    request: SurfaceRenderRequest | None = None
    result: SurfaceRenderResult | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "progress": self.progress,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "result": self.result.to_dict() if self.result else None,
        }


class JobRunner:
    """Submit generation onto a worker pool; poll without blocking the runtime."""

    def __init__(self, provider: SurfaceGenerator, *, max_workers: int = 2) -> None:
        self.provider = provider
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="lumur-gen"
        )
        self._jobs: dict[str, GenerationJob] = {}
        self._futures: dict[str, Future[SurfaceRenderResult]] = {}
        self._lock = threading.Lock()

    def submit(self, request: SurfaceRenderRequest) -> str:
        job_id = str((request.client or {}).get("request_id") or "") or f"job_{uuid.uuid4().hex[:12]}"
        job = GenerationJob(job_id=job_id, request=request, status=JobStatus.QUEUED)
        with self._lock:
            self._jobs[job_id] = job

        def _on_progress(value: float) -> None:
            with self._lock:
                j = self._jobs.get(job_id)
                if j is None:
                    return
                j.progress = float(value)
                j.status = JobStatus.RUNNING
                j.updated_at = time.time()

        def _run() -> SurfaceRenderResult:
            with self._lock:
                j = self._jobs[job_id]
                j.status = JobStatus.RUNNING
                j.updated_at = time.time()
            return self.provider.generate(request, on_progress=_on_progress)

        future = self._executor.submit(_run)
        self._futures[job_id] = future

        def _done(fut: Future[SurfaceRenderResult]) -> None:
            with self._lock:
                j = self._jobs.get(job_id)
                if j is None:
                    return
                try:
                    result = fut.result()
                except Exception as exc:  # noqa: BLE001 — surface to job status
                    j.status = JobStatus.FAILED
                    j.error = str(exc)
                    j.result = SurfaceRenderResult(
                        status=JobStatus.FAILED,
                        job_id=job_id,
                        error=str(exc),
                    )
                else:
                    j.result = result
                    j.status = result.status
                    j.progress = result.progress
                    j.error = result.error
                j.updated_at = time.time()

        future.add_done_callback(_done)
        return job_id

    def get(self, job_id: str) -> GenerationJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            # Shallow copy fields for a stable snapshot.
            return GenerationJob(
                job_id=job.job_id,
                status=job.status,
                progress=job.progress,
                request=job.request,
                result=job.result,
                error=job.error,
                created_at=job.created_at,
                updated_at=job.updated_at,
            )

    def wait(
        self,
        job_id: str,
        *,
        timeout_sec: float | None = None,
        poll_interval_sec: float = 0.05,
    ) -> GenerationJob:
        t0 = time.time()
        while True:
            job = self.get(job_id)
            if job is None:
                raise KeyError(job_id)
            if job.status in (
                JobStatus.SUCCEEDED,
                JobStatus.FAILED,
                JobStatus.TIMEOUT,
                JobStatus.SKIPPED,
            ):
                return job
            if timeout_sec is not None and (time.time() - t0) > timeout_sec:
                return job
            time.sleep(poll_interval_sec)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)
