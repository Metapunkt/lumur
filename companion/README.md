# Lumur companion

Python/OpenCV companion for structured-light calibration, room scan, and
tracking. Godot owns rendering; this process owns capture, Gray-code
decoding, calibration JSON, versioned room packages, pose / subtraction,
and footstep events
([ADR 0004](../docs/architectural-decisions/0004-godot-addon-and-python-companion.md),
[ADR 0005](../docs/architectural-decisions/0005-pose-and-predicted-frame-subtraction.md),
[ADR 0012](../docs/architectural-decisions/0012-versioned-room-package.md),
[ADR 0014](../docs/architectural-decisions/0014-udp-json-event-transport.md)).

## Setup

```bash
cd companion
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Tests (headless, no hardware)

```bash
cd companion
pytest
```

## Simulated projector–camera rig

```bash
lumur-calibrate --backend sim --scene empty_room \
  --distance-m 1.08 --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o /tmp/sim-calibration.json

lumur-scan --backend sim --scene room_with_box \
  --calibration /tmp/sim-calibration.json \
  -o /tmp/sim-room
```

Presets: `empty_room`, `room_with_box`, `noisy_room`, `room_with_walkers`. See
[docs/companion/simulation.md](../docs/companion/simulation.md) and
[docs/companion/room-scan.md](../docs/companion/room-scan.md).

## Godot paint export

```bash
lumur-export-godot /tmp/sim-room
# → /tmp/sim-room/godot/paint_manifest.json + PNG lookups
```

See [docs/godot/paint-mode.md](../docs/godot/paint-mode.md) and
[ADR 0013](../docs/architectural-decisions/0013-godot-paint-asset-export.md).

## Tracking / footstep ripples

```bash
lumur-track --scene room_with_walkers --people 2 --frames 120
# UDP JSON footsteps → 127.0.0.1:8765 (Godot LumurEventReceiver)
```

Optional real pose backends: `pip install -e ".[pose]"` (MediaPipe) or
`.[yolo]`. Sim tests use the built-in oracle detector. See
[docs/companion/tracking.md](../docs/companion/tracking.md) and
[docs/godot/ripples.md](../docs/godot/ripples.md).

## Surface generation (standalone ComfyUI)

```bash
lumur-generate /tmp/sim-room --surface floor --comfy-url http://127.0.0.1:8188
# → /tmp/sim-room/generated/ + paint_manifest generated_textures
```

No Synesyn dependency. See
[docs/companion/comfyui.md](../docs/companion/comfyui.md).

## Optional Synesyn Hub bridge

```bash
pip install -e ".[synesyn]"   # marker extra; stdlib HTTP only
lumur-generate-synesyn /tmp/sim-room --surface floor \
  --hub-url http://127.0.0.1:8787 --comfy-url http://127.0.0.1:8188
```

Separate package `lumur_synesyn` + Godot addon `addons/lumur_synesyn/`.
Core Lumur is unchanged without it. See
[docs/bridge/synesyn.md](../docs/bridge/synesyn.md).

## Story Stage → surfaces (slice 3)

Stub / layout / paint projection (no live Synesyn required):

```bash
pytest tests/test_story_stage_surfaces.py
```

See [docs/bridge/story-stage.md](../docs/bridge/story-stage.md).

## App manifests + room fit (PRD-003 slice 1)

```bash
pytest tests/test_app_manifest_fit.py
```

`lumur.app` schema / validator, `RoomServices` facade, and
`fit_app_to_room` bind surface *kinds* to a scanned room (no Synesyn).
See [docs/apps/manifest.md](../docs/apps/manifest.md).

## App input permissions (PRD-003 slice 2)

```bash
pytest tests/test_app_input_permissions.py
```

`AppInputBus` filters audience / footstep events per manifest `inputs`
allowlist (ADR 0019). Undeclared subscriptions are refused and logged.
See [docs/apps/input.md](../docs/apps/input.md).

## Audience steering + session replay (slice 4)

Opt-in per scenario (`lumur_audience`). Core emits presence / zone /
gathering; the bridge steers Story Stage only when opted in.

```bash
pytest tests/test_audience_steering.py
```

See [docs/bridge/audience-steering.md](../docs/bridge/audience-steering.md) and
[docs/bridge/replay.md](../docs/bridge/replay.md).

## Live calibration and scan

See [docs/companion/calibration.md](../docs/companion/calibration.md) and
[docs/companion/room-scan.md](../docs/companion/room-scan.md).