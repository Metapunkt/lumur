# Footstep ripples (Godot)

Room-input footstep events from the companion drive expanding rings on the
floor surface through paint-mode targeting
([ADR 0005](../architectural-decisions/0005-pose-and-predicted-frame-subtraction.md),
[ADR 0006](../architectural-decisions/0006-room-as-os-runtime.md),
[ADR 0014](../architectural-decisions/0014-udp-json-event-transport.md),
[tracking.md](../companion/tracking.md)).

## Pieces

| Script | Role |
| --- | --- |
| `addons/lumur/event_receiver.gd` | UDP JSON listener (`LumurEventReceiver`) |
| `addons/lumur/ripple_layer.gd` | Stamps rings into a floor overlay texture |
| `addons/lumur/paint_mode.gdshader` | Composites `ripple_tex` on the floor surface id |
| `demo/scenes/ripple_demo.tscn` | Paint + receiver + ripples |

Apps never call OpenCV or pose models. They subscribe to footstep signals.

## Run with the companion

```bash
# Terminal A — export paint assets if needed
cd companion && lumur-export-godot /tmp/sim-room

# Terminal B — Godot ripple demo
export LUMUR_GODOT_ASSETS=/tmp/sim-room/godot
godot --path . demo/scenes/ripple_demo.tscn

# Terminal C — sim walkers sending UDP events
cd companion && lumur-track --scene room_with_walkers --people 2
```

Default port: **8765** on localhost.

## Event shape

Envelope (ADR 0014):

```json
{"schema":"lumur.event","schema_version":"1.0","event":{
  "type":"footstep",
  "person_id":1,
  "foot":"left",
  "position_room":[0.1,0.0,0.4],
  "position_floor":[0.1,0.4],
  "timestamp":1.23,
  "confidence":0.99
}}
```

GDScript:

```gdscript
receiver.footstep.connect(func(ev):
    print(ev["person_id"], ev["position_floor"])
)
# Or inject without the network (tests / demos):
$Runtime/Ripples.inject_footstep(Vector2(0.2, 0.1))
```

## Headless check

Godot `--headless` uses the dummy renderer (no canvas shaders). Prefer
`xvfb-run` as in [paint-mode.md](paint-mode.md), or the Python UDP mock in
`companion/tests/test_tracking.py` (guaranteed CI path).

```bash
xvfb-run -a godot --path . \
  --display-driver x11 --rendering-driver opengl3 \
  --script res://demo/scripts/headless_ripple_render.gd \
  -- --assets=/tmp/sim-room/godot --out=/tmp/ripple.png \
     --foot=0.0,0.0;0.4,-0.2
```

## Graceful degradation

If the companion stops or UDP is silent, paint continues — the room remains a
mapped artwork ([REQ-001-007](../product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md)).
Ripples are additive overlay; they do not own the projector.

## Limitations

- Floor UV mapping from `position_floor` uses a fixed span heuristic for the
  first milestone; a later pass can use plane extents from the room package.
- Overlay resolution equals the projector map (often 64×48 in sim).
- No multi-app compositor yet (ADR 0006).

## Licence

Addon and demo source: MIT. This document: CC BY-SA 4.0.
