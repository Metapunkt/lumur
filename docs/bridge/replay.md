# Session recording and Story Log replay

PRD-002 slice 4: record a room session and replay it headlessly in the Lumur
sim so Story Stage stub output and paint digests match
([ADR 0015](../architectural-decisions/0015-single-lumur-synesyn-bridge.md)).
Audience steering: [audience-steering.md](audience-steering.md).

## What a session contains

Schema `lumur.session` v1.0:

| Field | Role |
| --- | --- |
| `room_package_ref` | Local room package path (and/or Hub artifact id) |
| `room_artifact_id` | Optional Hub `json.lumur_room` id |
| `scenario` | Host scenario dict (incl. `lumur_audience` / layout) |
| `audience_events` | Ordered presence / zone / gathering / footstep payloads |
| `stage_actions` | Authoritative steered + ambience actions applied live |
| `story_log` | Synesyn Story Log entries (array) |
| `story_log_ref` | Path to on-disk log when loaded from files |
| `story_log_provenance` | Synesyn `.provenance.json` sidecar (`synesyn_provenance_v2`) |
| `paint_digests` / `state_fingerprint` | Determinism witnesses |

Together with the room package, this is enough to replay dialogue pacing and
surface layout without live models or hardware (REQ-002-015).

## Story Log shape (Synesyn-compatible)

On-disk log = JSON **array** of entries (not wrapped), matching Synesyn’s
playback fixture:

```json
[
  {
    "sender": "Narrator",
    "message": "The room waits.",
    "timestamp": "2026-09-23 18:00:00",
    "timestamp_us": 1000000
  }
]
```

Provenance sidecar: `<stem>.provenance.json` with `schema:
synesyn_provenance_v2` and optional `stage` block (scenario key, cast, …).
Lumur does not require Hub to replay a local pair.

## Record

```python
from lumur_synesyn.session_record import SessionRecorder, save_session

rec = SessionRecorder(room_package_ref=str(room_dir), scenario=scenario)
rec.record_audience_batch(audience_events)
rec.record_actions(stage_actions)
rec.load_story_log_files("story_log_playback_fixture.json")  # optional
recording = rec.finalize(paint_digests=digests, state_fingerprint=fp)
save_session(recording, "session.json")
```

## Replay (deterministic)

```python
from lumur_synesyn.replay import replay_session

r1 = replay_session(recording, room_package_dir=room_dir, texture_size=(32, 32))
r2 = replay_session(recording, room_package_dir=room_dir, texture_size=(32, 32))
assert r1.state_fingerprint == r2.state_fingerprint
assert r1.paint_digests == r2.paint_digests
```

Replay path:

1. Load scenario + Story Log into `MockStoryStageReceiver` (playback host
   pattern, analogous to Synesyn’s `StoryLogPlaybackHost`).
2. Re-apply recorded `stage_actions` (authoritative) so steering matches the
   live session.
3. Project stub Story Stage layers through paint mode onto the room package
   (same path as [story-stage.md](story-stage.md)).

Re-deriving actions from `audience_events` alone is available via
`replay_session_from_events` for debounce / opt-in tests; production replay
prefers the recorded action stream.

## Hub provenance (REQ-002-014)

When Hub is available:

```python
from lumur_synesyn.session_record import register_session_with_hub

register_session_with_hub(client, recording, room_package_dir=room_dir)
```

Registers `json.lumur_session` (and optionally `json.lumur_room`) via the
generic substrate artifact API. Official type documentation remains a
Synesyn-side touchpoint (see [synesyn.md](synesyn.md)).

## Tests

```bash
cd companion
pytest tests/test_audience_steering.py -k replay
```

## Synesyn-side touchpoints (do not implement here)

| Touchpoint | Why | Status |
| --- | --- | --- |
| Document / accept `json.lumur_session` beside `json.lumur_room` | Hub discovery of recorded sessions | **Helpful** (generic API works today) |
| No change to Story Log JSON or provenance v2 | Lumur mirrors the public player contract | **None required** |
| Optional Hub download for remote room packages | Remote replay without co-located files | Same as slice 2 content-route touchpoint |

## Licence

Companion / addon source: MIT. This document: CC BY-SA 4.0.
