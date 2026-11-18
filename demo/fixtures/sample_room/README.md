# Sample room fixture

Committed Godot paint assets for the hardware-free demo (`empty_room` sim
preset). Regenerate with:

```bash
cd companion
lumur-calibrate --backend sim --scene empty_room \
  --distance-m 1.08 --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o ../demo/fixtures/sample_room/calibration.json
lumur-scan --backend sim --scene empty_room \
  --calibration ../demo/fixtures/sample_room/calibration.json \
  -o ../demo/fixtures/sample_room
lumur-export-godot ../demo/fixtures/sample_room
```

Then:

```bash
export LUMUR_GODOT_ASSETS=$PWD/demo/fixtures/sample_room/godot
godot --path .
```
