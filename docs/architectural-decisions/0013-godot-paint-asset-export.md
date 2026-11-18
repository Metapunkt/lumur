# 0013 — Godot paint assets exported as PNG + JSON

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** companion / Godot interchange / paint
- **Relates to:** ADR 0004, ADR 0006, ADR 0012; PRD-001

## Context

Paint-the-room (PRD-001 REQ-001-005 / REQ-001-006) needs the projector→surface
correspondence from the room package inside Godot shaders. The package stores
dense maps as compressed `.npz` ([ADR 0012](0012-versioned-room-package.md)).
GDScript has no first-class NumPy reader, and pulling a GDExtension only to
load arrays would overweight the first renderer slice.

## Options considered

1. **Read `.npz` in GDScript / a tiny GDExtension.** Keeps one on-disk
   format; adds native code or a fragile custom parser before the first
   picture.
2. **Rewrite the room package to OpenEXR / PNG only.** Breaks the companion
   scan contract just agreed in ADR 0012, and forces CV code to round-trip
   through image codecs.
3. **Companion export step:** leave `lumur.room` v1.0 as-is, and write a
   `godot/` subdirectory of PNG lookup textures plus `paint_manifest.json`
   for the renderer and surface-target API.

## Decision

Option 3. `lumur-export-godot` (and the `lumur.paint.export` API) materialises:

- `surface_id.png` — projector-resolution surface ids (R8)
- `confidence.png` — confidence × 255 (R8)
- `lookup.png` — RGB8 camera-UV + valid mask (distortion baked into the
  Gray-code correspondence, per the scratchpad)
- `paint_manifest.json` — schema `lumur.paint_godot` v1.0, surface records,
  and a role index (`floor`, `wall_1`, …)

Godot loads only these assets on the critical path. The Python companion
keeps `.npz` for scan/diagnostics. A Python reference painter mirrors the
shader for headless CI when a Godot binary is absent.

## Consequences

- Positive: Godot stays GDScript-only for paint; no GDExtension required yet.
- Positive: ADR 0012 room packages remain valid without the export; export is
  additive (`arrays.godot` pointer in `room.json`).
- Trade-off: 8-bit UV quantisation in `lookup.png` is coarse at high
  resolution; a later EXR/float export can supersede without changing the
  room schema.
- Follow-up: optional higher-precision lookup textures; mesh consumption
  still deferred.
