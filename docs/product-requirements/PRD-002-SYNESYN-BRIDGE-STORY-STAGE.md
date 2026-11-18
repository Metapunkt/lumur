---
id: PRD-002
title: Surface generation, Synesyn bridge, and Story Stage on Lumur
status: draft
version: "0.2"
owner: Ayodele Arigbabu
last_reviewed: 2026-11-18
primary_users: [installer, author, visitor, workshop facilitator]
supersedes: null
---

# Surface generation, Synesyn bridge, and Story Stage on Lumur

## Problem and outcome

PRD-001 leaves a mapped, paintable room with footstep ripples, complete in
sim, and explicitly postpones generative textures and Synesyn. Authors who
want AI surface treatments should be able to generate against the real room
**with or without** Synesyn. Separately, when Synesyn *is* present, a thin
bridge should let Story Stage leave the screen: characters, backdrops and
ambience map onto real surfaces, and — only when a scenario opts in —
audience movement can steer the story. Lumur remains a standalone room
runtime ([ADR 0009](../architectural-decisions/0009-standalone-with-synesyn-bridge.md));
people who want interactive walls never need the Hub or the agent stack.

## Users and jobs

- **Author (standalone):** When the room is scanned, they need to generate
  surface textures through ComfyUI using Lumur presets sized to each
  surface, so that they can invent materials without Synesyn, a Hub, or
  SynPunkt.
- **Author (Synesyn-connected):** When SynPunkt workflow presets and Hub
  provenance are available, they need the same generation job to go through
  the Hub so that renders carry artifact provenance and can be replayed.
- **Workshop facilitator:** When running a Story Catalyst scenario in a
  mapped room, they need Story Stage layers (backdrop, characters /
  portraits / FlashHead clips, ambience) mapped onto surfaces by role, so
  that deliberation happens in the space rather than on a monitor.
- **Visitor:** When walking the floor during a scenario that opts into
  audience steering, they need their presence and footsteps to influence
  the story; otherwise their movement should only feed ambience (and the
  existing ripples), so that ordinary installations stay calm.
- **Installer / CI:** When validating without hardware, they need the full
  flows to run headlessly in the Lumur sim against a ComfyUI stub and,
  when testing the bridge, a Synesyn Hub mock.

## Success measures

- Lumur core exposes a surface-generator interface; enabling or disabling
  Synesyn does not change how paint mode consumes generated textures.
- With only the standalone ComfyUI provider configured, a tagged Lumur
  workflow preset produces an image sized to a named surface role; that
  image lands on the surface through existing paint mode; projection
  continues if ComfyUI is absent, slow, or fails.
- With the Synesyn Hub provider configured (via `lumur_synesyn`), the same
  generator call submits `SynesynRenderRequestV1` to Hub `/render/submit`,
  selects SynPunkt `json.workflow` presets tagged
  `lumur:surface_role=<role>` (optional scoping tags), and maps returned
  `image.generated` artifacts onto surfaces with provenance retained.
- Story Stage layers appear on the correct surface roles in sim without
  requiring a physical projector.
- Scenarios without an audience-steering metaprompt section never advance
  story state from presence / zone / gathering / footstep events; those
  events may still drive ambience and ripples.
- A registered room package plus a Story Log replay the same surface
  layout and dialogue pacing in the Lumur sim.
- All acceptance for this PRD is automated against the sim (and mocks);
  no physical hardware is required to mark a slice complete-in-sim.

## Scope

### In scope

- A **generator / provider interface** in Lumur core (Godot), used by paint
  mode and any later app that wants surface textures. Providers are
  pluggable; the renderer never waits on them ([ADR 0008](../architectural-decisions/0008-comfyui-asynchronous.md),
  refined by [ADR 0016](../architectural-decisions/0016-pluggable-surface-generators.md)).
