# 0011 — Simulated projector–camera rig for hardware-free development

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** calibration / companion / testing
- **Relates to:** ADR 0003, ADR 0004, ADR 0010; PRD-001

## Context

The companion's first slice is Gray-code capture, decode, and calibration
against a real webcam and projector ([ADR 0010](0010-opencv-fullscreen-pattern-display.md)).
Physical hardware is not always available: agents and contributors need a
repeatable, headless path that exercises the same capture loop and produces
ground truth for residuals, intrinsics, pose, and correspondence. Later
PRD-001 work (confidence-filtered room scan, paint-the-room, predicted-frame
subtraction, footstep ripples) will also need a virtual room that can grow
occluders and figures without waiting on a lab setup.

## Options considered

1. **Keep only the thin synthetic helpers under `tests/synthetic/`.** Fast for
   unit tests, but not a device backend, not a configurable room, and not
   reusable by the CLI or future scan / paint paths.
2. **Recorded fixture videos + still patterns.** Replays one capture; cannot
   generate new projector images, change poses, or assert against true depth.
3. **A first-class `lumur.sim` package** with a virtual room, projector, and
   webcam that implement the same `PatternDisplay` / `FrameSource` protocols
   as OpenCV, plus scene files and ground-truth buffers.

## Decision

Option 3. Introduce `companion/lumur/sim/` and a small device backend factory
(`open_devices(backend="opencv"|"sim")`). The simulated display and camera
are drop-in replacements for `OpenCVFullscreenDisplay` and `OpenCVCamera`.
Scenes are JSON (YAML optional). Presets ship for an empty room, a room with
a box and a static occupant placeholder, and a noisy / ambient stress case.
The sim exposes ground-truth intrinsics, extrinsics, depth, and
correspondences. Pose estimation of people is explicitly out of scope here;
occupant placeholders exist so later PRD-001 features can hang animated
figures / occluders on the same room model.

## Consequences

- Positive: calibration development and CI proceed without hardware; e2e
  tests assert decode accuracy and pose / residual tolerances against GT.
- Positive: CLI gains `--backend sim --scene <path|preset>` without changing
  the OpenCV default path.
- Positive: future scan, paint, subtraction, and ripple work can reuse the
  same room and projective renderer.
- Trade-off: the transport model is diffuse + gamma + noise/blur only; it is
  not a radiometric twin of a real projector–camera pair.
- Follow-up: when predicted-frame subtraction (ADR 0005) lands, drive it from
  this renderer so the subtracted frame matches the virtual projector image.
