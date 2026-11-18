# 0002 — A spiritual successor to RoomAlive, not a port

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** product / architecture
- **Relates to:** ADR 0003, ADR 0004

## Context

The project began as a question about porting Microsoft's RoomAlive Toolkit
to Godot. RoomAlive is MIT-licensed and combines projector–camera
calibration, Kinect depth, and engine-side rendering in Unity. The Kinect
was effective, and it became a bottleneck once Microsoft stopped producing
it. Software for computer vision, segmentation and pose has moved on, and
the brief is to use only ordinary cameras — a standard webcam as the
baseline — together with a projector.

A line-by-line port would drag a Kinect-era architecture into a project
whose point is to leave that hardware behind.

## Options considered

1. **Port RoomAlive Toolkit** into Godot, replacing the Kinect module with
   a new depth source but keeping the original shape. Preserves known
   behaviour; inherits an architecture designed around a device we will not
   use.
2. **A spiritual successor.** Reuse ideas, calibration knowledge, and
   perhaps isolated algorithms under the MIT licence. Do not preserve the
   Unity or Kinect structure. Design around a webcam and a projector.

## Decision

Option 2. Lumur is not a port. There is no Kinect, and no other specialised
depth camera, in the baseline system. One fixed webcam and one projector
are the first hardware configuration.

## Consequences

- Positive: the design can be smaller, and can be honest about what a
  webcam can and cannot replace.
- Trade-off: behaviour will not be a drop-in replica of RoomAlive
  experiences, especially those that depended on dense live depth.
- Follow-up: sensing method is decided in ADR 0003; engine and process
  boundaries in ADR 0004.
