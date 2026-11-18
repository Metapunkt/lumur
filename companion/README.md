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

## Live calibration and scan

See [docs/companion/calibration.md](../docs/companion/calibration.md) and
[docs/companion/room-scan.md](../docs/companion/room-scan.md).