# 0004 — Godot 4 addon with a small Python companion

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** runtime / packaging
- **Relates to:** ADR 0006, ADR 0008, ADR 0009

## Context

Lumur has two different kinds of work. Calibration, structured-light
decoding and (later) pose run well in a small Python and OpenCV process.
Continuous projection, surface coordinates, effects and apps run well in
Godot. Putting either kind of work in the wrong place would bloat both.

The exact Godot 4 minor version is still open.

## Options considered

1. **Everything in GDScript (or a GDExtension from the start).** One
   process; calibration and CV would be rewritten or embedded before the
   first milestone had a picture on the wall.
2. **Everything in Python, with Godot only as a display client.** Makes
   the engine incidental, and fights the plan that experiences are Godot
   scenes.
3. **A Godot 4 addon plus a small Python/OpenCV companion.** A narrow
   boundary between them. Either side can be replaced later.

## Decision

Option 3. The companion owns capture, calibration and scan. Godot owns
rendering, the room runtime and apps. The boundary is kept minimal:

- JSON for configuration and events;
- a mesh or correspondence file for geometry;
- a local socket for live events.

The renderer must run without the companion's inference path, and without
ComfyUI, on its critical path. Whether calibration later moves into a
GDExtension remains an open question; it is not a requirement for the
first milestone.

## Consequences

- Positive: each side uses tools it is already good at; the first scan
  and the first shader do not block each other.
- Trade-off: two processes to run, version and diagnose.
- Follow-up: document the on-disk room package and the socket event
  schema once they exist, as implementation contracts, not as a second
  copy of this decision.
