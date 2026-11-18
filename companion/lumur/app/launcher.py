"""Headless app launcher (PRD-003 REQ-003-012).

Discovers ``lumur.app.json`` packages, lists installed apps, and starts one
through :class:`AppLifecycle`. On-projector UI is optional; this API is
required for complete-in-sim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lumur.app.lifecycle import AppLifecycle, AppRecord, AppState, LifecycleError
from lumur.schema.app import MANIFEST_FILENAME


@dataclass
class Launcher:
    """Simple launcher over an :class:`AppLifecycle` host."""

    lifecycle: AppLifecycle
    search_paths: list[Path] = field(default_factory=list)
    require_bridge: bool = False  # when False, skip bridge-only apps in list_startable

    def discover(self, *roots: str | Path) -> list[AppRecord]:
        """Find ``lumur.app.json`` under each root and install them."""
        found: list[AppRecord] = []
        for root in roots:
            root_path = Path(root)
            self.search_paths.append(root_path)
            if not root_path.exists():
                continue
            manifests = sorted(root_path.rglob(MANIFEST_FILENAME))
            for path in manifests:
                try:
                    record = self.lifecycle.install(path)
                except (ValueError, OSError):
                    continue
                found.append(record)
        return found

    def install_path(self, path: str | Path) -> AppRecord:
        return self.lifecycle.install(path)

    def list_installed(self) -> list[dict[str, Any]]:
        """All registered apps with observable state."""
        return [rec.to_dict() for rec in self.lifecycle.apps.values()]

    def list_startable(self) -> list[dict[str, Any]]:
        """Installed apps the launcher may start (core by default).

        Apps with a non-null manifest ``bridge`` field are omitted unless
        ``require_bridge`` is True — keeps bridge-hosted apps optional
        (REQ-003-016 posture for slice 3 listing; full packaging is slice 4).
        """
        out: list[dict[str, Any]] = []
        for rec in self.lifecycle.apps.values():
            bridge = rec.manifest.get("bridge")
            if bridge and not self.require_bridge:
                continue
            out.append(rec.to_dict())
        return out

    def start(self, app_id: str) -> AppRecord:
        """Start one app (launch or switch-to-foreground)."""
        if app_id not in self.lifecycle.apps:
            raise LifecycleError(f"unknown app {app_id!r}", reason="unknown_app")
        if self.lifecycle.foreground_app_id and self.lifecycle.foreground_app_id != app_id:
            return self.lifecycle.switch(app_id)
        record = self.lifecycle.apps[app_id]
        if record.state == AppState.PAUSED:
            return self.lifecycle.resume(app_id)
        if record.state == AppState.RUNNING:
            self.lifecycle.foreground_app_id = app_id
            return record
        return self.lifecycle.launch(app_id)

    def stop(self, app_id: str) -> AppRecord:
        return self.lifecycle.stop(app_id)

    def pause(self, app_id: str) -> AppRecord:
        return self.lifecycle.pause(app_id)
