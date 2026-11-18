# Lumur Architectural Decision Records (ADRs)

This directory is the append-only record of non-trivial architecture and design
decisions. ADRs explain why the system is taking a particular shape. Current
operating guidance will belong in a developer guide, once there is one, and
normative behaviour in implementation contracts, once those exist.

To reverse a decision, add a new ADR and mark the old one `Superseded by NNNN`.
Do not edit a decision away. A later amendment note may clarify wording or a
moved path, but the decision itself stands until a successor replaces it.

| # | Title | Status | Date |
|---|-------|--------|------|
| [0001](0001-adopt-architecture-decision-records.md) | Adopt Architecture Decision Records | Accepted | 2026-11-18 |
| [0002](0002-spiritual-successor-not-a-port.md) | A spiritual successor to RoomAlive, not a port | Accepted | 2026-11-18 |
| [0003](0003-projector-as-depth-sensor.md) | The projector is the depth sensor; geometry decides where | Accepted | 2026-11-18 |
| [0004](0004-godot-addon-and-python-companion.md) | Godot 4 addon with a small Python companion | Accepted | 2026-11-18 |
| [0005](0005-pose-and-predicted-frame-subtraction.md) | Pose on the raw frame, subtraction as a mask | Accepted | 2026-11-18 |
| [0006](0006-room-as-os-runtime.md) | Lumur is a runtime for rooms | Accepted (refined by 0017–0019) | 2026-11-18 |
| [0007](0007-lumur-os-as-appliance.md) | Lumur OS is a later appliance image, not a custom kernel | Proposed | 2026-11-18 |
| [0008](0008-comfyui-asynchronous.md) | ComfyUI sits beside the renderer, never on its critical path | Accepted (refined by 0016) | 2026-11-18 |
| [0009](0009-standalone-with-synesyn-bridge.md) | Lumur stays standalone; Synesyn integrates through a thin bridge | Accepted | 2026-11-18 |
| [0010](0010-opencv-fullscreen-pattern-display.md) | OpenCV fullscreen for calibration pattern display | Accepted | 2026-11-18 |
| [0011](0011-simulated-projector-camera-rig.md) | Simulated projector–camera rig for hardware-free development | Accepted | 2026-11-18 |
| [0012](0012-versioned-room-package.md) | Versioned room package for scan output | Accepted | 2026-11-18 |
| [0013](0013-godot-paint-asset-export.md) | Godot paint assets exported as PNG + JSON | Accepted | 2026-11-18 |
| [0014](0014-udp-json-event-transport.md) | Local UDP JSON for companion → Godot events | Accepted (refined by 0019) | 2026-11-18 |
| [0015](0015-single-lumur-synesyn-bridge.md) | Single `lumur_synesyn` bridge for Synesyn integration (render + Story Stage) | Accepted | 2026-11-18 |
| [0016](0016-pluggable-surface-generators.md) | Pluggable surface generators; ComfyUI with or without Synesyn | Accepted | 2026-11-18 |
| [0017](0017-app-manifest-format.md) | App manifest format and versioning (`lumur.app`) | Accepted | 2026-11-18 |
| [0018](0018-surface-allocation-and-compositing.md) | Surface allocation and compositing rules | Proposed | 2026-11-18 |
| [0019](0019-app-input-permissions.md) | Per-app input permissions for room events | Accepted | 2026-11-18 |