- A **first-class standalone ComfyUI provider** in Lumur (not in the
  Synesyn bridge): direct ComfyUI API, Lumur-owned workflow presets,
  surface-aware requests (size / aspect, optional mask / depth / normal
  control images). Request and preset shapes stay aligned with Synesyn’s
  where sensible so presets can move between providers, but core has
  **no Synesyn dependency**.
- One Godot bridge addon, **`lumur_synesyn`**, depending on
  `synesyn_core`, as the **only** Synesyn integration surface
  ([ADR 0015](../architectural-decisions/0015-single-lumur-synesyn-bridge.md)).
  It owns:
  - an optional **Synesyn Hub generator provider**
    (`SynesynRenderRequestV1` → `/render/submit`, SynPunkt presets,
    provenance artifacts);
  - Story Stage hosting / layer-to-surface mapping;
  - room-package registration as a Hub artifact;
  - Story Log + room package replay wiring;
  - forwarding of opt-in audience-steering events into scenario
    metaprompts.
- Mapping of Story Stage layers onto Lumur surface roles:
  - backdrop → primary wall / designated backdrop role;
  - characters / portraits / FlashHead clips → portrait or character
    roles;
  - ambience → floor and/or secondary walls as the scenario declares.
- Audience movement steering **opt-in per scenario**, enabled only when
  the scenario’s metaprompt / scenario sections incorporate it; otherwise
  presence and footsteps drive ambience (and PRD-001 ripples) only.
- Event vocabulary for the room → story seam: `presence`, `zone_enter`,
  `zone_leave`, `gathering`, `footstep` (see Requirements).
- Headless verification in the Lumur sim, with a ComfyUI stub for the
  standalone provider and a Synesyn Hub mock for bridge slices.

### Out of scope

- Changing PRD-001 calibrate / paint / ripple behaviour, except consuming
  generated textures through the existing paint path.
- Folding Lumur into the Synesyn repository, or requiring Hub / agent
  stack for ordinary wall painting.
