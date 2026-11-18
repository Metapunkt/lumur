# Story Stage on Lumur surfaces (`lumur_synesyn`)

PRD-002 slice 3: map Synesyn Story Stage layers onto Lumur surface roles and
project them through existing paint mode. Lumur core stays independent —
all Story Stage code lives in the optional `lumur_synesyn` bridge
([ADR 0009](../architectural-decisions/0009-standalone-with-synesyn-bridge.md),
[ADR 0015](../architectural-decisions/0015-single-lumur-synesyn-bridge.md)).

Hub generation (slice 2): [synesyn.md](synesyn.md). Audience steering and
Story Log replay are slice 4 — not in this document.

## What lands where

| Story Stage layer | Default Lumur surface | Notes |
| --- | --- | --- |
| Backdrop (`vis_story` / background) | `wall_1` | Main wall; falls back to `wall_2`, then `floor` |
| Characters / portraits / sprites | `wall_2` | Side wall; falls back to `wall_1`, then `floor` |
| FlashHead / talking clips (`.ogv`) | `wall_2` | Same preference chain as characters; crossfades over portrait |
| Captions / dialogue text | `wall_1` (lower safe band) | Wall region via safe area, not a separate plane |
| Ambience / ripples | `floor` | Presence / footsteps may still drive PRD-001 ripples |

Mapping is by **role name**, never hard-coded projector UV (REQ-002-009).

## Layout (scenario-configurable)

Optional scenario section (Synesyn-style dict after section parse):

```text
[LUMUR_LAYOUT]
backdrop: wall_1
character: wall_2
caption: wall_1
ambience: floor
```

Or JSON / host scenario dict:

```json
{
  "lumur_layout": {
    "backdrop": "wall_2",
    "character": "wall_1",
    "ambience": "floor",
    "safe_areas": {
      "caption": {"left": 0.05, "right": 0.05, "top": 0.72, "bottom": 0.04}
    }
  },
  "vis_story": {"enabled": "true"}
}
```

Accepted section keys: `lumur_layout`, `lumur_story_stage`, `lumur_surfaces`.
Every other section (`vis_story`, `lull_protocol`, `lumur_audience`, …) is
**ignored** by the layout reader without breaking projection (REQ-002-010).
Scenarios with no Lumur section keep the defaults above — authored loops, no
forced slideshow / lull from Lumur’s side.

When a preferred surface is missing from the room package, the bridge walks
the preference chain and skips the layer only if nothing remains.

## Projection path

1. A **layer source** produces a snapshot (backdrop / character / clip /
   caption / ambience frames).
2. **Layout** resolves each layer → surface role for the current room.
3. **Compose** aspect-fits content into the surface texture, applies safe
   areas, and handles cut / crossfade transitions (clip over character;
   caption band over backdrop).
4. **Paint mode** samples the texture through the exported correspondence
   maps (confidence masking unchanged — see
   [paint-mode.md](../godot/paint-mode.md)).

Live path (workshop): Godot `LumurStoryStageProjector` + optional
`LumurStoryStageObserverSource` reading a Synesyn `story_stage` tree
non-invasively (`%Background`, portrait sprite, `VideoStreamPlayer`,
`%DialogLine`). No edits to `Metapunkt/Synesyn`.

Headless path (CI): Python `StubStoryStageSource` →
`project_from_source` → reference painter → sim projector→camera.

## Layout (code)

| Piece | Location | Role |
| --- | --- | --- |
| Layout + fallback | `companion/lumur_synesyn/story_stage_layout.py` | Role chains, scenario parse |
| Stub source | `…/story_stage_layers.py` | Known colours / frames for tests |
| Compose | `…/story_stage_compose.py` | Aspect fit, safe areas, crossfade |
| Project | `…/story_stage_project.py` | Snapshot → `PaintAssignment`s |
| Godot layout / host / projector | `addons/lumur_synesyn/story_stage_*.gd` | Runtime seam |
| Stub + observer sources | `stub_…gd`, `story_stage_observer_source.gd` | Mock vs live observe |

`LumurStoryStageHost` mirrors Synesyn’s host contract (ADR 0029) without
subclassing `StoryStageHost`, so the bridge loads without `story_stage` /
`synesyn_core`. When those addons are installed, set `stage.host` to a
`LumurStoryStageHost` (or thin subclass) before `add_child`.

## Video clips and transitions

- Story Stage rung-4 / FlashHead clips are Theora `.ogv` (Synesyn ADR 0030).
- The bridge does **not** re-implement FlashHead; it consumes textures /
  players the stage already shows.
- Observer: if a `VideoStreamPlayer` is playing under the stage, that layer
  maps as `clip` onto the character surface chain.
- Python stub: clip appears after `clip_start_s` and crossfades from the
  character colour over `clip_fade_s`.
- Godot older than Synesyn’s 4.7 target: degrade to still portrait frames;
  projection continues.

## Tests

```bash
cd companion
pytest tests/test_story_stage_surfaces.py
```

Asserts: default + fallback mapping; unknown scenario sections ignored;
stub layers land on the intended surfaces through paint + sim camera
chromaticity; core `addons/lumur` / `lumur.generate` stay Synesyn-free.

Godot headless for this slice is optional — the Python reference painter is
the guaranteed CI path (same gap as paint-mode.md when `godot` / `xvfb` are
absent). A Godot projector path exists for workshops when the binary is
available.

## Synesyn-side touchpoints (do not implement here)

Read-only against `Metapunkt/Synesyn`. Changes, if any, belong on
Synes-bot’s fork only.

| Touchpoint | Why | Status for slice 3 |
| --- | --- | --- |
| Optional `supports(&"lumur_surfaces")` (or similar) on `StoryStageHost` | Cleaner capability advertisement for surface mapping | **Optional** — bridge works by observing nodes / host scenario without it |
| Document `[LUMUR_LAYOUT]` beside other scenario sections | Authors discover the mapping section | **Helpful** (docs only); presence-as-opt-in already matches ADR 0027 |
| Per-layer `SubViewport` export hooks on Story Stage | Higher-fidelity layer isolation than observing UI nodes | **Optional** — observer + stub suffice for complete-in-sim |
| No change required to motion ladder, imagery port, or FlashHead | Bridge consumes what the stage already produces | **None required** |

If public contracts already suffice (they do for this slice), **no Synesyn
code change is required**.

## Licence

Companion / addon source: MIT. This document: CC BY-SA 4.0.
