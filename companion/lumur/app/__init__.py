"""App-layer helpers: manifests, room services, fit, input bus, compositor, lifecycle (PRD-003)."""

from lumur.app.compositor import (
    CompositeFrame,
    Compositor,
    CompositorError,
    OwnershipEntry,
    SurfaceClaim,
    TransitionRecord,
)
from lumur.app.fit import (
    FitError,
    FitResult,
    SurfaceBinding,
    UnmetSurface,
    fit_app_to_room,
)
from lumur.app.generation import (
    AppGenerationRecord,
    AppGenerationService,
    GenerationDenied,
    bridge_app_roots,
    bundled_app_roots,
)
from lumur.app.input_bus import (
    AppInputBus,
    AppInputSession,
    RefusedSubscription,
)
from lumur.app.launcher import Launcher
from lumur.app.lifecycle import AppLifecycle, AppRecord, AppState, LifecycleError
from lumur.app.room_services import RoomServices, SurfaceRecord
from lumur.app.zone_switch import ZoneAppSwitcher, ZoneSwitchConfig
from lumur.schema.app import (
    KNOWN_INPUTS,
    MANIFEST_FILENAME,
    SCHEMA_ID as APP_SCHEMA_ID,
    SCHEMA_VERSION as APP_SCHEMA_VERSION,
    build_app_manifest,
    load_app_manifest,
    save_app_manifest,
    validate_app_manifest,
)

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