- Implementing FlashHead / motion-ladder rung 4 inside Lumur; the bridge
  consumes clips Story Stage already produces when the host and scenario
  grant that rung ([Synesyn ADR 0030](https://github.com/Metapunkt/Synesyn/blob/main/docs/architectural-decisions/0030-story-stage-motion-and-imagery-layers.md)).
- Embodied Thinking Map / workshop accept–reject–defer zones (scratchpad
  idea; later PRD).
- Multi-projector blending, view-dependent rendering, Lumur OS appliance
  image ([ADR 0007](../architectural-decisions/0007-lumur-os-as-appliance.md)).
- Edits to `Metapunkt/Synesyn` main. Any Synesyn-side experiment lands
  only on Synes-bot’s fork, surgically (see Constraints).

## Critical journey

### Standalone generation (no Synesyn)

1. Author has a scanned room package and paint assets (PRD-001).
2. They configure the standalone ComfyUI provider and select a Lumur
   workflow preset for a surface role (for example `wall_1`).
3. Lumur builds a surface-aware request (target size / aspect; optional
   mask, depth, or normal control images derived from the room package)
   and submits it directly to ComfyUI.
4. When the image returns, paint mode applies it to that surface. If
   ComfyUI is missing or the job fails, the last good texture (or solid /
   authored content) remains; projection never stalls.

### Synesyn Hub generation (optional provider)

1. Author has SynPunkt workflow presets tagged
   `lumur:surface_role=<role>` (optional
   `lumur:room=<id>`, `lumur:scenario=<key>`, etc.).
2. With `lumur_synesyn` enabled and Hub reachable, the same generator call
   selects the most specific matching preset, submits
   `SynesynRenderRequestV1` via Hub `/render/submit` (with
   `input_uploads` for control images when needed), and receives
   `image.generated` artifacts with provenance.
3. Paint mode maps the artifact onto the surface. Provenance links
   (render request, workflow, prompt) remain queryable through the Hub.

### Story Stage on surfaces

1. Facilitator starts a Story Catalyst scenario; `lumur_synesyn` supplies
   a `StoryStageHost` and maps stage layers to surface roles.
2. Backdrop, portraits / clips, and ambience appear on the assigned
   surfaces in the sim (and later on the projector).
3. If the scenario opts into audience steering, zone and gathering events
   from the companion influence the metaprompt / director path; otherwise
   those events only affect ambience / ripples.
4. The room package is registered as a Hub artifact. Together with the
   Story Log (and its provenance sidecar), a later session replays the
   performance in the Lumur sim without hardware.

Detailed Synesyn authoring stays in Synesyn’s user guides (SynPunkt Render
tab, Story Catalyst, Story Stage). This PRD does not duplicate them.

## Requirements

### Generator interface and standalone ComfyUI

- **REQ-002-001:** Lumur core must expose a surface-generator interface
  that accepts a surface role (or id), target size / aspect, optional
  control images (mask, depth, normal), and a preset reference, and that
  delivers textures asynchronously to paint mode. The projector render
  path must not await generation.
  **Status (slice 1):** complete-in-sim — `lumur.generate` +
  `LumurSurfaceGenerator` (Godot); `JobRunner` keeps work off the render
  path; paint loads finished textures from the room package.
- **REQ-002-002:** Lumur must ship a first-class **standalone ComfyUI
  provider** implementing that interface via the direct ComfyUI API, with
  Lumur-owned workflow presets. Core and this provider must not depend on
  Synesyn packages, Hub URLs, or `synesyn_core`.
  **Status (slice 1):** complete-in-sim — `ComfyUISurfaceGenerator` +
  `lumur-generate` CLI; verified against an in-process ComfyUI mock; no
  Synesyn imports in core.
- **REQ-002-003:** Standalone requests must be surface-aware: they carry
  the target surface’s pixel size and aspect, and may attach mask, depth,
  and/or normal control images derived from the room package when the
  preset expects them.
  **Status (slice 1):** complete-in-sim — `lumur.surface_render_request`
  + control image derivation from the room package.
- **REQ-002-004:** Standalone preset metadata must use a tag shape
  aligned with Synesyn’s where sensible — at minimum
  `lumur:surface_role=<role>`, with optional scoping tags — so authors
  can move presets between Lumur-local storage and SynPunkt without
  rewriting role semantics.
  **Status (slice 1):** complete-in-sim — `lumur.workflow_preset` with
  `metadata.preset.tags` and most-specific selection fallback.
- **REQ-002-005:** If no generator provider is configured, or generation
  fails / times out / disconnects, paint mode and the projector must
  continue with the last good or authored surface content
  (graceful degradation; ADR 0008 / ADR 0016).
  **Status (slice 1):** complete-in-sim — null provider; failure/timeout
  leave `generated_textures` unchanged.

### Optional Synesyn Hub provider (`lumur_synesyn`)

- **REQ-002-006:** All Synesyn integration in Lumur must live in a single
  Godot addon `lumur_synesyn` that depends on `synesyn_core`. Core Lumur
  addons must not import Synesyn types or call the Hub directly.
  **Status (slice 2):** complete-in-sim — `addons/lumur_synesyn/` + optional
  Python package `companion/lumur_synesyn/`; core `addons/lumur/**` and
  `lumur.generate` do not import Synesyn / Hub. Live Godot
  `HubSubstrateClient` remains optional when `synesyn_core` is installed;
  Hub HTTP for generation is in the companion bridge (same pattern as
  slice 1 ComfyUI).
- **REQ-002-007:** `lumur_synesyn` must register an optional generator
  provider that submits `SynesynRenderRequestV1` to Hub `/render/submit`
  (via `HubSubstrateClient.submit_render` / `SynesynRenderService`),
  selects `json.workflow` presets whose `metadata.preset.tags` include
  `lumur:surface_role=<role>` (most-specific optional scoping tags win),
  passes control images through `input_uploads` when needed, and maps
  completed `image.generated` artifacts onto surfaces through paint mode
  while retaining provenance.
  **Status (slice 2):** complete-in-sim — `SynesynHubSurfaceGenerator` +
  `lumur-generate-synesyn`; verified against mock Hub (submit, progress,
  success, failure, timeout, auth, `input_uploads`, provenance IDs).
- **REQ-002-008:** Switching between the standalone ComfyUI provider and
  the Hub provider must not require changes to paint mode or room-package
  consumers — only provider configuration.
  **Status (slice 2):** complete-in-sim — both providers implement
  `SurfaceGenerator`; paint still loads `generated_textures` only.

### Story Stage on surfaces

- **REQ-002-009:** `lumur_synesyn` must host Synesyn’s `story_stage` addon
  through a Lumur `StoryStageHost`, mapping stage layers to surface roles:
  backdrop, character / portrait / clip, and ambience. Mapping is by role
  name, not by hard-coded projector UV.
  **Status (slice 3):** complete-in-sim — `LumurStoryStageHost` +
  `LumurStoryStageLayout` / projector in `addons/lumur_synesyn/`; Python
  `story_stage_*` layout/compose/project with stub source. Live
  `story_stage` is observed non-invasively when present; headless uses the
  stub. See [story-stage.md](../bridge/story-stage.md).
- **REQ-002-010:** Story Stage scenario sections that Lumur does not
  understand must be ignored without breaking projection. Scenarios with
  no new sections behave as Synesyn’s compatibility contract requires
  (authored loops, no forced slideshow / lull).
  **Status (slice 3):** complete-in-sim — layout reader only accepts
  `lumur_layout` / `lumur_story_stage` / `lumur_surfaces`; other sections
  ignored; defaults match authored-loop behaviour.

### Audience steering (opt-in)

- **REQ-002-011:** Audience movement steering of story state is **opt-in
  per scenario**. It is enabled only when the scenario’s metaprompt /
  scenario declaration includes an explicit audience-steering section
  (working name `[LUMUR_AUDIENCE]` or equivalent agreed with Synes-bot).
  Absent that section, `presence`, `zone_enter`, `zone_leave`,
  `gathering`, and `footstep` events must not advance story / director
  state.
- **REQ-002-012:** Regardless of steering opt-in, the runtime may use
  presence and footsteps for ambience and for PRD-001 ripples.
- **REQ-002-013:** Event vocabulary (companion → Lumur → bridge), stable
  for this PRD:

  | Event | Meaning | Typical payload |
  | --- | --- | --- |
  | `presence` | One or more people detected in the room | `person_ids[]`, count, timestamp |
  | `zone_enter` | A tracked person entered a named interaction zone | `person_id`, `zone_id`, timestamp |
  | `zone_leave` | A tracked person left a named zone | `person_id`, `zone_id`, timestamp |
  | `gathering` | N people concurrently in a zone or proximity cluster | `zone_id` or cluster id, `person_ids[]`, count |
  | `footstep` | Ankle→floor contact (existing PRD-001 event) | as `lumur.event` footstep |

  Opted-in scenarios consume a filtered stream of these events through the
  bridge into the metaprompt / host path (for example as staged cues or
  director hints). Exact prompt wording is scenario-owned; Lumur owns the
  event schema and delivery.

### Provenance and replay

- **REQ-002-014:** When the Hub provider or Story Stage bridge is active,
  the current room package (`lumur.room` and Godot paint export) must be
  registerable as a Hub artifact so spatial setup carries provenance.
  **Status (slice 2):** complete-in-sim — `register_room_package` posts
  `json.lumur_room` via Hub `POST /substrate/artifacts` (generic API).
  Official type documentation remains a Synesyn-side touchpoint; Story
  Stage / Story Log replay stays slice 4.
- **REQ-002-015:** A Story Log plus its provenance sidecar, together with
  the registered room package, must be sufficient to replay dialogue and
  surface layout in the Lumur sim without live models or hardware
  (playback host pattern analogous to Synesyn’s story-log player).

### Verification

- **REQ-002-016:** Every in-scope requirement above must be verifiable
  headlessly in the Lumur sim (companion tests and/or Godot headless /
  xvfb), using a ComfyUI stub for standalone generation and a Synesyn Hub
  mock for bridge behaviour. Physical hardware validation is explicitly
  deferred.
  **Status (slice 3):** complete-in-sim for REQs 001–010, 014 (room
  registration) —
  `companion/tests/test_generate_comfyui.py` +
  `companion/tests/test_generate_synesyn_hub.py` (mock Hub) +
  `companion/tests/test_story_stage_surfaces.py` (stub Story Stage →
  layout → paint → sim). Audience steering / Story Log replay remain
  slice 4.

## Acceptance

Automated (target, as slices land):

- Generator interface + null provider: paint continues; no Hub or ComfyUI
  required (REQ-002-001, REQ-002-005).
- Standalone ComfyUI provider against a stub: surface-sized output mapped
  through paint; failure leaves last good texture (REQ-002-002–005) —
  companion and/or Godot headless tests.
- Hub provider against a Hub mock: preset tag selection,
  `SynesynRenderRequestV1` submit shape, `input_uploads`, artifact →
  surface mapping, provenance fields retained (REQ-002-006–008).
- Story Stage layer → surface role mapping in sim; unknown scenario
  sections ignored (REQ-002-009–010) —
  `companion/tests/test_story_stage_surfaces.py` (stub source).
- Steering off by default; with `[LUMUR_AUDIENCE]` (or agreed name),
  injected zone/gathering events affect a test host; without it, they do
  not (REQ-002-011–013).
- Room package artifact registration + Story Log replay in sim
  (REQ-002-014–015).
- No live projector/webcam required for complete-in-sim (REQ-002-016).

Manual (later hardware / live Synesyn):

- Live ComfyUI against a real projector surface.
- Live Hub + SynPunkt presets in a workshop room.
- Facilitator-run Story Stage with optional audience steering.

## Suggested slicing

| Slice | Delivers | Primary REQs |
| --- | --- | --- |
| **1 — Standalone ComfyUI provider** | Generator interface in core; Lumur presets; direct ComfyUI; paint integration; ComfyUI stub tests. **No Synesyn.** | 001–005, 016 |
| **2 — Bridge + Hub render provider** | `lumur_synesyn` addon; Hub provider behind the same interface; preset tags; provenance; Hub mock. | 006–008, 014, 016 |
| **3 — Story Stage on surfaces** | Host + layer→role mapping; ambience vs content; sim layout checks. | 009–010, 016 |
| **4 — Opt-in audience steering + replay** | Event vocabulary end-to-end; metaprompt opt-in; Story Log + room package replay in sim. | 011–015, 016 |

Slices 1 and 2 are intentionally independent: standalone generation ships
without the bridge; the Hub provider is additive. Story Stage work does
not block slice 1.

## Constraints and dependencies

- [ADR 0006: runtime for rooms](../architectural-decisions/0006-room-as-os-runtime.md)
- [ADR 0008: ComfyUI asynchronous](../architectural-decisions/0008-comfyui-asynchronous.md)
  — refined by [ADR 0016](../architectural-decisions/0016-pluggable-surface-generators.md)
- [ADR 0009: standalone with Synesyn bridge](../architectural-decisions/0009-standalone-with-synesyn-bridge.md)
- [ADR 0012: versioned room package](../architectural-decisions/0012-versioned-room-package.md)
- [ADR 0013: Godot paint asset export](../architectural-decisions/0013-godot-paint-asset-export.md)
- [ADR 0014: UDP JSON event transport](../architectural-decisions/0014-udp-json-event-transport.md)
- [ADR 0015: single `lumur_synesyn` bridge](../architectural-decisions/0015-single-lumur-synesyn-bridge.md)
- [ADR 0016: pluggable surface generators](../architectural-decisions/0016-pluggable-surface-generators.md)
- [PRD-001](PRD-001-CALIBRATE-PAINT-RIPPLE.md) (complete-in-sim)
- Synesyn (read-only reference on `Metapunkt/Synesyn`): SynPunkt Render tab
  / `SynesynRenderRequestV1`, `synesyn_core` (ADR 0017), `story_stage`
  addon (ADRs 0027, 0029, 0030), Story Log + provenance sidecar, FlashHead
  spike README

### Synesyn-side touchpoints (experimentation only)

During experimentation, Synesyn changes must be **surgical** and made
**only on Synes-bot’s fork** of Synesyn — never on `Metapunkt/Synesyn`
main from this workstream. Expected minimal touchpoints (none are
required to start slice 1):

| Touchpoint | Why | Required to start? |
| --- | --- | --- |
| Document / accept `lumur:surface_role=*` (and optional scoping) preset tags beside existing `scensyn:render_purpose=*` | Hub provider preset discovery | Slice 2 |
| Optional scenario section for audience steering (e.g. `[LUMUR_AUDIENCE]`) readable via existing section opt-in | REQ-002-011 | Slice 4 |
| Artifact type or metadata convention for `lumur.room` (or wrapper) on the Hub | REQ-002-014 | Slice 2/4 |
| Story Stage host feature flag(s) if Lumur needs to declare surface mapping support through `supports()` | Cleaner host contract | Slice 3; may be avoidable |

If fork experiments show the public contracts already suffice, **no
Synesyn code change is required**; Lumur adapts at the bridge boundary.

## Open questions and risks

- Exact name and schema of the audience-steering scenario section
  (`[LUMUR_AUDIENCE]` vs a field inside an existing section) — agree with
  Synes-bot before slice 4.
- How aggressive gathering detection should be (count threshold, dwell
  time, zone vs proximity cluster).
- Whether standalone Lumur presets live as on-disk JSON in the room
  package / a presets directory, or as a small Godot resource format;
  alignment with `json.workflow` should favour easy export into SynPunkt.
- Whether mask / depth / normal uploads are required for v1 presets or
  only for advanced ones; v1 should tolerate presets that need none.
- Room-package Hub artifact: wrap the whole directory (archive) vs
  register `room.json` + key arrays as related artifacts.
- Godot minor alignment: Lumur demo is on 4.3; Synesyn Story Stage targets
  4.7 features for some motion rungs — bridge must degrade when host Godot
  is older.
- Audio in the room (character voice from where the figure stands) is
  desirable later; this PRD does not require spatialised audio.
- Licence of any third-party ComfyUI nodes used by Lumur presets remains
  to verify per preset.

## Evidence map

- User workflow: [paint-mode.md](../godot/paint-mode.md),
  [tracking.md](../companion/tracking.md),
  [ripples.md](../godot/ripples.md); Synesyn SynPunkt / Story Stage /
  Story Catalyst guides (upstream)
- Normative contract: [comfyui.md](../companion/comfyui.md) (slice 1
  generator / presets); `lumur.event` extensions for presence / zones
  (later slices); `SynesynRenderRequestV1` (upstream, slice 2+)
- Architectural decision: ADR 0008, 0009, 0015, 0016
- Implementation tracker: slice 1 in companion `lumur.generate` +
  `addons/lumur` paint texture path; slice 2 in `lumur_synesyn` +
  `addons/lumur_synesyn` ([bridge/synesyn.md](../bridge/synesyn.md));
  slice 3 Story Stage layout
  ([bridge/story-stage.md](../bridge/story-stage.md))
- Executable specification: `companion/tests/test_generate_comfyui.py`
  (slice 1); `companion/tests/test_generate_synesyn_hub.py` (slice 2 Hub
  mock); `companion/tests/test_story_stage_surfaces.py` (slice 3 stub →
  paint → sim)
- Founding notes: [scratchpad](../scratchpad.md)
