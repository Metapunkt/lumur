# 0015 — Single `lumur_synesyn` bridge for Synesyn integration (render + Story Stage)

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** integration / boundaries
- **Relates to:** ADR 0006, ADR 0008, ADR 0009, ADR 0016; PRD-002

Accepted after owner merge of
[PR #8](https://github.com/Metapunkt/lumur/pull/8) (docs: PRD-002 + ADRs
0015–0016). Slice 1 implements standalone generation without this bridge;
`lumur_synesyn` remains future work (PRD-002 slices 2+).

## Context

ADR 0009 established that Lumur stays a standalone runtime and that Synesyn
integrates through a thin bridge — not by folding the repositories together.
PRD-002 now names the concrete joint capabilities: optional Hub-backed
surface generation, Story Stage mapped onto room surfaces, room packages as
Hub artifacts, Story Log replay in the room, and opt-in audience steering.

Without a hard boundary, those features tend to grow a second ComfyUI client
in core, ScenSyn imports in paint mode, or parallel “Synesyn-aware” event
paths. Synesyn itself already concentrates shared Hub and render contracts in
`synesyn_core` (Synesyn ADR 0017) and keeps Story Stage as its own addon
(`addons/story_stage`, Synesyn ADRs 0029–0030). Lumur should meet that shape
with one integration addon, not several.

Separately, surface generation must work **without** Synesyn
([ADR 0016](0016-pluggable-surface-generators.md)). The bridge therefore owns
only the Synesyn *provider* and Story Stage mapping — not generation itself.

## Options considered

1. **Synesyn calls into Lumur core from ScenSyn / SynPunkt.** Fast for a
   demo; makes Lumur a host detail of Synesyn and breaks standalone installs.
2. **Several Lumur addons** (`lumur_comfy_hub`, `lumur_story_stage`, …).
   Clear per feature, but duplicates Hub client setup and invites core to
   special-case “is Synesyn present?” in more than one place.
3. **One bridge addon, `lumur_synesyn`**, depending on `synesyn_core` (and
   optionally instancing `story_stage`). All Hub, provenance, Story Stage
   host, and audience-steering forwarding live there. Core Lumur speaks only
   its own generator interface, surfaces, events, and room package.
   Chosen.

## Decision

Option 3.

- **`addons/lumur_synesyn/`** is the only Lumur code allowed to depend on
  `synesyn_core`, call Hub endpoints, or instance Synesyn’s `story_stage`.
- It registers an optional **Hub generator provider** behind Lumur’s
  generator interface (ADR 0016): `SynesynRenderRequestV1` via
  `/render/submit`, SynPunkt presets tagged `lumur:surface_role=…`,
  `input_uploads`, `image.generated` + provenance.
- It supplies a **`StoryStageHost`** that maps Story Stage layers
  (backdrop, characters / portraits / clips, ambience) onto Lumur surface
  roles, and forwards opt-in audience events into scenario metaprompts.
- It can register the room package as a Hub artifact and bind Story Log
  replay to sim / projector layout.
- Core addons (`addons/lumur`, companion, paint, ripples) must not import
  Synesyn types or URLs. Absence of `lumur_synesyn` leaves Lumur fully
  useful, including standalone ComfyUI generation when that provider is
  configured.

Synesyn-side experiments stay surgical and **only on Synes-bot’s fork**,
never on `Metapunkt/Synesyn` main from this workstream (see PRD-002).

## Consequences

- Positive: one place to review Synesyn coupling; ADR 0009 stays
  enforceable in packaging and in CI (bridge optional).
- Positive: Story Stage and Hub render share Hub client, session, and
  artifact conventions without a second integration style.
- Positive: standalone ComfyUI (ADR 0016) is unaffected by enabling or
  disabling this addon.
- Trade-off: facilitators who want Story Stage on walls must enable
  `synesyn_core` + `story_stage` + `lumur_synesyn` beside Lumur — the same
  drop-in honesty Synesyn already documents for its own addons.
- Follow-up: boundary check (no `synesyn_core` / Hub imports under
  `addons/lumur/**`) when the addon lands; listed as PRD-002 slice 2+.
