# Optional Synesyn Hub bridge (`lumur_synesyn`)

PRD-002 slice 2: second `SurfaceGenerator` provider that submits
`SynesynRenderRequestV1`-shaped requests to Synesyn Hub `/render/submit`.
Lumur core does **not** depend on Synesyn — enable this bridge only when you
want Hub provenance and SynPunkt workflow presets
([ADR 0009](../architectural-decisions/0009-standalone-with-synesyn-bridge.md),
[ADR 0015](../architectural-decisions/0015-single-lumur-synesyn-bridge.md),
[ADR 0016](../architectural-decisions/0016-pluggable-surface-generators.md)).

Standalone ComfyUI (slice 1) remains first-class:
[companion/comfyui.md](../companion/comfyui.md).

## Layout

| Piece | Location | Role |
| --- | --- | --- |
| Python package | `companion/lumur_synesyn/` | Hub HTTP client, provider, CLI |
| Extra | `pip install -e ".[synesyn]"` | Opt-in marker (no extra deps) |
| Godot addon | `addons/lumur_synesyn/` | Provider id + package texture apply |
| Core interface | `lumur.generate.SurfaceGenerator` | Unchanged; paint does not special-case Hub |

Absence of `lumur_synesyn` leaves calibrate / scan / paint / ripples / direct
ComfyUI generation identical.

## Setup

```bash
cd companion
source .venv/bin/activate
pip install -e ".[synesyn,dev]"   # or pip install -e ".[dev]" — package is present either way
```

Config (never commit secrets):

| Source | Keys |
| --- | --- |
| Env | `LUMUR_SYNESYN_HUB_URL`, `LUMUR_SYNESYN_HUB_TOKEN`, `LUMUR_SYNESYN_HUB_AUTH=1`, `LUMUR_SYNESYN_COMFY_URL` |
| JSON file | `{"hub":{"base_url":"…","auth":{"enabled":false,"token":""},"comfy_base_url":"…"}}` |
| CLI | `--hub-url`, `--hub-token`, `--hub-auth`, `--comfy-url`, `--config` |

`routing.comfy_base_url` is the ComfyUI instance the **Hub worker** calls
(same as SynPunkt Hub mode).

## Provider selection

| Goal | Command / provider |
| --- | --- |
| Direct ComfyUI (no Hub) | `lumur-generate … --comfy-url …` → `ComfyUISurfaceGenerator` |
| Hub + SynPunkt presets | `lumur-generate-synesyn … --hub-url …` → `SynesynHubSurfaceGenerator` |
| No generation | `NullSurfaceGenerator` / omit providers |

Paint mode only reads `godot/paint_manifest.json` → `generated_textures`.
Swap providers by configuration; do not change paint consumers (REQ-002-008).

```bash
# Reachability
lumur-generate-synesyn /tmp/sim-room --surface floor --hub-url http://127.0.0.1:8787 --ping

# Generate (tag-selected SynPunkt json.workflow)
lumur-generate-synesyn /tmp/sim-room --surface floor \
  --hub-url http://127.0.0.1:8787 \
  --comfy-url http://127.0.0.1:8188

# Optional: register room.json as Hub artifact first
lumur-generate-synesyn /tmp/sim-room --surface wall_1 \
  --hub-url http://127.0.0.1:8787 --register-room
```

Godot (after companion write):

```gdscript
var hub_gen := LumurSynesynHubSurfaceGenerator.new()
hub_gen.configure_package(paint)
hub_gen.request_surface("floor")  # non-blocking package apply
```

## Presets

Hub discovery queries `json.workflow` artifacts whose
`metadata.preset.tags` include `lumur:surface_role=<role>` (aligned with
SynPunkt / ScenSyn tagging documented in Synesyn’s SynPunkt guide).

| Tag | Meaning |
| --- | --- |
| `lumur:surface_role=<role>` | Required for discovery |
| `lumur:room=<id>` | Optional room scope |
| `lumur:scenario=<key>` | Optional scenario scope |

Selection fallback (most specific wins): role+room+scenario → role+room →
role → none. Pass `--preset <artifact_id>` to force an id.

If the Hub has no matching tagged preset, the CLI falls back to on-disk
Lumur presets (`companion/lumur/presets/workflows/`) unless
`--no-local-fallback` is set.

Control images are uploaded as Hub artifacts (`image.control`) and passed
as `input_uploads` entries (`node_id`, `input`, `artifact_id`) when the
preset declares `control_nodes`.

## Provenance

On success the room package gains the same layout as slice 1, plus Synesyn
IDs in `provenance.json` / `extra`:

- `synesyn_job_id`
- `synesyn_render_request_artifact_id`
- `synesyn_image_artifact_ids`
- `synesyn_workflow_artifact_id` (when known)
- `synesyn_prompt_id`

## Room package as Hub artifact (REQ-002-014)

`register_room_package` posts `room.json` (+ paint summary) via
`POST /substrate/artifacts` as type **`json.lumur_room`**. The public Hub
API already accepts arbitrary artifact types with `inline_json`; there is
no first-class Lumur room type in Synesyn yet — see Synesyn-side
touchpoints below.

## Tests

```bash
cd companion
pytest tests/test_generate_synesyn_hub.py
```

Uses an in-process mock Hub (submit, progress, success, failure, timeout,
auth, `input_uploads`, room registration). No live Hub or projector
required.

## Synesyn-side touchpoints (do not implement here)

Read-only against `Metapunkt/Synesyn`. Changes, if any, belong on
Synes-bot’s fork only.

| Touchpoint | Why | Status for slice 2 |
| --- | --- | --- |
| Document / accept `lumur:surface_role=*` (and optional scoping) beside `scensyn:render_purpose=*` in SynPunkt docs | Authors know the tag vocabulary | **Needed** (docs only; Hub already stores arbitrary `metadata.preset.tags`) |
| Official artifact type (or workshop allowlist note) for `json.lumur_room` / room package archive | REQ-002-014 clarity | **Needed** (convention works today via generic `POST /substrate/artifacts`) |
| HTTP download for artifact bytes when URI is not co-located `file://` (e.g. `GET /substrate/artifacts/{id}/content`) | Remote Hub installs cannot read Hub disk | **Needed** for non-local Hub; mock implements content route; co-located `file://` works as Synesyn does today |
| No change to `/render/submit`, job shape, or `SynesynRenderRequestV1` | Bridge uses public contracts | **None required** |

## Story Stage on surfaces

Slice 3 (layer → surface mapping, stub + paint / sim verification):
[story-stage.md](story-stage.md).

## Licence

Companion / addon source: MIT. This document: CC BY-SA 4.0.
