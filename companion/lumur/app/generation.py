"""App-side SurfaceGenerator requests (PRD-003 REQ-003-014).

Apps with ``generation: true`` may request per-surface content through the
existing provider interface. Requests apply only to surfaces the app owns
or overlays (ADR 0018). Missing / failing providers leave last-good content;
core never imports the optional bridge package.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lumur.app.lifecycle import AppLifecycle, AppState, LifecycleError
from lumur.generate.provider import NullSurfaceGenerator, SurfaceGenerator
from lumur.generate.types import (
    JobStatus,
    SurfaceRenderRequest,
    SurfaceRenderResult,
    SurfaceTarget,
)


class GenerationDenied(LifecycleError):
    """App may not generate for this surface / state."""

    def __init__(self, message: str, *, reason: str = "generation_denied"):
        super().__init__(message, reason=reason)


@dataclass
class AppGenerationRecord:
    """One app generation attempt (observable for sim / replay)."""

    app_id: str
    surface_key: str
    surface_id: int | None
    status: str
    provider: str
    job_id: str | None = None
    denied_reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "surface_key": self.surface_key,
            "surface_id": self.surface_id,
            "status": self.status,
            "provider": self.provider,
            "job_id": self.job_id,
            "denied_reason": self.denied_reason,
            "meta": dict(self.meta),
        }


@dataclass
class AppGenerationService:
    """Gate SurfaceGenerator calls by manifest + compositor ownership."""

    lifecycle: AppLifecycle
    provider: SurfaceGenerator | None = None
    history: list[AppGenerationRecord] = field(default_factory=list)
    last_good: dict[tuple[str, str], SurfaceRenderResult] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.provider is None:
            self.provider = NullSurfaceGenerator()

    @property
    def provider_id(self) -> str:
        name = type(self.provider).__name__ if self.provider else "null"
        if isinstance(self.provider, NullSurfaceGenerator):
            return "null"
        return name

    def set_provider(self, provider: SurfaceGenerator | None) -> None:
        self.provider = provider or NullSurfaceGenerator()

    def request(
        self,
        app_id: str,
        surface_key: str,
        *,
        width: int = 64,
        height: int = 48,
        workflow: dict[str, Any] | None = None,
        routing: dict[str, Any] | None = None,
        raise_on_deny: bool = True,
    ) -> AppGenerationRecord:
        """Request generation for one fitted surface key owned/overlaid by the app."""
        record = self.lifecycle.get(app_id)
        if record is None:
            return self._deny(
                app_id, surface_key, "unknown_app", raise_on_deny=raise_on_deny
            )
        if not bool(record.manifest.get("generation")):
            return self._deny(
                app_id,
                surface_key,
                "generation_not_declared",
                raise_on_deny=raise_on_deny,
            )
        if record.state != AppState.RUNNING:
            return self._deny(
                app_id, surface_key, "not_running", raise_on_deny=raise_on_deny
            )
        if record.fit is None or surface_key not in record.fit.bindings:
            return self._deny(
                app_id, surface_key, "unknown_surface_key", raise_on_deny=raise_on_deny
            )
        binding = record.fit.bindings[surface_key]
        sid = binding.surface_id
        if sid is None:
            return self._deny(
                app_id, surface_key, "surface_unbound", raise_on_deny=raise_on_deny
            )
        if not self.lifecycle.compositor.app_controls_surface(app_id, sid):
            return self._deny(
                app_id,
                surface_key,
                "surface_not_owned",
                surface_id=sid,
                raise_on_deny=raise_on_deny,
            )

        provider = self.provider or NullSurfaceGenerator()
        job_id = f"appgen_{uuid.uuid4().hex[:12]}"
        role = binding.role_requested
        roles = binding.roles
        if roles:
            # Prefer a concrete role label when available.
            for r in roles:
                if r == "floor" or r.startswith("wall"):
                    role = r
                    break
        request = SurfaceRenderRequest(
            surface=SurfaceTarget(
                role=str(role),
                surface_id=int(sid),
                width=int(width),
                height=int(height),
            ),
            routing=dict(
                routing
                or {
                    "mode": "direct",
                    "provider": self.provider_id,
                }
            ),
            workflow={"inline": dict(workflow or {"1": {"class_type": "EmptyImage"}})},
            client={
                "app_id": app_id,
                "client_id": f"lumur_app_{app_id}",
                "request_id": job_id,
            },
            refs={"surface_key": surface_key},
        )
        result = provider.generate(request)
        status = (
            result.status.value
            if isinstance(result.status, JobStatus)
            else str(result.status)
        )
        entry = AppGenerationRecord(
            app_id=app_id,
            surface_key=surface_key,
            surface_id=int(sid),
            status=status,
            provider=self.provider_id,
            job_id=result.job_id or job_id,
            meta={
                "result_meta": dict(result.meta or {}),
                "layer": (
                    self.lifecycle.compositor.claims_by_app[app_id][int(sid)].layer
                ),
            },
        )
        if result.status in (JobStatus.SUCCEEDED, JobStatus.SKIPPED):
            self.last_good[(app_id, surface_key)] = result
        self.history.append(entry)
        return entry

    def last_good_for(self, app_id: str, surface_key: str) -> SurfaceRenderResult | None:
        return self.last_good.get((app_id, surface_key))

    def _deny(
        self,
        app_id: str,
        surface_key: str,
        reason: str,
        *,
        surface_id: int | None = None,
        raise_on_deny: bool,
    ) -> AppGenerationRecord:
        entry = AppGenerationRecord(
            app_id=app_id,
            surface_key=surface_key,
            surface_id=surface_id,
            status="denied",
            provider=self.provider_id,
            denied_reason=reason,
        )
        self.history.append(entry)
        if raise_on_deny:
            raise GenerationDenied(
                f"generation denied for {app_id!r} key={surface_key!r}: {reason}",
                reason=reason,
            )
        return entry


def bundled_app_roots(repo_root: str | Path) -> list[Path]:
    """Core bundled app search roots (never includes the Synesyn bridge)."""
    root = Path(repo_root)
    return [root / "apps" / "ripples", root / "apps" / "paint", root / "apps"]


def bridge_app_roots(repo_root: str | Path) -> list[Path]:
    """Optional bridge-hosted app packages (Story Stage)."""
    root = Path(repo_root)
    return [root / "addons" / "lumur_synesyn" / "apps"]
