# 0006 — Lumur is a runtime for rooms

- **Status:** Accepted (refined by [ADR 0017](0017-app-manifest-format.md),
  [ADR 0018](0018-surface-allocation-and-compositing.md),
  [ADR 0019](0019-app-input-permissions.md))
- **Date:** 2026-11-18
- **Area:** runtime / product
- **Relates to:** ADR 0004, ADR 0007, ADR 0009, ADR 0017, ADR 0018, ADR 0019

## Context

Once calibration and a room scan exist, the question is what software
shape sits on top of them. A bag of demo scenes would work for a weekend
prototype and would not travel between rooms. A heavy “operating system”
metaphor — window managers, permission systems, app stores — would
postpone the first beautiful projection.

The useful idea in “Lumur OS” is that the room is a computer: devices,
a file system, input events, a display, and apps that target surfaces
rather than coordinates.

## Options considered

1. **A toolkit of calibration scripts and demo scenes.** Fastest path to
   a picture; every experience hard-codes one room.
2. **A full OS metaphor from day one**, including a multi-app compositor,
   permissions and packaging policy. The name would be literal early;
   almost none of it helps the first app.
3. **A small room runtime.** Provide the boundaries an OS would provide,
   and implement only what the next app needs. One app first.

## Decision

Option 3. Lumur is a runtime for rooms. In principle it provides:

- **Devices.** Cameras and projectors, with calibration as their driver.
  Apps do not call OpenCV.
- **A room package, as a file system.** Measured geometry and confidence,
  calibration, named surfaces, exclusions, interaction zones, and later
  an adjacency graph between surfaces. Apps ask for “the floor” or “is
  the doorway clear?”.
- **Input events.** Footstep, hover, presence, enter and leave zone.
  Apps subscribe; they do not own the pose model.
- **A display server.** Lumur owns the projector output. Compositing
  several apps onto different surfaces is deferred until more than one
  app needs it.
- **Apps as Godot scenes**, each with a small manifest declaring the
  surfaces it needs. Lumur binds those names to the current room.

Portability is a goal of the model: an app authored in one room should
install in another by retargeting surfaces, not by rewriting coordinates.
The first release still proves the model with a single app, run
beautifully.

## Consequences

- Positive: clean seams for later work (ComfyUI, Synesyn, a second app)
  without building a platform nobody can fill.
- Positive: graceful degradation is expressible — if tracking fails, the
  display server can still show a mapped artwork.
- Trade-off: the runtime must stay small. New platform machinery is
  justified only by a real app that needs it.
- Follow-up: the appliance image that would make the “OS” literal is a
  separate, later proposal (ADR 0007).
