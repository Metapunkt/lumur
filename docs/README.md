# Lumur documentation

Pick the documentation pathway that best describes your needs.

## I want to understand the project

- [Scratchpad](scratchpad.md) — the founding brainstorm, dated 2026-11-18,
  including the naming journey and open questions.
- [Product requirements](product-requirements/README.md) — what each
  milestone must do, and how success is measured ([PRD-001](product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md)
  and [PRD-002](product-requirements/PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md)
  complete-in-sim; [PRD-003](product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
  draft: application layer).
- [Architectural decisions](architectural-decisions/README.md) — why it is
  built this way. Append-only, including the decisions we reverse.

## Why it is the way it is

Reference material both audiences reach for eventually.

| Where | Question it answers |
| --- | --- |
| [Scratchpad](scratchpad.md) | What was considered, and what remains open? |
| [Product requirements](product-requirements/README.md) | What problem is this solving, and how is success measured? |
| [Architectural decisions](architectural-decisions/README.md) | Why is it built this way? Append-only, including the decisions we reversed. |

Companion calibration (Gray-code driver, JSON schema, live webcam/projector
runbook): [companion/calibration.md](companion/calibration.md).

Simulated projector–camera rig (hardware-free capture / calibration,
scene format, limits): [companion/simulation.md](companion/simulation.md).

Room scan (triangulation, confidence, planes, room package schema):
[companion/room-scan.md](companion/room-scan.md).

Godot paint-the-room mode (addon, surface targets, headless render):
[godot/paint-mode.md](godot/paint-mode.md).

Tracking / footsteps (pose, subtraction mask, UDP events):
[companion/tracking.md](companion/tracking.md).

Footstep ripples in Godot:
[godot/ripples.md](godot/ripples.md).

Standalone ComfyUI surface generation (no Synesyn):
[companion/comfyui.md](companion/comfyui.md).

Optional Synesyn Hub bridge (`lumur_synesyn`, PRD-002 slice 2):
[bridge/synesyn.md](bridge/synesyn.md).

Story Stage layers on room surfaces (PRD-002 slice 3):
[bridge/story-stage.md](bridge/story-stage.md).

Opt-in audience steering (PRD-002 slice 4):
[bridge/audience-steering.md](bridge/audience-steering.md).

Session / Story Log replay (PRD-002 slice 4):
[bridge/replay.md](bridge/replay.md).

Application layer (PRD-003; slice 1 = manifest + room fit):
[PRD-003](product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md),
[apps/manifest.md](apps/manifest.md),
[ADR 0017](architectural-decisions/0017-app-manifest-format.md) (Accepted),
[ADR 0018](architectural-decisions/0018-surface-allocation-and-compositing.md),
[ADR 0019](architectural-decisions/0019-app-input-permissions.md).

## Credit and licence

© 2026 “Lumur” by Ayodele Arigbabu

This documentation is [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The source code is MIT. See [`LICENSE`](../LICENSE).
