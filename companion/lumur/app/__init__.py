"""App-layer helpers: manifests, room services, fit, input bus, compositor, lifecycle (PRD-003).

Imports are lazy so leaf modules such as ``lumur.app.metrics`` can load without
pulling ``room_services`` / ``paint.export`` (avoids circular imports).
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "APP_SCHEMA_ID",
    "APP_SCHEMA_VERSION",
    "KNOWN_INPUTS",
    "MANIFEST_FILENAME",
    "AppGenerationRecord",
    "AppGenerationService",
    "AppInputBus",
    "AppInputSession",
    "AppLifecycle",
    "AppRecord",
    "AppState",
    "CompositeFrame",
    "Compositor",
    "CompositorError",
    "FitError",
    "FitResult",
    "GenerationDenied",
    "Launcher",
    "LifecycleError",
    "OwnershipEntry",
    "RefusedSubscription",
    "RoomServices",
    "SurfaceBinding",
    "SurfaceClaim",
    "SurfaceRecord",
    "TransitionRecord",
    "UnmetSurface",
    "ZoneAppSwitcher",
    "ZoneSwitchConfig",
    "bridge_app_roots",
    "build_app_manifest",
    "bundled_app_roots",
    "fit_app_to_room",
    "load_app_manifest",
    "save_app_manifest",
    "validate_app_manifest",
]

_LAZY: dict[str, tuple[str, str]] = {
    "APP_SCHEMA_ID": ("lumur.schema.app", "SCHEMA_ID"),
    "APP_SCHEMA_VERSION": ("lumur.schema.app", "SCHEMA_VERSION"),
    "KNOWN_INPUTS": ("lumur.schema.app", "KNOWN_INPUTS"),
    "MANIFEST_FILENAME": ("lumur.schema.app", "MANIFEST_FILENAME"),
    "build_app_manifest": ("lumur.schema.app", "build_app_manifest"),
    "load_app_manifest": ("lumur.schema.app", "load_app_manifest"),
    "save_app_manifest": ("lumur.schema.app", "save_app_manifest"),
    "validate_app_manifest": ("lumur.schema.app", "validate_app_manifest"),
    "AppGenerationRecord": ("lumur.app.generation", "AppGenerationRecord"),
    "AppGenerationService": ("lumur.app.generation", "AppGenerationService"),
    "GenerationDenied": ("lumur.app.generation", "GenerationDenied"),
    "bridge_app_roots": ("lumur.app.generation", "bridge_app_roots"),
    "bundled_app_roots": ("lumur.app.generation", "bundled_app_roots"),
    "AppInputBus": ("lumur.app.input_bus", "AppInputBus"),
    "AppInputSession": ("lumur.app.input_bus", "AppInputSession"),
    "RefusedSubscription": ("lumur.app.input_bus", "RefusedSubscription"),
    "AppLifecycle": ("lumur.app.lifecycle", "AppLifecycle"),
    "AppRecord": ("lumur.app.lifecycle", "AppRecord"),
    "AppState": ("lumur.app.lifecycle", "AppState"),
    "LifecycleError": ("lumur.app.lifecycle", "LifecycleError"),
    "CompositeFrame": ("lumur.app.compositor", "CompositeFrame"),
    "Compositor": ("lumur.app.compositor", "Compositor"),
    "CompositorError": ("lumur.app.compositor", "CompositorError"),
    "OwnershipEntry": ("lumur.app.compositor", "OwnershipEntry"),
    "SurfaceClaim": ("lumur.app.compositor", "SurfaceClaim"),
    "TransitionRecord": ("lumur.app.compositor", "TransitionRecord"),
    "FitError": ("lumur.app.fit", "FitError"),
    "FitResult": ("lumur.app.fit", "FitResult"),
    "SurfaceBinding": ("lumur.app.fit", "SurfaceBinding"),
    "UnmetSurface": ("lumur.app.fit", "UnmetSurface"),
    "fit_app_to_room": ("lumur.app.fit", "fit_app_to_room"),
    "Launcher": ("lumur.app.launcher", "Launcher"),
    "RoomServices": ("lumur.app.room_services", "RoomServices"),
    "SurfaceRecord": ("lumur.app.room_services", "SurfaceRecord"),
    "ZoneAppSwitcher": ("lumur.app.zone_switch", "ZoneAppSwitcher"),
    "ZoneSwitchConfig": ("lumur.app.zone_switch", "ZoneSwitchConfig"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    import importlib

    module = importlib.import_module(module_name)
    value = getattr(module, attr)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
