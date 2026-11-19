# 0020 — Coplanar plane merge and tilt reject in room scan

- **Status:** Accepted
- **Date:** 2026-11-19
- **Area:** companion / scan
- **Relates to:** ADR 0011, ADR 0012, ADR 0013; PRD-001
- **Refines:** sequential RANSAC segmentation in `lumur.scan.planes`

## Context

On planar sim presets (especially `empty_room`), sequential RANSAC minted many
tilted `surface_*` fragments that were neither walls nor floors. App fit still
succeeded via the floor role, but the surface table was noisy and hard to
reason about in demos and docs.

## Options considered

1. **Leave as-is.** Rejected: empty rooms over-segmented into ~7 `surface_*`
   planes.
2. **Lower `max_planes` only.** Rejected: still admits tilted junk first.
3. **Reject mid-tilt RANSAC hits, merge near-coplanar fragments, collapse
   duplicate floor-like planes.** Chosen.

## Decision

Option 3. Gravity alignment bands drop tilted fragments into `non_planar`;
near-coplanar survivors merge; extra passes may only mint wall-like planes.
Presets keep a floor role and continue to fit bundled paint/ripples apps.

## Consequences

- Fewer surfaces on empty/noisy rooms; box residue remains `non_planar` or
  wall-like faces on `room_with_box`.
- Thresholds (`WALL_ALIGN_MAX`, `FLOOR_ALIGN_MIN`, merge distance) are tunable
  but shared across presets — change carefully and re-check app fits.
