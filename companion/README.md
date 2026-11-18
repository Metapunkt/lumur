# Lumur companion

Python/OpenCV companion for structured-light calibration. Godot owns
rendering; this process owns capture, Gray-code decoding, and calibration
JSON ([ADR 0004](../docs/architectural-decisions/0004-godot-addon-and-python-companion.md)).

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

## Live calibration

See [docs/companion/calibration.md](../docs/companion/calibration.md).