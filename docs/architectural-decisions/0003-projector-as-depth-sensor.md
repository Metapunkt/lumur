# 0003 — The projector is the depth sensor; geometry decides where

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** sensing / calibration
- **Relates to:** ADR 0002, ADR 0005, ADR 0008

## Context

Without a Kinect, the system still has to know where surfaces are, and
where projector pixels land on them. It is tempting to treat a monocular
depth model as a drop-in replacement. Models such as Depth Anything V2 can
supply relative or, in some variants, metric depth, but relative depth is
not a calibrated room measurement, and a metric prediction is still a
prediction. It does not, by itself, validate projector alignment against
observed geometry.

The projector is already a controlled light source in the room.

## Options considered

1. **RGB-only depth models as the primary measurement.** Attractive
   hardware-wise; alignment would rest on predictions that vary with
   lighting, texture and model choice. Licence terms for particular
   weights are **to verify** before any adoption.
2. **Structured light with the projector itself.** Project known patterns
   (Gray code for the first implementation), observe them with the webcam,
   and triangulate. Established camera–projector practice. Scan is
   occasional, not a per-frame dense reconstruction.
3. **Stereo from two ordinary cameras as the primary method.** More
   observable dynamic geometry later; heavier calibration and
   synchronisation, and weak on textureless walls — exactly the surfaces
   we will project onto.

## Decision

Option 2 is the foundation. **Geometry decides where; AI suggests what.**
The room is measured occasionally by structured light. Selected
interactions may be tracked continuously. Rendering runs continuously and
does not wait on a vision model.

AI depth, segmentation and pose are optional later tiers, not the source
of alignment. A second camera is an optional extension, not a requirement
for the first system.

Reconstruction for rendering may be projective and up to scale. A printed
checkerboard is optional. One tape-measured distance, or optionally a
phone LiDAR scan, can supply metric units when physics needs them.

## Consequences

- Positive: alignment rests on observations of patterns we emitted, which
  is something we can test and report residuals for.
- Positive: the first useful modes (a mapped plane, correspondence-based
  painting) do not require a perfect mesh.
- Trade-off: a scan describes a mostly static room. Freely moving people
  are not reconstructed in depth by this method; interaction with people
  is a separate, constrained problem (ADR 0005).
- Follow-up: confidence must be retained with the mesh, so unsupported
  triangles are not invented across gaps.
