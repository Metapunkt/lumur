# Lumur documentation

Pick the documentation pathway that best describes your needs.

## I want to understand the project

Lumur is in design phase; there is no software to install yet.

- [Scratchpad](scratchpad.md) — the founding brainstorm, dated 2026-11-18,
  including the naming journey and open questions.
- [Product requirements](product-requirements/README.md) — what the first
  milestone must do, and how success is measured.
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

Further user guides, a developer guide, and implementation contracts will
appear here as the runtime grows.

## Credit and licence

© 2026 “Lumur” by Ayodele Arigbabu

This documentation is [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The source code is MIT. See [`LICENSE`](../LICENSE).
