from lumur.schema.app import (
    SCHEMA_ID as APP_SCHEMA_ID,
    SCHEMA_VERSION as APP_SCHEMA_VERSION,
    build_app_manifest,
    load_app_manifest,
    save_app_manifest,
    validate_app_manifest,
)
from lumur.schema.calibration import (
    SCHEMA_VERSION as CALIBRATION_SCHEMA_VERSION,
    build_calibration_document,
    load_calibration,
    save_calibration,
    validate_calibration_document,
)
from lumur.schema.room import (
    SCHEMA_VERSION as ROOM_SCHEMA_VERSION,
    build_room_document,
    load_room_package,
    save_room_package,
    validate_room_document,
)

# Back-compat: SCHEMA_VERSION refers to the calibration schema.
SCHEMA_VERSION = CALIBRATION_SCHEMA_VERSION

__all__ = [
    "SCHEMA_VERSION",
    "CALIBRATION_SCHEMA_VERSION",
    "ROOM_SCHEMA_VERSION",
    "APP_SCHEMA_ID",
    "APP_SCHEMA_VERSION",
    "build_calibration_document",
    "load_calibration",
    "save_calibration",
    "validate_calibration_document",
    "build_room_document",
    "load_room_package",
    "save_room_package",
    "validate_room_document",
    "build_app_manifest",
    "load_app_manifest",
    "save_app_manifest",
    "validate_app_manifest",
]