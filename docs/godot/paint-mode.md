# Paint the room (Godot)

Correspondence-based projector painting for [PRD-001](../product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md)
([ADR 0004](../architectural-decisions/0004-godot-addon-and-python-companion.md),
[ADR 0006](../architectural-decisions/0006-room-as-os-runtime.md),
[ADR 0012](../architectural-decisions/0012-versioned-room-package.md),
[ADR 0013](../architectural-decisions/0013-godot-paint-asset-export.md)).

No authored 3D mesh is required. The scan’s projector→camera map selects a
surface id per projector pixel; the Godot addon fills those pixels from
per-surface content (solid colour, tinted texture hook, or a simple pulse).

## Prerequisites

1. A room package from [`lumur-scan`](../companion/room-scan.md).
2. Godot **4.3** (other 4.x minors are expected to work; 4.3 is what the
   demo `project.godot` declares).
3. Exported paint assets (below).

## Export Godot assets

GDScript does not read `.npz`. Export PNG lookups + a manifest into the
package:

```bash
cd companion
source .venv/bin/activate

# After lumur-scan -o /tmp/sim-room
lumur-export-godot /tmp/sim-room
```

This writes `/tmp/sim-room/godot/`:

| File | Role |
| --- | --- |
| `paint_manifest.json` | `lumur.paint_godot` v1.0 — surfaces, roles, texture names |
| `surface_id.png` | R8 projector map: pixel value = surface id |
| `confidence.png` | R8: confidence × 255 |
| `lookup.png` | RGB8: R/G = normalised camera UV, B = valid. Distortion is already baked into the Gray-code correspondence. |

`room.json` gains `arrays.godot` pointing at the manifest. Older readers that
ignore unknown keys remain valid.

## Run the demo

Repository root is the Godot project (`project.godot` + `addons/lumur`).

```bash
export LUMUR_GODOT_ASSETS=/tmp/sim-room/godot
godot --path . 
# or: tools/godot --path .
```

The demo paints `floor` red, `wall_1` blue, and pulses `wall_2` when present.

## Headless render (CI / verification)

Godot’s `--headless` flag uses the dummy renderer, which does not draw
canvas shaders. For a real paint PNG, use a virtual display:

```bash
xvfb-run -a godot --path . \
  --display-driver x11 --rendering-driver opengl3 \
  --script res://demo/scripts/headless_paint_render.gd \
  -- --assets=/tmp/sim-room/godot --out=/tmp/paint.png
```

Python tests call the same path when a Godot binary is on `PATH`, at
`tools/godot`, or in `GODOT_BIN`, and `xvfb-run` is available. If Godot
or xvfb is missing, the companion’s **reference painter**
(`lumur.paint.render`) still verifies mapping and sim colour landing —
see Limitations.

## Surface target API

Apps address surfaces by **id** or **role**, not by raw projector UV.

| Key | Meaning |
| --- | --- |
| `floor` | Floor plane from the scan |
| `wall_1`, `wall_2`, … | Walls in ascending `plane_id` order |
| scan `label` | e.g. `wall_3`, `non_planar`, `surface_4` |
| integer id | Stable `plane_id` from `room.json` |

GDScript:

```gdscript
var runtime: LumurRoomRuntime = $PaintDemo
runtime.load_room("/tmp/sim-room/godot")
runtime.paint_surface("floor", Color(0.9, 0.2, 0.15))
runtime.pulse_surface("wall_1", Color(0.2, 0.6, 0.95), 0.8)

var floor := runtime.surface("floor")
print(floor.surface_id, floor.roles)
```

`LumurPaintMode` is a fullscreen `ColorRect` using `paint_mode.gdshader`.
It samples the exported textures, applies a confidence threshold, and looks
up a 256-wide palette / mode row keyed by surface id. The renderer does not
call Python or ComfyUI on its critical path ([ADR 0008](../architectural-decisions/0008-comfyui-asynchronous.md)).

## How the mapping works

1. Companion scan scatters camera→projector samples into `projector_map.npz`.
2. Export projects `points.npz` `surface_id` into projector space through that
   map and writes PNG lookups.
3. For each projector pixel with confidence ≥ threshold and a non-zero
   surface id, the shader emits that surface’s colour (or pulse).
4. Optional verification: feed the projector RGB image into the sim’s
   `render_camera_view(..., retain_color=True)` and check chromaticity on
   camera pixels labelled with the same surface id.

## Layout

```
addons/lumur/          Godot 4 addon (MIT)
  plugin.cfg
  room_package.gd      loads godot/ assets
  surface_target.gd    per-surface content handle
  paint_mode.gd(.shader)
  room_runtime.gd      small room-as-OS facade
demo/
  scenes/paint_demo.tscn
  scripts/headless_paint_render.gd
project.godot          demo project at repo root
```

## Limitations

- **8-bit lookup UV** — fine at the 64×48 sim preset; high-res rooms may want
  a float/EXR export later (ADR 0013).
- **Texture mode** is scaffolded in the surface API; the lean shader pass
  uses solid + pulse for the first milestone. Full atlas sampling can land
  without changing the export contract.
- **Godot in CI** — preferred when `godot` / `GODOT_BIN` is available. The
  Python reference painter is the guaranteed headless path and must stay
  behaviourally aligned with the shader.
- **No mesh** — paint does not require one; a confidence-filtered mesh remains
  optional later work.

## Licence

Addon and demo source: MIT. This document: CC BY-SA 4.0.
