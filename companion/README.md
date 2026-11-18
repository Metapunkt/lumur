# Lumur companion

Python/OpenCV companion for structured-light calibration and room scan.
Godot owns rendering; this process owns capture, Gray-code decoding,
calibration JSON, and versioned room packages
([ADR 0004](../docs/architectural-decisions/0004-godot-addon-and-python-companion.md),
[ADR 0012](../docs/architectural-decisions/0012-versioned-room-package.md)).

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

Presets: `empty_room`, `room_with_box`, `noisy_room`. See
[docs/companion/simulation.md](../docs/companion/simulation.md) and
[docs/companion/room-scan.md](../docs/companion/room-scan.md).

## Live calibration and scan

See [docs/companion/calibration.md](../docs/companion/calibration.md) and
[docs/companion/room-scan.md](../docs/companion/room-scan.md).