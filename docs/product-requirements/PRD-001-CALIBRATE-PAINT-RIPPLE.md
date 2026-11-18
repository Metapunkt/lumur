---
id: PRD-001
title: Calibrate, paint the room, and footstep ripples
status: draft
version: "0.1"
owner: Ayodele Arigbabu
last_reviewed: 2026-11-18
primary_users: [installer, author, visitor]
supersedes: null
---

# Calibrate, paint the room, and footstep ripples

## Problem and outcome

A room with a webcam and a projector should become a mapped, paintable,
lightly interactive surface without a Kinect or other specialised depth
camera, and without waiting for a 3D authoring pipeline. The first
milestone should take someone from an uncalibrated camera–projector pair
to two visible results: they can paint the room through the
correspondence the scan already produced, and walking on the floor makes
ripples. If tracking or generation is absent, the projection should
remain a mapped artwork.

## Users and jobs

- **Installer:** When setting up one fixed webcam and one projector, they
  need a calibration and scan they can judge from reported residuals, so
  that alignment is trusted before any content is authored.
- **Author:** When the room has been scanned, they need to paint surfaces
  and enable one interaction without building a 3D scene, so that a first
  experience exists the same day.
- **Visitor:** When they walk the floor, they need the ripples to follow
  their steps, and the room to remain beautiful if their body is missed,
  so that the installation degrades gracefully.

## Success measures

- A projected grid aligns at the centre and at the edges of the mapped
  plane or surfaces under test.
- Reprojection residuals are reported, including the worst region, not
  only a single average.
- A confidence-filtered scan does not invent unsupported triangles that
  bridge gaps in the observed geometry.
- Correspondence-based painting transfers appearance from a camera view
  into projector space without requiring a 3D mesh to be authored.
- The projector output continues if the Python companion's inference
  path is stopped, and if ComfyUI is absent or disconnected.
- Footstep ripples appear where ankles, ray-cast to the scanned floor,
  say a person stepped. End-to-end latency and false-trigger rate are
  measured under the actual projected content, not only on a bare floor.

## Scope

### In scope

- Gray-code structured-light calibration between one webcam and one
  projector. A printed checkerboard target is optional, not required.
- Projective reconstruction sufficient to render through the projector.
  One measured distance supplies metric scale when it is needed.
- A structured-light room scan that retains confidence, and a dense
  camera-to-projector correspondence field.
- “Paint the room” using that correspondence, with no 3D model required.
- A Godot 4 projector renderer that applies lens distortion as a lookup
  texture in a final shader pass.
- One interaction: footstep ripples, from a pose model's ankles ray-cast
  onto the scanned floor plane. Pose runs on the raw camera frame.
- Locked camera exposure and white balance as part of a repeatable
  setup. Predicted-frame subtraction may be added as a false-detection
  mask once raw-frame pose has been observed.

### Out of scope

- Dense live reconstruction of moving people.
- Multi-projector blending.
- View-dependent rendering for one or more privileged viewers.
- A custom operating system, or the later Lumur OS appliance image
  ([ADR 0007](../architectural-decisions/0007-lumur-os-as-appliance.md)).
- Multi-app compositing, automatic room semantics, and a second camera.
- A working ComfyUI integration (the renderer must already tolerate its
  absence; the integration itself is a later PRD).
- Synesyn bridge features, including Story Stage on Lumur.

## Critical journey

1. The installer mounts one webcam and one projector, and locks exposure
   and white balance.
2. They run Gray-code capture. A checkerboard may be used; it is not
   required. If metric scale is wanted, they enter one measured distance.
3. The system reports residuals, including the worst region. A projected
   grid is inspected at the centre and the edges.
4. A scan produces a correspondence field and a confidence-filtered
   mesh. Gaps are left as gaps.
5. The author paints the room through the correspondence field, without
   building a 3D model.
6. Footstep ripples are enabled. A visitor walks the floor; ripples
   follow visible feet.
7. The companion's inference path is stopped, or ComfyUI is left
   unconnected; projection continues.

There is no user guide yet. Operational detail belongs there once it
exists, not in a second copy of this journey.

## Requirements

