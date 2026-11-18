# App input permissions

PRD-003 slice 2: companion audience events become room input devices on the
existing `lumur.event` bus, with a **per-app allowlist** from the manifest
([ADR 0019](../architectural-decisions/0019-app-input-permissions.md),
[ADR 0014](../architectural-decisions/0014-udp-json-event-transport.md),
[PRD-003](../product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
REQ-003-005–007).

Manifest surface fit: [manifest.md](manifest.md). Audience vocabulary and
optional Story Stage steering: [audience-steering.md](../bridge/audience-steering.md).

## Vocabulary

Unchanged from PRD-002 / ADR 0014:

| Type | Typical payload |
| --- | --- |
| `footstep` | `person_id`, `foot`, `position_floor`, `position_room`, `timestamp` |
| `presence` | `person_ids[]`, `count`, `timestamp` |
| `zone_enter` / `zone_leave` | `person_id`, `zone_id`, `position_floor`, `timestamp` |
| `gathering` | `zone_id` / `cluster_id`, `person_ids[]`, `count` |

Transport stays local UDP JSON. Permissions are an API contract for honest
apps and CI — not a sandbox against a malicious local process.

## Manifest allowlist

```json
"inputs": ["footstep"]
```

- Empty list → display-only (no room events).
- Unknown names → manifest validation error (slice 1 / ADR 0017).
- Only listed types reach the app’s handlers, even if the companion emits more.

Example: ripples (`apps/examples/ripples/`) declares `footstep` only — injected
`zone_enter` / `presence` / `gathering` never appear in its stream.

## Enforcement

Filtering happens in the **runtime fan-out** after UDP decode (or after test
injection):

| Layer | API |
| --- | --- |
| Python companion | `lumur.app.AppInputBus` |
| Godot | `LumurAppInputBus` (+ `LumurRoomRuntime.register_app_inputs`) |

`subscribe(app_id, event_type)` for a type **not** in the allowlist is
**refused and logged** (`undeclared_input`). Unknown apps are refused with
`unknown_app`.

Multiple launched apps each get an independent filtered view. A privileged
**host / launcher** path (`register_host`) may listen for `zone_*` for
zone→app switching (REQ-003-013; [lifecycle.md](lifecycle.md)) without
granting those types to the foreground app. **Paused** apps keep
subscriptions but receive no events (REQ-003-011).

Bridge audience steering (`lumur_synesyn`) remains opt-in per scenario
(REQ-002-011). App input permissions do **not** grant story steering.

## Fitted surface coordinates

When an app’s room fit bound a floor surface, positioned deliveries
(`footstep`, `zone_enter`, `zone_leave`) include:

| Field | Meaning |
| --- | --- |
| `surface_key` | Manifest surface key (e.g. `floor`) |
| `surface_id` | Concrete plane id from the room package |
| `position_surface` | Same floor u/v metres as `position_floor` |

Apps must not receive (or invent) projector pixel rects / raw UV placement
for input — placement remains the runtime’s job (ADR 0017).

## Python

```python
from lumur.app import AppInputBus, fit_app_to_room, load_app_manifest, RoomServices

manifest = load_app_manifest("apps/examples/ripples/lumur.app.json")
room = RoomServices.load("/tmp/sim-room")
fit = fit_app_to_room(manifest, room)

bus = AppInputBus()
bus.register_app(manifest, fit=fit)
assert bus.subscribe(manifest["id"], "footstep")
assert not bus.subscribe(manifest["id"], "zone_enter")  # refused + logged

bus.inject({"type": "footstep", "position_floor": [0.1, 0.2], "timestamp": 1.0, ...})
bus.inject({"type": "zone_enter", "zone_id": "left", "timestamp": 1.1, ...})
assert bus.streams()[manifest["id"]][0]["type"] == "footstep"
```

Replay a recorded session for identical per-app streams:

```python
stream_a = bus.streams()
stream_b = bus.replay(recorded_events)
assert stream_a == stream_b
```

## Godot

```gdscript
var bus := LumurAppInputBus.new()
bus.register_app(manifest, fit_result)
bus.subscribe(manifest.app_id(), "footstep")  # true
bus.subscribe(manifest.app_id(), "zone_enter")  # false + warning
bus.inject({"type": "footstep", "position_floor": [0.2, 0.3], "timestamp": 1.0})
# or bind_receiver(lumur_event_receiver) for live UDP
```

`LumurRoomRuntime` creates an `InputBus` child and exposes
`register_app_inputs` / `subscribe_app_input` / `inject_app_event`.

Headless script: `demo/scripts/headless_app_input.gd`.

## Tests

```bash
cd companion
pytest tests/test_app_input_permissions.py
```

Covers: declared vs undeclared delivery, refused subscriptions, multiple
apps with different allowlists, fitted surface coordinates, deterministic
ordering, walking figures in the sim, and replay identity. No hardware.

## Licence

Source code MIT. This document CC BY-SA 4.0.
