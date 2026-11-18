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

**Status:** [PRD-001](docs/product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md)
and [PRD-002](docs/product-requirements/PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md)
are **complete-in-sim** (calibrate → paint → ripples; generation, Synesyn
bridge, Story Stage, opt-in audience steering / replay — all against the
sim and mocks). [PRD-003](docs/product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
is in progress: **slice 1 (manifest + room fit) complete-in-sim**; later
slices cover input permissions, compositor/lifecycle, and bundled apps.
Hardware validation is still pending. Founding intent:
[scratchpad](docs/scratchpad.md),
[ADRs](docs/architectural-decisions/README.md),
[PRDs](docs/product-requirements/README.md).

Code: Python companion [`companion/`](companion/) (calibrate, sim, room scan,
paint export, tracking, audience events, ComfyUI generation, optional Hub +
Story Stage + steering/replay bridge) and Godot 4 addons
[`addons/lumur/`](addons/lumur/), optional
[`addons/lumur_synesyn/`](addons/lumur_synesyn/).

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
[`docs/apps/manifest.md`](docs/apps/manifest.md).

## Licence

© 2026 “Lumur” by Ayodele Arigbabu

Source code is MIT. Text, documentation, and other website material are
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). See
[`LICENSE`](LICENSE).

## Credits

Built by **Ayodele Arigbabu** with the help of cheerful AI agents for the Metapunkt project.
