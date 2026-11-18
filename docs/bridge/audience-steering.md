# Opt-in audience steering (`lumur_synesyn`)

PRD-002 slice 4: map room audience events onto Story Stage inputs **only**
when a scenario opts in. Lumur core always emits the event vocabulary;
steering lives in the optional bridge
([ADR 0009](../architectural-decisions/0009-standalone-with-synesyn-bridge.md),
[ADR 0014](../architectural-decisions/0014-udp-json-event-transport.md),
[ADR 0015](../architectural-decisions/0015-single-lumur-synesyn-bridge.md)).

Story Log / session replay: [replay.md](replay.md). Story Stage surfaces:
[story-stage.md](story-stage.md). Tracking: [tracking.md](../companion/tracking.md).

## Opt-in (REQ-002-011)

Steering is enabled only when the scenario declares an audience section:

```text
[LUMUR_AUDIENCE]
enabled: true
min_dwell_s: 1.5
debounce_s: 0.8
```

Or as a host / JSON scenario dict:

```json
{
  "lumur_audience": {
    "enabled": true,
    "min_dwell_s": 1.5,
    "debounce_s": 0.8,
    "zones": [
      {"zone_id": "left", "kind": "rect", "u_min": -1.0, "u_max": -0.2, "v_min": 0.2, "v_max": 0.9}
    ],
    "zone_actions": {
      "left": {"action": "choose_option", "option_index": 0},
      "right": {"action": "choose_option", "option_index": 1}
    },
    "gathering_action": "advance_beat",
    "intensity_parameter": "intensity"
  }
}
```

Absent the section (or `enabled: false`), `presence` / `zone_*` /
`gathering` / `footstep` **must not** advance story or director state.
They may still drive ambience and PRD-001 ripples (REQ-002-012).

If Synesyn’s scenario loader does not yet whitelist `LUMUR_AUDIENCE`, the
section arrives as free text (`lumur_audience_text`). The bridge treats a
non-empty text body as opt-in (same ADR 0027 presence-as-feature pattern).

## Event vocabulary (REQ-002-013)

| Event | Core emitter | Typical payload |
| --- | --- | --- |
| `presence` | `AudienceDetector` | `person_ids[]`, `count`, `timestamp` |
| `zone_enter` / `zone_leave` | `AudienceDetector` | `person_id`, `zone_id`, `position_floor`, `timestamp` |
| `gathering` | `AudienceDetector` | `zone_id` or `cluster_id`, `person_ids[]`, `count` |
| `footstep` | `FootstepDetector` (PRD-001) | existing `lumur.event` footstep |

Zones are rectangles or polygons in **floor surface coordinates** (same
u/v frame as footstep `position_floor`). Transport remains ADR 0014 UDP
JSON (`schema: lumur.event`).

## Safety: dwell + debounce

Passers-by must not steer the story:

- **Minimum dwell** (`min_dwell_s`, default 1.5 s) inside a zone before a
  zone action fires.
- **Debounce** (`debounce_s`, default 0.8 s) per zone (and for gathering)
  so repeated edge triggers collapse.
- Leaving before the dwell completes records a rejection
  (`dwell_too_short`) and does not choose an option.

## Bridge → Story Stage

When opted in, the bridge maps events to:

| Source | Stage action |
| --- | --- |
| Zone dwell | `choose_option` / `advance_beat` / `set_parameter` (per `zone_actions`) |
| Gathering (held) | `gathering_action` (default `advance_beat`) |
| Presence count | `set_parameter` intensity (scaled, clamped 0..1) |
| Footstep | small intensity bump (never a choice by itself) |

Headless / CI uses `MockStoryStageReceiver` (Python stand-in for Godot /
Story Stage). Live workshops use `LumurAudienceSteering` +
`LumurStoryStageHost` in `addons/lumur_synesyn/`.

## Metaprompt summary

For opted-in scenarios the bridge exposes a structured audience state
(and short prose) suitable for scenario metaprompts:

```python
bridge.audience_state_for_metaprompt(detector.state)
# {"enabled": True, "text": "Audience: 2 present …", "state": {...}, ...}
```

Exact prompt wording stays scenario-owned; Lumur owns the schema.

## Layout (code)

| Piece | Location |
| --- | --- |
| Zones + detector | `companion/lumur/audience/` |
| Tracking hook | `TrackingPipeline.audience_detector` |
| Config / opt-in | `companion/lumur_synesyn/audience_config.py` |
| Steering + debounce | `…/audience_steering.py` |
| Mock Stage receiver | `…/mock_story_stage.py` |
| Godot steering | `addons/lumur_synesyn/audience_steering.gd` |
| Godot UDP signals | `addons/lumur/event_receiver.gd` |

## Tests

```bash
cd companion
pytest tests/test_audience_steering.py
```

Covers: opt-out never steers; opt-in zone choice; dwell rejects passers-by;
walking figures in the sim; UDP → Python Godot mock; Hub session
registration; replay determinism (see [replay.md](replay.md)).

## Synesyn-side touchpoints (do not implement here)

| Touchpoint | Why | Status |
| --- | --- | --- |
| Whitelist `[LUMUR_AUDIENCE]` in `scenario_loader.gd` → `scenario["lumur_audience"]` dict | First-class key:value parse (ADR 0027) | **Needed** for clean authoring; bridge already accepts `lumur_audience_text` fallback |
| Document section beside `PLAYER_AUTO_INPUT` / `VIS_STORY` | Authors discover opt-in | **Helpful** (docs only) |
| No change required to Story Stage host API for v1 | Bridge drives choices / beats / parameters at the host boundary | **None required** |

Changes, if any, belong only on Synes-bot’s fork — never `Metapunkt/Synesyn`
main from this workstream.

## Licence

Companion / addon source: MIT. This document: CC BY-SA 4.0.
