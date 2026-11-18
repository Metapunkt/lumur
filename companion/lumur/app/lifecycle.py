"""App install / launch / pause / resume / switch / stop (PRD-003 slice 3).

Observable state machine against a loaded room package. Input-bus delivery
follows lifecycle: paused and stopped apps receive no room events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from lumur.app.compositor import Compositor, CompositorError
from lumur.app.fit import FitError, FitResult, fit_app_to_room
from lumur.app.input_bus import AppInputBus
from lumur.app.room_services import RoomServices
from lumur.schema.app import (
    MANIFEST_FILENAME,
    load_app_manifest,
    validate_app_manifest,
)


class AppState(str, Enum):
    INSTALLED = "installed"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class AppRecord:
    """One installed / launched app and its observable lifecycle state."""

    app_id: str
    manifest: dict[str, Any]
    path: Path | None = None
    state: AppState = AppState.INSTALLED
    fit: FitResult | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "name": self.manifest.get("name"),
            "version": self.manifest.get("version"),
            "state": self.state.value,
            "path": str(self.path) if self.path else None,
            "fit": self.fit.to_dict() if self.fit else None,
            "last_error": self.last_error,
            "shares": list(self.manifest.get("shares") or []),
            "inputs": list(self.manifest.get("inputs") or []),
        }


class LifecycleError(ValueError):
    def __init__(self, message: str, *, reason: str = "lifecycle"):
        super().__init__(message)
        self.reason = reason


@dataclass
class AppLifecycle:
    """Runtime host for app packages against one room + compositor + input bus."""

    room: RoomServices
    compositor: Compositor
    input_bus: AppInputBus
    apps: dict[str, AppRecord] = field(default_factory=dict)
    foreground_app_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, room: RoomServices) -> AppLifecycle:
        compositor = Compositor(room=room)
        bus = AppInputBus()
        return cls(room=room, compositor=compositor, input_bus=bus)

    def install(
        self,
        source: str | Path | Mapping[str, Any],
        *,
        path: str | Path | None = None,
    ) -> AppRecord:
        """Discover/register a manifest (+ optional package path)."""
        if isinstance(source, (str, Path)):
            manifest_path = Path(source)
            if manifest_path.is_dir():
                manifest_path = manifest_path / MANIFEST_FILENAME
            manifest = load_app_manifest(manifest_path)
            path = path or manifest_path
        else:
            manifest = dict(source)
            validate_app_manifest(manifest)
            path = Path(path) if path else None

        app_id = str(manifest["id"])
        # Bridge-only apps may install; launcher filters display separately.
        record = AppRecord(
            app_id=app_id,
            manifest=manifest,
            path=Path(path) if path else None,
            state=AppState.INSTALLED,
        )
        self.apps[app_id] = record
        self._log("install", app_id)
        return record

    def get(self, app_id: str) -> AppRecord | None:
        return self.apps.get(app_id)

    def states(self) -> dict[str, str]:
        return {aid: rec.state.value for aid, rec in self.apps.items()}

    def launch(
        self,
        app_id: str,
        *,
        as_overlay: bool = False,
        make_foreground: bool = True,
    ) -> AppRecord:
        """Fit + claim surfaces + register input session; state → running."""
        record = self._require(app_id)
        if record.state == AppState.RUNNING:
            return record
        if record.state == AppState.PAUSED:
            return self.resume(app_id)

        shares = list(record.manifest.get("shares") or [])
        owned = self.compositor.exclusive_owned_ids()
        try:
            fit = fit_app_to_room(
                record.manifest,
                self.room,
                exclusive_owned=owned,
                share_keys=set(shares),
                raise_on_unmet=True,
            )
        except FitError as exc:
            record.last_error = str(exc)
            self._log("launch_failed", app_id, reason="unmet_surface")
            raise LifecycleError(
                f"launch failed for {app_id}: {exc}", reason="unmet_surface"
            ) from exc

        try:
            self.compositor.claim_from_fit(
                app_id, fit, shares=shares, as_overlay=as_overlay
            )
        except CompositorError as exc:
            record.last_error = str(exc)
            self._log("launch_failed", app_id, reason=exc.reason)
            raise LifecycleError(
                f"launch conflict for {app_id}: {exc}", reason=exc.reason
            ) from exc

        record.fit = fit
        record.state = AppState.RUNNING
        record.last_error = None

        session = self.input_bus.register_app(record.manifest, fit=fit)
        session.paused = False
        for ev_type in record.manifest.get("inputs") or []:
            self.input_bus.subscribe(app_id, str(ev_type))

        if make_foreground:
            prev = self.foreground_app_id
            self.foreground_app_id = app_id
            self.compositor.switch_handoff(prev, app_id, reason="launch")

        self._log("launch", app_id)
        return record

    def pause(self, app_id: str) -> AppRecord:
        record = self._require(app_id)
        if record.state != AppState.RUNNING:
            raise LifecycleError(
                f"cannot pause {app_id} in state {record.state.value}",
                reason="invalid_state",
            )
        self.compositor.pause_handoff(app_id)
        session = self.input_bus.get(app_id)
        if session is not None:
            session.paused = True
        record.state = AppState.PAUSED
        if self.foreground_app_id == app_id:
            self.foreground_app_id = None
        self._log("pause", app_id)
        return record

    def resume(self, app_id: str, *, make_foreground: bool = True) -> AppRecord:
        record = self._require(app_id)
        if record.state == AppState.RUNNING:
            return record
        if record.state not in (AppState.PAUSED, AppState.INSTALLED, AppState.STOPPED):
            raise LifecycleError(
                f"cannot resume {app_id} in state {record.state.value}",
                reason="invalid_state",
            )
        if record.state != AppState.PAUSED:
            # Treat as fresh launch.
            return self.launch(app_id, make_foreground=make_foreground)

        # Re-claim surfaces (may conflict if another app took them).
        shares = list(record.manifest.get("shares") or [])
        owned = self.compositor.exclusive_owned_ids()
        try:
            fit = fit_app_to_room(
                record.manifest,
                self.room,
                exclusive_owned=owned,
                share_keys=set(shares),
                raise_on_unmet=True,
            )
        except FitError as exc:
            record.last_error = str(exc)
            raise LifecycleError(
                f"resume failed for {app_id}: {exc}", reason="unmet_surface"
            ) from exc

        try:
            self.compositor.claim_from_fit(app_id, fit, shares=shares)
        except CompositorError as exc:
            record.last_error = str(exc)
            raise LifecycleError(
                f"resume conflict for {app_id}: {exc}", reason=exc.reason
            ) from exc

        record.fit = fit
        record.state = AppState.RUNNING
        session = self.input_bus.get(app_id)
        if session is None:
            session = self.input_bus.register_app(record.manifest, fit=fit)
            for ev_type in record.manifest.get("inputs") or []:
                self.input_bus.subscribe(app_id, str(ev_type))
        else:
            session.bindings = dict(fit.bindings)
            session.paused = False

        if make_foreground:
            prev = self.foreground_app_id
            self.foreground_app_id = app_id
            self.compositor.switch_handoff(prev, app_id, reason="resume")

        self._log("resume", app_id)
        return record

    def stop(self, app_id: str) -> AppRecord:
        record = self._require(app_id)
        if record.state in (AppState.RUNNING, AppState.PAUSED):
            self.compositor.release(app_id, reason="stop")
        self.input_bus.unregister(app_id)
        record.state = AppState.STOPPED
        record.fit = None
        if self.foreground_app_id == app_id:
            self.foreground_app_id = None
        self._log("stop", app_id)
        return record

    def switch(self, app_id: str) -> AppRecord:
        """Pause current foreground (if any) and launch/resume ``app_id``."""
        current = self.foreground_app_id
        if current == app_id:
            record = self._require(app_id)
            if record.state == AppState.RUNNING:
                return record
        if current is not None and current in self.apps:
            cur = self.apps[current]
            if cur.state == AppState.RUNNING:
                self.pause(current)
        record = self.apps.get(app_id)
        if record is None:
            raise LifecycleError(f"unknown app {app_id!r}", reason="unknown_app")
        if record.state == AppState.PAUSED:
            return self.resume(app_id, make_foreground=True)
        if record.state == AppState.RUNNING:
            self.foreground_app_id = app_id
            return record
        return self.launch(app_id, make_foreground=True)

    def _require(self, app_id: str) -> AppRecord:
        record = self.apps.get(app_id)
        if record is None:
            raise LifecycleError(f"unknown app {app_id!r}", reason="unknown_app")
        return record

    def _log(self, action: str, app_id: str, **extra: Any) -> None:
        entry = {"action": action, "app_id": app_id, **extra}
        self.history.append(entry)
