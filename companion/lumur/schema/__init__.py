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
    "build_calibration_document",
    "load_calibration",
    "save_calibration",
    "validate_calibration_document",
    "build_room_document",
    "load_room_package",
    "save_room_package",
    "validate_room_document",
]