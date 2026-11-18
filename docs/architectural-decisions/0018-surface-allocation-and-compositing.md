# 0018 — Surface allocation and compositing rules

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** runtime / display / apps
- **Relates to:** ADR 0006, ADR 0012, ADR 0013, ADR 0017, ADR 0019; PRD-003
- **Refines:** ADR 0006 (display server / multi-app compositing was deferred
  until real apps needed it — PRD-003 slice 3 implements ownership + cut
  handoff; see [compositor.md](../apps/compositor.md))

## Context

Paint mode already maps per-surface content through correspondence and
confidence ([ADR 0013](0013-godot-paint-asset-export.md),
[paint-mode.md](../godot/paint-mode.md)). ADR 0006 said Lumur owns the
projector output and postponed compositing several apps until more than one
app needed it. PRD-003 introduces manifests that request surface *kinds*
and a lifecycle that can launch more than one experience. Without shared
rules for who gets which surface, how conflicts resolve, and what happens
when a room lacks a requested kind, every app will fight over `wall_1`.

## Options considered

1. **Single fullscreen app only.** Keeps today’s demos; fails PRD-003’s
   multi-app and launcher goals. Rejected as the end state.
2. **Pixel window manager** (rectangles in projector space). Fights the
   surface-native model; apps regain pixel coordinates. Rejected.
3. **Role/constraint allocator + paint-mode compositor.** Bind manifest
   requests to room surfaces; exclusive ownership by default; overlays only
   when declared; confidence masking unchanged. Chosen.

## Decision

Option 3.

### Allocation (manifest → room)

1. **Inputs.** Current `lumur.room` package (+ Godot `role_index` /
   planes), and the app’s surface requests from
   [ADR 0017](0017-app-manifest-format.md).
2. **Matching order.** For each request, candidate surfaces are those
   whose role matches (`floor` exact; `wall` matches any `wall_*` /
   `kind=wall`; a specific label matches that label). Filter by
   `min_confidence` and `min_width_m` when present. Prefer larger extent,
   then lower `plane_id` / stable id for determinism.
3. **Binding.** Assign distinct candidates to requests in manifest order.
   A surface already exclusively owned by a running app is not a candidate
   unless that app pauses/stops or the new request opts into sharing.
4. **Missing surfaces.**
   - `required: true` and no candidate → **hard fail** install/launch with
     a structured reason (`unmet_surface`, request key, constraints).
   - `required: false` → bind `null`; app must tolerate missing handles;
     projector shows prior content or clear on that region.
5. **No geometry invention.** Allocation never synthesises planes or
   fills low-confidence gaps. Confidence masking at draw time remains
   paint-mode’s threshold behaviour.

### Ownership and layering

1. **Exclusive by default.** One launched app owns a bound surface’s base
   layer. A second app cannot take that surface until the owner pauses,
   stops, or yields.
2. **Declared overlays.** An app may list surface keys under `shares` (or
   an equivalent) to draw an overlay (example: ripples on a floor another
   app painted). Overlay apps still need a successful bind; they do not
   steal base ownership.
3. **Conflict at launch.** If two apps request the same exclusive surface
   and both would be foreground, the launcher starts only one; the other
   stays installed but not launched (or launches degraded if its request
   was optional). No silent split of one wall between two unaware apps.
4. **Regions.** v1 allocates whole surfaces (plane ids). Sub-surface
   regions (safe bands, caption strips) may be expressed later as optional
   normalized insets on an owned surface; they are not a second allocator.

### Compositing path

1. Reuse paint-mode / correspondence shaders: each owned surface contributes
   colour/texture into the projector map; invalid / low-confidence pixels
   stay masked.
2. **Transitions** on switch/pause: v1 requires a deterministic **cut**
   (clear or hand off on the next frame). Optional crossfade may be added
   without changing ownership rules.
3. **Generation** textures apply only to surfaces the requesting app owns
   (or overlays), through `SurfaceGenerator` (ADR 0016); never by writing
   another app’s base layer behind its back.

### Fallbacks (summary)

| Situation | Behaviour |
| --- | --- |
| Role present, constraints unmet | Try next candidate; then required-fail or optional-null |
| No wall in room, app wants `wall` | Hard fail if required; else degrade |
| Two apps want `floor` exclusive | Second does not launch on that surface |
| Ripples declare share on `floor` | Allowed overlay if base owner accepts shares / policy allows |
| Confidence below threshold | Pixels remain unpainted; not reassigned |

## Consequences

- Positive: apps stay portable; conflicts are explicit and testable in sim
  with wall-poor and multi-wall presets.
- Positive: paint-mode confidence behaviour stays the single masking
  authority.
- Trade-off: whole-surface allocation is coarse; workshop layouts that need
  two apps on one wall wait for region insets or a later ADR.
- Trade-off: authors must mark overlays explicitly — accidental double paint
  on the floor is a config error, not undefined behaviour.
- Follow-up: region insets / crossfade remain future work; slice 3 shipped
  whole-surface ownership + cut transitions in `Compositor` /
  `LumurCompositor` with companion sim tests.
