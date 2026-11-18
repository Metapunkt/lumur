# 0010 — OpenCV fullscreen for calibration pattern display

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** calibration / companion
- **Relates to:** ADR 0003, ADR 0004

## Context

The calibration driver must project Gray-code patterns onto the room while
the webcam captures. [ADR 0004](0004-godot-addon-and-python-companion.md)
keeps the companion responsible for capture and calibration, and Godot
responsible for the runtime renderer. The first calibration slice has no
Godot addon yet, but still needs a reliable fullscreen path the companion
can drive.

## Options considered

1. **Godot window as the pattern sink.** Matches the eventual projector
   output path, but couples the first calibration slice to a Godot project,
   IPC, and a second process before any JSON exists.
2. **A local HTTP page or OS slideshow.** Works, but adds a browser or
   window manager choreography around what is already an OpenCV pipeline.
3. **OpenCV `namedWindow` + fullscreen.** Same process as pattern
   generation and capture; minimal dependencies; good enough multi-monitor
   placement via `moveWindow` before entering fullscreen.

## Decision

Option 3 for the calibration driver. Patterns are shown with
`OpenCVFullscreenDisplay` in the companion. Godot remains the authority
for interactive projection once the addon exists; calibration does not
wait on it.

## Consequences

- Positive: `lumur-calibrate` is a single Python process an installer can
  run against a real webcam and projector.
- Positive: synthetic tests stay headless by swapping in `NullDisplay`.
- Trade-off: multi-monitor targeting is best-effort and backend-dependent;
  installers may need to pass `--monitor` or arrange the OS display layout.
- Follow-up: a later ADR may move pattern display into Godot if shared
  radiometric prediction (ADR 0005) needs an identical output path.