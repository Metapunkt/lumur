# 0005 — Pose on the raw frame, subtraction as a mask

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** sensing / interaction
- **Relates to:** ADR 0003, ADR 0006

## Context

Projected content appears in the webcam image. That can be mistaken for a
person, and projected light on a person's body can confuse joint
detection. An infrared workaround was considered: a webcam with its
IR-cut filter removed, a visible-light-blocking filter, and an 850 nm
illuminator, so the tracking camera cannot see the projection. The
project owner declined hardware hacks of that kind.

Subtraction is the attractive software alternative, but subtraction is
not what *finds* people.

## Options considered

1. **Infrared camera and illuminator.** Robust against contamination;
   rejected, because it requires modified hardware.
2. **Run the pose model on a subtracted or difference image.** Removes
   projection, but also removes clothing texture and lighting that pose
   models are trained on, and inherits every error in the predicted frame.
3. **Pose on the raw frame, subtraction as a filter.** A pose model runs
   on the unmodified webcam image. A predicted-frame difference mask is
   used to reject detections that coincide with what we just projected
   (for example, a figure painted on the wall).

## Decision

Option 3.

To make subtraction trustworthy: lock the webcam's auto-exposure and
white balance; perform a rough radiometric calibration; compare against
a short buffer of recent renders, because USB webcams typically lag by
tens of milliseconds.

Several people in one frame are expected to be detectable by a modern
pose model. Identity and occlusion are harder. A tracker (ByteTrack was
named as an example, not a selection) should be used so identities do
not swap when paths cross. With one camera, a person standing behind
another loses joints. Two to four people in a living-room-sized space is
the design point for effects such as footstep ripples. Dense crowds or
precise per-person hand interaction would need a second camera.

3D location uses the room, not a depth camera: cast a ray from the
camera through each ankle and intersect the scanned floor (and the same
for a hand near a known wall).

Prototype order: lock exposure, run pose on raw frames, add the
subtraction mask once the actual false detections are visible.

The exact pose model is still open.

## Consequences

- Positive: no modified cameras; detection uses images the models were
  trained on; subtraction earns its keep against concrete false
  positives.
- Trade-off: strong, fast-moving projection on a torso can still jitter
  joints, especially in a dark room. Calmer or darker content near
  people will help.
- Trade-off: single-camera occlusion and identity swaps are accepted
  limits, not problems the first system pretends to have solved.
