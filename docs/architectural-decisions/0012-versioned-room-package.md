# 0012 — Versioned room package for scan output

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** companion / scan / interchange
- **Relates to:** ADR 0003, ADR 0004, ADR 0006, ADR 0011; PRD-001

## Context

The structured-light room scan (PRD-001 REQ-001-004) must hand geometry to
Godot and to later paint-the-room / footstep-ripple work. The scan produces
more than a mesh: dense points or depth, per-pixel confidence, masks for
invalid regions, labelled planes (including the floor), and the
camera↔projector correspondence field. Callers need a stable on-disk
contract that can evolve without breaking consumers.

## Options considered

1. **Calibration JSON only, plus ad-hoc `.npz` files.** Cheap, but the
   room artefacts have no schema identity, and paint / ripple each invent
   their own layout.
2. **A single HDF5 / OpenEXR container.** Rich, but adds a heavy dependency
   beyond numpy + OpenCV for the first companion slice.
3. **A versioned package directory:** `room.json` (`lumur.room` v1.0) plus
   compressed `.npz` arrays for dense maps. Matches the existing
   `lumur.calibration` pattern.

## Decision

Option 3. The companion writes a **room package** directory:

- `room.json` — schema id/version, calibration reference (and an embedded
  calibration summary), plane / surface records with stable IDs, floor
  plane id, coverage report, mask-code legend.
- `points.npz` — per-camera-pixel `points`, `depth` (optical-axis Z),
  `normals`, `confidence`, `mask`, `surface_id`, `proj_u` / `proj_v`,
  plus diagnostic `reprojection_error_px` and `triangulation_angle_deg`.
- `projector_map.npz` — dense projector→camera scatter (`cam_u`, `cam_v`,
  `confidence`, `valid`) for correspondence-based painting.

Coordinate frame is the **camera** frame from the calibration document.
Gaps stay gaps: low-confidence and invalid pixels are masked; no bridging
triangles are emitted. A simple plane-derived normal map is included;
a full mesh is optional later and is not required for paint-the-room.

## Consequences

- Positive: Godot and future companion tools share one versioned contract;
  schema bumps are explicit (`schema_version`).
- Positive: Dependencies stay at numpy + OpenCV; no HDF5/EXR requirement
  for the first scan slice.
- Trade-off: multiple files per scan; consumers must read the manifest
  before the arrays.
- Follow-up: paint-the-room consumes `projector_map.npz`; footstep ripples
  consume `floor_plane_id` and the floor plane equation.