- **REQ-001-001:** Calibration must recover a webcam–projector
  correspondence from Gray-code structured light, with a printed
  checkerboard optional.
- **REQ-001-002:** After calibration, a projected grid must be alignable
  at the centre and the edges of the mapped plane, and residuals —
  including the worst region — must be recorded.
- **REQ-001-003:** Metric scale, when requested, must be recoverable from
  a single measured distance. Rendering through the projector must not
  depend on that scale.
- **REQ-001-004:** A room scan must retain per-region confidence and must
  not emit unsupported triangles that bridge unobserved gaps.
- **REQ-001-005:** A paint-the-room mode must transfer appearance from
  camera space to projector space through the scanned correspondence,
  without requiring an authored 3D model.
- **REQ-001-006:** The Godot renderer must project into surface
  coordinates and apply distortion via a lookup texture derived from the
  scan.
- **REQ-001-007:** The renderer must continue in the absence of Python
  inference and in the absence of ComfyUI.
- **REQ-001-008:** Footstep ripples must be driven by ankle joints
  detected on the raw webcam frame and ray-cast onto the scanned floor.
- **REQ-001-009:** Setup must include a way to lock camera exposure and
  white balance. If a predicted-frame subtraction mask is present, it
  must be used to filter detections, not as the image the pose model
  sees.
- **REQ-001-010:** End-to-end ripple latency and false-trigger rate must
  be measurable under the projected content actually being shown.

## Acceptance

Automated coverage: none yet. Lumur is in design phase and has no
harness.

Manual coverage, when implementation begins:

- Projected grid alignment at centre and edges, with residual report
  including worst region (REQ-001-001, REQ-001-002).
- Optional scale from one measured distance; rendering still works if
  scale is omitted (REQ-001-003).
- Visual inspection that the scan follows visible geometry and does not
  bridge gaps (REQ-001-004).
- A paint-the-room pass completed without an authored mesh (REQ-001-005,
  REQ-001-006).
- Renderer still outputting after the companion inference path is
  stopped and with ComfyUI disconnected (REQ-001-007).
- Ripples under one and then two to four walkers, with latency and false
  triggers recorded; a deliberate occlusion case noted, not treated as
  a failure of the milestone (REQ-001-008, REQ-001-010).
- Exposure and white balance remain fixed during a session (REQ-001-009).

## Constraints and dependencies

- [ADR 0002: spiritual successor, not a port](../architectural-decisions/0002-spiritual-successor-not-a-port.md)
- [ADR 0003: projector as depth sensor](../architectural-decisions/0003-projector-as-depth-sensor.md)
- [ADR 0004: Godot addon and Python companion](../architectural-decisions/0004-godot-addon-and-python-companion.md)
- [ADR 0005: pose on the raw frame, subtraction as a mask](../architectural-decisions/0005-pose-and-predicted-frame-subtraction.md)
- [ADR 0006: runtime for rooms](../architectural-decisions/0006-room-as-os-runtime.md)
- [ADR 0008: ComfyUI is asynchronous and optional](../architectural-decisions/0008-comfyui-asynchronous.md)

No implementation contracts yet.

## Open questions and risks

- Target Godot 4 minor version is unset.
- Recommended webcam and projector hardware is unset.
- Pose model and tracker are unset (MediaPipe, YOLO-pose, ByteTrack were
  examples only).
- Whether the Python companion later becomes a GDExtension is open, and
  must not block this milestone.
- Radiometric calibration quality, and webcam latency, may limit how
  useful the subtraction mask is; the journey is valid without it.
- Single-camera occlusion and identity swaps are accepted risks for this
  milestone.
- Licence is decided: MIT for source code, CC BY-SA 4.0 for text and
  documentation. See [`LICENSE`](../../LICENSE). The public
  Metapunkt/lumur repository had not yet been created when this PRD was
  written; see the [scratchpad](../scratchpad.md#open-questions).

## Evidence map

- User workflow: not yet written
- Normative contract: not yet written
- Architectural decisions: ADR 0002, 0003, 0004, 0005, 0006, 0008
- Implementation tracker: none
- Executable specification: none
- Founding notes: [scratchpad](../scratchpad.md)
