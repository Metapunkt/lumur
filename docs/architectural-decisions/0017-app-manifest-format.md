# 0017 — App manifest format and versioning

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** runtime / apps / interchange
- **Relates to:** ADR 0006, ADR 0012, ADR 0013, ADR 0018, ADR 0019; PRD-003
- **Refines:** ADR 0006 (apps as Godot scenes with a small manifest —
  concrete schema and versioning below)

## Context

ADR 0006 decided that Lumur apps are Godot scenes plus a small manifest
that declares the surfaces an app needs, so the same app can retarget
another room. PRD-001/002 demos (paint, ripples, Story Stage) still wire
surfaces and inputs in scene scripts. Without a versioned manifest
contract, every new experience invents its own “needs floor” convention,
and the deferred multi-app compositor has nothing stable to allocate
against.

## Options considered

1. **Keep demos as bespoke scenes.** Fastest short-term; blocks portability
   and compositing. Rejected for PRD-003.
2. **Full app-store package** (signed bundle, sandbox FS, rich capability
   OS). Too heavy; none of it helps the first three apps. Rejected.
3. **Versioned JSON manifest beside the scene** (`lumur.app`), declaring
   identity, surface *kinds*, and input permissions. Runtime binds kinds
   to the current room package. Chosen.

## Decision

Option 3. Adopt schema `lumur.app` with explicit `schema_version`.

### Binding rules

1. **One manifest per app.** Default filename `lumur.app.json` next to the
   main `.tscn` (exact discovery path is an implementation detail; schema
   identity is not).
2. **Surfaces are kinds, never pixels.** Requests name role and optional
   constraints (minimum extent in metres, minimum confidence, optional
   count). They must not include projector pixel rects, raw UV quads, or
   hard-coded `plane_id` values that only exist in one scan.
3. **Inputs are declared permissions.** The `inputs` list is the only event
   types the app may receive ([ADR 0019](0019-app-input-permissions.md)).
4. **Versioning is append-friendly.** Readers must ignore unknown fields.
   Breaking changes bump `schema_version` (e.g. `1.0` → `2.0`). Additive
   fields stay on the same major when defaulted safely.
5. **Scene entry is data.** Manifest points at a Godot scene path; the
   runtime instantiates and binds allocated surface handles before
   `_ready` work that paints.

### Shape (`schema_version` `1.0`)

Normative for PRD-003 slice 1 (validator + tests). Authoring guide:
[docs/apps/manifest.md](../apps/manifest.md).

```json
{
  "schema": "lumur.app",
  "schema_version": "1.0",
  "id": "lumur.ripples",
  "name": "Footstep ripples",
  "version": "1.0.0",
  "scene": "res://apps/ripples/ripple_app.tscn",
  "surfaces": [
    {
      "key": "floor",
      "role": "floor",
      "min_confidence": 0.2,
      "required": true
    }
  ],
  "inputs": ["footstep"],
  "generation": false,
  "bridge": null
}
```

Surface request fields expected in v1.0:

| Field | Meaning |
| --- | --- |
| `key` | App-local name the scene uses when asking the runtime for its binding. |
| `role` | Room role to match (`floor`, `wall`, or a named role such as `wall_1` preference). |
| `min_width_m` | Optional minimum extent (metres) along the surface’s major horizontal axis. |
| `min_confidence` | Optional floor on scan confidence for accepted pixels / plane. |
| `count` | Optional; default 1. How many distinct surfaces of this kind. |
| `required` | If true, install/launch fails when unmet; if false, app launches degraded. |

Optional top-level:

| Field | Meaning |
| --- | --- |
| `generation` | If true, app may call `SurfaceGenerator` (still async / optional). |
| `bridge` | `null` for core apps; `"lumur_synesyn"` for bridge-only apps (Story Stage). |
| `shares` | Optional list of surface keys the app is willing to share as an overlay (see ADR 0018). |

Allocation and conflict rules live in
[ADR 0018](0018-surface-allocation-and-compositing.md), not in this file.

## Consequences

- Positive: portability becomes testable — same manifest, two sim room
  packages, different bound ids.
- Positive: bundled demos become the proof of the format (PRD-003
  REQ-003-015/016).
- Trade-off: authors must think in roles and metres, not in the projector
  layout they see in one room.
- Trade-off: v1.0 will be deliberately small; rich adjacency / doorway
  queries from ADR 0006 wait until an app needs them.
- Follow-up done (slice 1): companion validator (`lumur.schema.app`) and
  Godot loader (`LumurAppManifest`); room-fit in `lumur.app.fit` /
  `LumurAppFit`. Slice 4 ships bundled `apps/paint`, `apps/ripples`, and
  bridge-only Story Stage under `addons/lumur_synesyn/apps/`.
