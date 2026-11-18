# Tracking and footsteps

Pose on the raw webcam frame, predicted-frame subtraction as a false-detection
mask, multi-person tracking, and ankle→floor footstep events
([ADR 0005](../architectural-decisions/0005-pose-and-predicted-frame-subtraction.md),
[ADR 0006](../architectural-decisions/0006-room-as-os-runtime.md),
[ADR 0014](../architectural-decisions/0014-udp-json-event-transport.md),
[PRD-001](../product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md)).

## Pipeline

1. **Lock exposure / WB** (sim: always locked).
2. **Push** each outgoing projector frame into a ring buffer (latency match).
3. **Grab** the raw camera frame (never a subtracted image).
4. **Detect** pose with a pluggable backend.
5. **Subtract:** predict the camera view of projected content from room
   correspondence + radiometric model; build a bright-agreement mask; reject
   detections whose upper-body keypoints sit on that mask (painted people).
6. **Track** with a lightweight ByteTrack-style associator (stable ids).
7. **Footsteps:** ray-cast ankles through the camera onto the scanned floor
   plane; emit events on contact heuristics.
8. **Audience (optional):** project tracks onto floor u/v; emit `presence`,
   `zone_enter` / `zone_leave`, and `gathering` for named floor zones
   ([PRD-002](../product-requirements/PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md)
   slice 4). Story steering is **not** here — see
   [audience-steering.md](../bridge/audience-steering.md).
9. **Send** events as local UDP JSON to Godot (default `127.0.0.1:8765`).

## Quick start (sim)

```bash
cd companion
pip install -e ".[dev]"

# Stream footsteps from animated walkers (no hardware)
lumur-track --scene room_with_walkers --people 2 --frames 120

# Inject a projected silhouette and exercise the subtraction mask
lumur-track --project-silhouette --no-send --frames 60
```

Preset `room_with_walkers` includes two articulated figures. Or attach people
to any scene:

```python
from lumur.sim import SimRig, default_crossing_people
rig = SimRig.from_scene_path("empty_room", latency_frames=2, n_people=3)
```

## Pose backends

| Backend | Install | Role |
| --- | --- | --- |
| `oracle` / `sim` | (built-in) | Projects ground-truth joints from `PeopleSim`; supports noise and injected false detections. **Default for tests.** |
| `mediapipe` | `pip install -e ".[pose]"` | Optional real detector. |
| `yolo` | `pip install -e ".[yolo]"` | Optional YOLO-pose. |

```python
from lumur.track import create_pose_detector, OraclePoseDetector
det = create_pose_detector("oracle", joint_records_fn=rig.ground_truth_joints)
```

MediaPipe / YOLO are **not** required dependencies.

## Radiometric calibration + subtraction

```python
from lumur.track import PredictedFrameSubtractor, calibrate_radiometric

radio = calibrate_radiometric(predict_fn, capture_fn, projector_size=(64, 48))
sub = PredictedFrameSubtractor.from_sim_ground_truth(
    gt, ambient=5.0, exposure=1.0, gamma=2.2,
    radiometric=radio, latency_frames=2,
)
sub.push_projector_frame(pattern)
result = sub.compare(camera_bgr)
# result.projected_mask → filter detections
```

Only **bright** agreement counts as projected content, so faintly lit floors
do not erase real ankles.

## Footstep events

```json
{
  "type": "footstep",
  "person_id": 1,
  "foot": "left",
  "position_room": [0.12, 0.02, 0.55],
  "position_floor": [0.12, 0.55],
  "timestamp": 3.41,
  "confidence": 0.99
}
```

`position_floor` is metres along floor u/v axes (default world +X / +Z).
Transport envelope: see [ADR 0014](../architectural-decisions/0014-udp-json-event-transport.md)
and [ripples.md](../godot/ripples.md).

## Audience events

Core package `lumur.audience` derives presence / zone / gathering from the
same floor frame. Attach an `AudienceDetector` to `TrackingPipeline`:

```python
from lumur.audience import AudienceDetector, FloorZone
from lumur.track import TrackingPipeline

zones = [FloorZone.rect("left", -1.0, -0.2, 0.2, 0.9)]
pipeline = TrackingPipeline(
    ...,
    audience_detector=AudienceDetector(zones=zones),
)
# result.audience_events → presence / zone_enter / …
```

These events always may drive ambience and ripples. Mapping them onto
Story Stage beats / choices requires an opted-in `lumur_audience` scenario
section in the bridge.

## Tests

```bash
cd companion
pytest tests/test_tracking.py tests/test_audience_steering.py -q
```

Coverage: radiometric fit, prediction accuracy, silhouette rejection,
stable IDs for 2–4 crossing walkers, footstep position tolerance, UDP e2e
into a Python mock of the Godot receiver; audience opt-in / debounce /
replay via the bridge tests.

## Limitations

- Sim people are capsules, not skinned meshes; oracle pose is exact (plus optional noise), not a neural net.
- Single-camera occlusion can hide joints; identity swaps remain an accepted risk (ADR 0005).
- Radiometric model is a global affine — not a full projector falloff map.
- Hardware validation of latency and false-trigger rate is still pending.

## Licence

Companion source: MIT. This document: CC BY-SA 4.0.
