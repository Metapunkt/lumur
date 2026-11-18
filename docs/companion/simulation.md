# Simulated projector–camera rig

Hardware-free development harness for the Python companion
([ADR 0011](../architectural-decisions/0011-simulated-projector-camera-rig.md)).
A virtual room, projector, and webcam plug into the same capture loop as a
real OpenCV display and camera, so Gray-code capture → decode → calibration
can run headlessly against ground truth.

## Quick start

```bash
cd companion
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# End-to-end on a preset scene (no webcam / projector required)
lumur-calibrate \
  --backend sim --scene empty_room \
  --distance-m 1.08 \
  --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o /tmp/sim-calibration.json
```

Projector resolution defaults come from the scene when `--backend sim`.
Settle time defaults to 0 ms for the sim.

List built-in presets from Python:

```python
from lumur.sim import list_presets
print(list_presets())  # empty_room, room_with_box, noisy_room, room_with_walkers
```

## Using the sim as a device backend

```python
from lumur.capture.backends import open_devices
from lumur.capture.loop import CaptureLoop
from lumur.patterns.graycode import generate_graycode_sequence

devices = open_devices("sim", scene="room_with_box")
seq = generate_graycode_sequence(*devices.projector_size)
loop = CaptureLoop(
    devices.camera,
    devices.display,
    settle_s=0.0,
    discard_warmup_grabs=0,
)
captures = loop.capture_sequence(seq)
gt = devices.rig.ground_truth()
devices.close()
```

`SimDisplay.show` updates the virtual projector framebuffer;
`SimCamera.grab` re-renders the room under that pattern (BGR uint8, matching
OpenCV webcam frames). Exposure / white-balance lock succeeds immediately and
records a `simulated camera` note.

## Scene format

Scenes are JSON (or YAML if [PyYAML](https://pyyaml.org/) is installed).
Built-in presets live under `companion/lumur/sim/presets/`.

| Block | Fields |
| --- | --- |
| `name` / `seed` | Optional labels; camera `seed` drives sensor noise. |
| `room.type` | `"axis"` (default) builds floor + back wall + optional side walls / ceiling. |
| `room.width` / `depth` / `height` | Metres; floor at `y = 0`, origin at floor centre. |
| `room.floor_albedo` / `wall_albedo` | Diffuse reflectance in `[0, 1]`. |
| `room.boxes[]` | Axis-aligned boxes: `center`, `size`, optional `albedo`, `name`. |
| `room.occupants[]` | Static person placeholders (AABB stand-ins): `center`, `height`, `radius`. |
| `room.people[]` | Animated articulated walkers: `waypoints`, `speed_m_s`, `height`, `phase_offset`, … See [tracking.md](tracking.md). |
| `room.planes[]` | Alternate explicit planes (`point`, `normal`, `albedo`) when `type` is not `axis`. |
| `projector` | `width`, `height`, `eye`, `target`, optional `fov_y_deg`, `gamma`, `up`, `K`. |
| `camera` | Same pose fields, plus `distortion` (Brown–Conrady), `exposure`, `noise_std`, `ambient`, `blur_sigma`, `seed`. |

World coordinates: +Y up, devices look toward +Z into the room from negative Z.

## What the sim models

- Diffuse floor / walls / boxes / static occupant placeholders.
- Pinhole projector with configurable gamma (digital → linear light).
- Pinhole webcam with radial / tangential distortion, exposure gain,
  additive ambient, Gaussian sensor noise, and optional Gaussian blur.
- Exact ground truth: device intrinsics / extrinsics, per-pixel depth,
  camera→projector correspondences, and stereo `R`/`T` (camera → projector).

## Animated people and latency

`room.people` (or `SimRig(..., n_people=N)`) adds capsule stick figures with
ground-truth joints each frame. `latency_frames` makes the camera observe
projector frame N−k. Exposure / white balance stay locked. Predicted-frame
subtraction, pose, and footsteps live in `lumur.track` —
[tracking.md](tracking.md).

## What it does not model

- Specular materials, colour cross-talk, projector focus falloff, or
  rolling shutter.
- Temporal AE/AWB behaviour of real USB cameras.
- Skinned human meshes or neural pose inside the renderer (oracle pose is
  separate).
- Multi-projector blending.

## Tests

```bash
cd companion
pytest tests/test_sim_e2e.py tests/test_room_scan.py -q
```

The e2e suite runs capture → decode → plane calibration on the sim and
checks decode accuracy, reprojection residuals, retained camera intrinsics,
and essential-matrix pose against ground truth. A noise / ambient stress
case uses the `noisy_room` preset with harsher sensor settings.

Room-scan tests (`test_room_scan.py`) triangulate against ground-truth pose
on `room_with_box`, recover the floor / walls, treat the box as non-planar
or extra surfaces, and check degraded-but-sane confidence on `noisy_room`.
See [room-scan.md](room-scan.md).

**Pose note:** translation direction from plane-only calibration is weakly
constrained on near-planar scenes. Prefer `room_with_box` (or
`--use-sim-gt-pose` on `lumur-scan`) when judging metric depth.

## Licence

Companion source is MIT. This document is CC BY-SA 4.0.
