# Standalone ComfyUI surface generation

Generate AI surface textures **without Synesyn** via Lumur’s direct ComfyUI
provider ([ADR 0008](../architectural-decisions/0008-comfyui-asynchronous.md),
[ADR 0016](../architectural-decisions/0016-pluggable-surface-generators.md),
[PRD-002](../product-requirements/PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md) slice 1).

The projector path never waits on ComfyUI. Generation runs in the Python
companion; Godot loads finished PNGs from the room package through existing
paint mode.

## Prerequisites

1. A scanned room package (`lumur-scan`) and Godot paint export
   (`lumur-export-godot`).
2. A reachable ComfyUI instance (or the in-process mock used by tests).
3. Companion installed: `cd companion && pip install -e ".[dev]"`.

## Quick start (sim room)

```bash
cd companion
source .venv/bin/activate

# Room + paint assets (sim, no hardware)
lumur-calibrate --backend sim --scene empty_room \
  --distance-m 1.08 --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o /tmp/sim-calibration.json
lumur-scan --backend sim --scene room_with_box \
  --calibration /tmp/sim-calibration.json -o /tmp/sim-room
lumur-export-godot /tmp/sim-room

# Reachability
lumur-generate /tmp/sim-room --surface floor --ping --comfy-url http://127.0.0.1:8188

# Generate (tag-selected preset for the surface role)
lumur-generate /tmp/sim-room --surface floor --comfy-url http://127.0.0.1:8188
lumur-generate /tmp/sim-room --surface wall_1 --preset surface_solid_dev \
  --comfy-url http://127.0.0.1:8188 --width 512 --height 512
```

Status goes to stderr; a JSON job summary goes to stdout.

## What gets written

```
<room>/
  generated/
    manifest.json          # lumur.generated — latest texture per surface
    gen_<id>/
      request.json         # lumur.surface_render_request snapshot
      result.png
      provenance.json      # lumur.generation_provenance (local, not Hub)
      controls/            # optional mask / depth / normal PNGs
  godot/
    paint_manifest.json    # gains generated_textures{ role|id → path }
```

Godot:

```gdscript
runtime.load_room("/tmp/sim-room/godot")
runtime.apply_generated_textures()  # non-blocking; no ComfyUI call
```

## Provider interface

| Piece | Location | Role |
| --- | --- | --- |
| `SurfaceGenerator` | `lumur.generate.provider` | Python ABC |
| `NullSurfaceGenerator` | same | Default: skip, no render errors |
| `ComfyUISurfaceGenerator` | `lumur.generate.comfy_provider` | Direct HTTP (+ optional WS progress) |
| `JobRunner` | `lumur.generate.jobs` | Thread-pool submit; runtime must not await |
| `LumurSurfaceGenerator` | `addons/lumur/surface_generator.gd` | Godot null / package apply |

Request shape (`lumur.surface_render_request`) mirrors Synesyn’s
`SynesynRenderRequestV1` by convention (`routing`, `workflow`, `patches`,
`client`, `input_uploads`) without importing Synesyn.

## Workflow presets

On-disk JSON under `companion/lumur/presets/workflows/`
(`schema: lumur.workflow_preset`). Tags live at `metadata.preset.tags`,
aligned with SynPunkt:

| Tag | Meaning |
| --- | --- |
| `lumur:surface_role=<role>` | Required for discovery (`floor`, `wall_1`, …) |
| `lumur:room=<id>` | Optional room scope |
| `lumur:scenario=<key>` | Optional scenario scope |

Selection fallback (most specific wins): role+room+scenario → role+room →
role → none. Pass `--preset <id>` to force an id.

Shipped presets (`surface_solid_dev`, `surface_floor_controls`) are **dev /
mock-friendly** EmptyImage graphs — swap in real ComfyUI API workflows for
production. Third-party node licences must be verified per preset.

## Control images

When a preset sets `controls.mask` / `depth` / `normal`, the companion
derives them from the room package (projector-space surface crop, resized to
the generation size) and uploads them through ComfyUI `/upload/image`.
CLI: `--controls auto|all|none`.

## Asynchronous behaviour

- `JobRunner.submit` returns immediately; poll or `wait`.
- CLI defaults to waiting; `--async` prints the job id and returns after
  enqueue on the worker pool.
- Failures / timeouts leave the last good paint content; paint_manifest
  `generated_textures` is only updated on success.

## Tests

```bash
cd companion
pytest tests/test_generate_comfyui.py
```

Uses an in-process mock ComfyUI (HTTP upload/prompt/history/view + WS
progress). No physical projector or live ComfyUI required.

## Limitations

- Slice 1 is **standalone only** — no Hub / SynPunkt / `lumur_synesyn`
  (those are PRD-002 slices 2+).
- Local provenance JSON is not a Hub artifact; Hub provenance arrives with
  the optional Synesyn provider.
- Godot texture sampling uses a fixed-size `Texture2DArray` (64² layers);
  high-res materials are resized on apply.
- WebSocket progress is best-effort; completion is always from `/history`
  polling.
- Shipped presets are placeholders for CI / mock, not production materials.

## Licence

Companion source: MIT. This document: CC BY-SA 4.0.
