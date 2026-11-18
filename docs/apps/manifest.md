# App manifests (`lumur.app`)

Versioned JSON beside a Godot scene that declares what an experience needs from
a scanned room — surface *kinds* and input permissions — so the same app can
retarget another room without editing projector pixels or UV
([ADR 0017](../architectural-decisions/0017-app-manifest-format.md),
[PRD-003](../product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
slice 1).

## Package shape

```
my_app/
  lumur.app.json     # schema lumur.app v1.0
  my_app.tscn        # scene path referenced by the manifest
```

Default filename: `lumur.app.json`. Schema identity matters; discovery path is
an implementation detail.

## Document fields

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | Must be `"lumur.app"` |
| `schema_version` | yes | `"1.0"` for this build; unknown major → reject |
| `id` | yes | Stable app id (e.g. `lumur.examples.ripples`) |
| `name` | yes | Human-readable title |
| `version` | yes | App semver string |
| `scene` | yes | Godot scene path (`res://…`) |
| `surfaces` | yes | List of surface *requests* (kinds, not pixels) |
| `inputs` | yes | Allowlist of room event types (ADR 0019 vocabulary) |
| `generation` | no | If true, app may call `SurfaceGenerator` (async / optional) |
| `bridge` | no | `null` for core apps; `"lumur_synesyn"` for bridge-only apps |
| `shares` | no | Surface keys willing to draw as overlays (compositor, later slice) |

Readers **ignore unknown fields**. Breaking changes bump `schema_version`.

### Surface requests

| Field | Meaning |
| --- | --- |
| `key` | App-local name used when asking the runtime for the binding |
| `role` | `floor`, `wall` (any wall), or a named role such as `wall_1` |
| `min_width_m` | Optional minimum extent (metres) on the major horizontal axis |
| `min_confidence` | Optional floor on mean scan confidence for that surface |
| `count` | Optional; default 1 |
| `required` | Default true — unmet → hard fail; false → bind null / degrade |

**Forbidden** on surface requests: `plane_id`, pixel rects, UV quads, or any
other projector-placement fields. Placement is the runtime’s job.

### Example

```json
{
  "schema": "lumur.app",
  "schema_version": "1.0",
  "id": "lumur.examples.ripples",
  "name": "Footstep ripples (example)",
  "version": "0.1.0",
  "scene": "res://apps/examples/ripples/ripple_app.tscn",
  "surfaces": [
    {
      "key": "floor",
      "role": "floor",
      "min_confidence": 0.15,
      "required": true
    }
  ],
  "inputs": ["footstep"],
  "generation": false,
  "bridge": null
}
```

Shipped examples: [`apps/examples/`](../../apps/examples/).

## Room fit

At install / launch the runtime binds each request to concrete surface ids from
the current `lumur.room` package (+ Godot paint `role_index`)
([ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md)):

1. Candidates match role (`floor` exact; `wall` → any `wall_*` / `kind=wall`).
2. Filter by `min_width_m` and `min_confidence` when set.
3. Prefer larger width, then lower `plane_id` (deterministic).
4. Assign distinct candidates in manifest order.
5. `required: true` + no candidate → structured `unmet_surface` failure.
6. `required: false` → `surface_id: null`; app must tolerate missing handles.
7. **No geometry invention** — low-confidence gaps stay gaps.

Paint export writes `width_m` and `mean_confidence` on each surface in
`paint_manifest.json` so Godot can fit without reading `.npz`.

## APIs

**Python companion**

```python
from lumur.app import (
    load_app_manifest,
    validate_app_manifest,
    RoomServices,
    fit_app_to_room,
    FitError,
)

manifest = load_app_manifest("apps/examples/ripples/lumur.app.json")
room = RoomServices.load("/tmp/sim-room")  # after lumur-scan + export
try:
    result = fit_app_to_room(manifest, room)
except FitError as exc:
    print(exc.result.to_dict())
else:
    print(result.bindings["floor"].surface_id)
```

`RoomServices` is the app-facing room “file system”: surfaces, roles, floor
plane id, confidence metrics, and `generated_textures` handles.

**Godot** (`addons/lumur`)

- `LumurAppManifest` — load / validate
- `LumurAppFit` — allocate against a `LumurRoomPackage`
- `LumurRoomRuntime.load_app_manifest` / `fit_app` / `bound_surface_id`

## Verification

Headless companion tests in `companion/tests/test_app_manifest_fit.py` cover
valid / invalid manifests, version handling, fit success, fallback / failure,
and deterministic binding on `empty_room`, `room_with_box`, and `noisy_room`.

## Related

Per-app input allowlist and event bus: [input.md](input.md) (PRD-003 slice 2).
Compositor ownership / masking: [compositor.md](compositor.md) (slice 3).
Lifecycle / launcher / zone switch: [lifecycle.md](lifecycle.md) (slice 3).

## Licence

Source code MIT. This document CC BY-SA 4.0.
