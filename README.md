# Lumur

Projection-mapping runtime for Godot that makes rooms come alive
with just a webcam and a projector. A spiritual successor to Microsoft's
RoomAlive providing structured-light room scanning, surface-aware apps, interaction
through people's movement, and optional ComfyUI driven content generation. No Kinect
required.

The name joins *lumen* (light) with *mur* (French, from Latin *murus*: wall).

Geometry is authoritative: the system measures the room occasionally, tracks
only the interactions that matter, and renders continuously. Experiences are
apps that target named surfaces, so the same app can be installed in another
room.

**Status:** [PRD-001](docs/product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md),
[PRD-002](docs/product-requirements/PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md),
and [PRD-003](docs/product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
are **complete-in-sim** (calibrate → paint → ripples; generation, Synesyn
bridge, Story Stage, audience steering / replay; app manifest, compositor,
lifecycle, bundled paint/ripples apps + bridge-only Story Stage + app-side
generation — all against the sim and mocks).
Hardware validation is still pending. Founding intent:
[scratchpad](docs/scratchpad.md),
[ADRs](docs/architectural-decisions/README.md),
[PRDs](docs/product-requirements/README.md).

Code: Python companion [`companion/`](companion/) (calibrate, sim, room scan,
paint export, tracking, audience events, ComfyUI generation, optional Hub +
Story Stage + steering/replay bridge) and Godot 4 addons
[`addons/lumur/`](addons/lumur/), optional
[`addons/lumur_synesyn/`](addons/lumur_synesyn/).

## Sim quickstart (no hardware)

Uses one scene (`empty_room`) end to end. Needs `python3-venv` (Debian/Ubuntu:
`sudo apt install python3-venv`). Godot 4: download from
[godotengine.org](https://godotengine.org/download) and put the binary on
`PATH` as `godot`, or set `GODOT_BIN`. The tape-measure pixels below are for
the **64×48 projector / 80×60 camera** sim presets.

```bash
# 1) Companion
cd companion
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

lumur-calibrate --backend sim --scene empty_room \
  --distance-m 1.08 --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o ../demo/fixtures/sample_room/calibration.json
lumur-scan --backend sim --scene empty_room \
  --calibration ../demo/fixtures/sample_room/calibration.json \
  -o ../demo/fixtures/sample_room
lumur-export-godot ../demo/fixtures/sample_room

# Or skip capture and use the committed fixture:
#   demo/fixtures/sample_room/godot/

# 2) Godot (from repo root)
export LUMUR_GODOT_ASSETS="$PWD/demo/fixtures/sample_room/godot"
godot --path . demo/scenes/paint_demo.tscn   # or ripple_demo.tscn

# 3) Bundled apps (headless fit check)
lumur-app check ../apps/paint/lumur.app.json
lumur-app fit ../apps/paint/lumur.app.json --room ../demo/fixtures/sample_room
lumur-app fit ../apps/ripples/lumur.app.json --room ../demo/fixtures/sample_room
```

Keep calibrate and scan on the **same** `--scene`. A mismatch prints a warning.

## Documentation

Start at [`docs/`](docs/README.md). Calibration:
[`docs/companion/calibration.md`](docs/companion/calibration.md). Room scan:
[`docs/companion/room-scan.md`](docs/companion/room-scan.md). Tracking:
[`docs/companion/tracking.md`](docs/companion/tracking.md). Paint:
[`docs/godot/paint-mode.md`](docs/godot/paint-mode.md). Ripples:
[`docs/godot/ripples.md`](docs/godot/ripples.md). ComfyUI generation:
[`docs/companion/comfyui.md`](docs/companion/comfyui.md). Optional Synesyn
Hub bridge: [`docs/bridge/synesyn.md`](docs/bridge/synesyn.md). Story Stage
on surfaces: [`docs/bridge/story-stage.md`](docs/bridge/story-stage.md).
Audience steering:
[`docs/bridge/audience-steering.md`](docs/bridge/audience-steering.md).
Session / Story Log replay:
[`docs/bridge/replay.md`](docs/bridge/replay.md). App manifests + room fit:
[`docs/apps/manifest.md`](docs/apps/manifest.md). Input permissions:
[`docs/apps/input.md`](docs/apps/input.md). Compositor:
[`docs/apps/compositor.md`](docs/apps/compositor.md). Lifecycle / launcher:
[`docs/apps/lifecycle.md`](docs/apps/lifecycle.md). Generation from apps:
[`docs/apps/generation.md`](docs/apps/generation.md). Bundled packages:
[`apps/`](apps/).

## Licence

© 2026 “Lumur” by Ayodele Arigbabu

**Dual licence:** source code is [MIT](LICENSE); documentation and other text
are [CC BY-SA 4.0](LICENSE-docs)
([summary](https://creativecommons.org/licenses/by-sa/4.0/)).

## Credits

Built by **Ayodele Arigbabu** with the help of cheerful AI agents for the Metapunkt project.
