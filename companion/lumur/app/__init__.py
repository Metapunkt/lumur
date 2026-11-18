"""App-layer helpers: manifests, room services, fit, and input bus (PRD-003)."""

from lumur.app.fit import (
    FitError,
    FitResult,
    SurfaceBinding,
    UnmetSurface,
    fit_app_to_room,
)
from lumur.app.input_bus import (
    AppInputBus,
    AppInputSession,
    RefusedSubscription,
)
from lumur.app.room_services import RoomServices, SurfaceRecord
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
    "AppInputBus",
    "AppInputSession",
    "FitError",
    "FitResult",
    "RefusedSubscription",
    "RoomServices",
    "SurfaceBinding",
    "SurfaceRecord",
    "UnmetSurface",
    "build_app_manifest",
    "fit_app_to_room",
    "load_app_manifest",
    "save_app_manifest",
    "validate_app_manifest",
]
