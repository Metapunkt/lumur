# Camera–projector calibration

First slice of [PRD-001](../product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md):
Gray-code structured light, optional checkerboard, optional metric scale
from one measured distance. Patterns are shown with an OpenCV fullscreen
window ([ADR 0010](../architectural-decisions/0010-opencv-fullscreen-pattern-display.md)).

## Hardware setup

1. Mount one webcam and one projector so the camera sees the projected area.
2. Set the OS to extend the desktop onto the projector at its native
   resolution.
3. Lock room lighting as much as practical. The companion will attempt to
   lock camera exposure and white balance (backend-dependent).

## Install

```bash
cd companion
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Run (checkerboard)

Print a checkerboard, place it in view, note interior corner counts
(for example 9×6) and square size in metres:

```bash
lumur-calibrate \
  --camera 0 \
  --projector-width 1920 --projector-height 1080 \
  --monitor 1 \
  --board 9x6 --square-m 0.025 \
  --settle-ms 250 \
  -o room/calibration.json \
  --correspondence-out room/correspondence.npz
```

Inspect the printed residual summary. `worst_region.bbox` is in camera
pixels; re-check alignment there as well as at the centre.

## Run (no board, scale from a tape measure)

Pick two points on a mostly planar surface visible to the camera, measure
the distance between them, and pass their camera pixel coordinates:

```bash
lumur-calibrate \
  --camera 0 \
  --projector-width 1920 --projector-height 1080 \
  --monitor 1 \
  --distance-m 0.80 \
  --point-a 320,240 --point-b 900,260 \
  -o room/calibration.json
```

Rendering through the projector does not require metric scale; the
distance only supplies units when physics needs them (ADR 0003).

## Calibration JSON schema (`lumur.calibration` v1.0)

| Field | Meaning |
| --- | --- |
| `schema` | Always `"lumur.calibration"`. |
| `schema_version` | `"1.0"` for this slice. |
| `created_at` | UTC ISO-8601 timestamp. |
| `projector_resolution` | `[width, height]` of the projected patterns. |
| `camera` / `projector` | `image_size`, 3×3 `matrix`, `distortion` vector. |
| `stereo.R` / `stereo.T` | Rotation and translation from camera to projector. |
| `stereo.scale_source` | `"checkerboard"`, `"measured_distance"`, or `"none"`. |
| `stereo.measured_distance_m` | Tape length when `scale_source` is `measured_distance`. |
| `residuals.mean_px` / `rms_px` / `median_px` | Global residual summary in pixels. |
| `residuals.worst_region` | `{bbox: [x0,y0,x1,y1], mean_px, rms_px, count}` — highest-mean tile. |
| `correspondence_valid_fraction` | Fraction of camera pixels with a confident decode. |
| `method` | `"checkerboard"` or `"plane_measured_distance"`. |
| `notes` | Optional free-form block (e.g. AE/AWB lock status). |

Dense correspondence (when requested) is stored beside the JSON as an
`.npz` with arrays `proj_u`, `proj_v`, `confidence`, and `valid`, all
shaped like the camera image. Invalid pixels have `valid == false` and
`confidence == 0`.

## Simulated hardware

When a webcam and projector are unavailable, use the simulated rig
([simulation.md](simulation.md), [ADR 0011](../architectural-decisions/0011-simulated-projector-camera-rig.md)):

```bash
lumur-calibrate \
  --backend sim --scene empty_room \
  --distance-m 1.08 \
  --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o /tmp/sim-calibration.json
```

## What this slice does not do

Godot rendering, room meshing, paint-the-room, and footstep ripples are
later PRD-001 work. This package is the calibration driver only.