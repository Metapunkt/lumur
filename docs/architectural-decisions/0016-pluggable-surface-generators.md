# 0016 — Pluggable surface generators; ComfyUI with or without Synesyn

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** content / generation
- **Relates to:** ADR 0004, ADR 0006, ADR 0008, ADR 0009, ADR 0015; PRD-002
- **Refines:** ADR 0008 (async / optional / off the render path remains binding;
  the attachment shape is replaced below)

Accepted after owner merge of
[PR #8](https://github.com/Metapunkt/lumur/pull/8). Slice 1 lands the
generator interface, null provider, and standalone ComfyUI provider in the
Python companion (Godot consumes results via paint mode). Slice 2 adds the
optional Hub provider in `lumur_synesyn` behind the same interface.

## Context

ADR 0008 decided that ComfyUI sits beside the renderer: asynchronous,
optional, never on the critical path, and never inventing geometry. It left
open *how* generation attaches when the Synesyn bridge arrives.

Two mistakes are easy from that silence:

1. **Hard-wire Lumur to Synesyn** for all generation — authors who never use
   the Hub inherit a Hub, SynPunkt presets, and `synesyn_core`.
2. **Treat Synesyn as a parallel second pipeline** — two request shapes, two
   paint integrations, and drift between “Lumur ComfyUI” and “Hub render.”

Owner direction for PRD-002: Lumur must generate through ComfyUI **with or
without** Synesyn. Core owns a provider interface and a first-class
standalone ComfyUI provider. The Synesyn Hub route is an **optional second
provider** inside `lumur_synesyn` ([ADR 0015](0015-single-lumur-synesyn-bridge.md)).

## Options considered

1. **Generation only through Synesyn Hub.** Clean provenance; violates
   standalone. Rejected.
2. **Only a direct ComfyUI client in core; no Hub path.** Keeps Lumur free;
   throws away SynPunkt presets, `image.generated` provenance, and shared
   workshop artifacts. Rejected as the sole option.
3. **Two unrelated pipelines** (core→ComfyUI and bridge→Hub) with different
   request shapes. Works short-term; doubles paint integration and preset
   vocabulary. Rejected.
4. **One generator interface in Lumur core; multiple providers.**
   Standalone ComfyUI is first-class in Lumur. Hub submit is a provider
   implemented only in `lumur_synesyn`. Preset / request shapes stay aligned
   where sensible. Chosen.

## Decision

Option 4.

### Binding rules (still from ADR 0008)

- Generation is asynchronous and optional.
- The projector continues with last-good or authored content if a provider
  is missing, slow, or failing.
- Generative output may not replace measured geometry in the room package.

### New attachment shape (refines ADR 0008)

1. **Interface in core.** Something in the spirit of a
   `LumurSurfaceGenerator` / provider API: surface role or id, target size
   and aspect, optional control images (mask, depth, normal), preset
   reference in; texture (and optional provenance handle) out, async.
   Paint mode and apps depend on the interface, not on ComfyUI or Hub.
2. **Standalone ComfyUI provider (first-class, in Lumur).** Talks to the
   ComfyUI HTTP/API directly. Owns Lumur workflow presets on disk (or an
   equivalent Godot resource). Builds surface-aware requests. **No
   dependency on Synesyn, Hub, or `synesyn_core`.**
3. **Synesyn Hub provider (optional, in `lumur_synesyn` only).** Submits
   `SynesynRenderRequestV1` to `/render/submit`, selects SynPunkt
   `json.workflow` presets tagged `lumur:surface_role=<role>` (optional
   scoping tags), uses `input_uploads` for control images, consumes
   `image.generated` with provenance. Swap providers by configuration;
   paint mode does not change.
4. **Aligned shapes, separate ownership.** Tag keys such as
   `lumur:surface_role=` and the idea of patches / control uploads should
   match Synesyn’s vocabulary closely enough that presets can move between
   Lumur-local storage and SynPunkt. Core still does not import Synesyn
   types; alignment is by convention and tests, not by linking.
5. **Null provider.** Default when nothing is configured: no generation,
   no errors on the render path.

ADR 0008’s phrase “ComfyUI as an optional, asynchronous companion” is
therefore read as **“generation providers beside the renderer”**, of which
direct ComfyUI is the default concrete provider for standalone installs,
not as “one hard-wired ComfyUI sidecar” or “ComfyUI only via Synesyn.”

## Consequences

- Positive: authors get AI surface treatments with webcam + projector +
  ComfyUI alone.
- Positive: Synesyn workshops get Hub provenance and shared presets without
  a second paint path.
- Positive: PRD-002 can slice standalone ComfyUI independently of the
  bridge (slice 1 vs slice 2).
- Trade-off: two providers to maintain; mitigated by one interface and
  shared tag/request conventions.
- Trade-off: full byte-identical parity with every Synesyn render field is
  not promised in v1 — only the surface-role and control-image seams
  needed for portable presets.
- Follow-up done: interface + standalone ComfyUI provider landed with PRD-002
  slice 1; Hub provider in `lumur_synesyn` (slice 2). Keep `addons/lumur/**`
  free of `synesyn_core` imports.
