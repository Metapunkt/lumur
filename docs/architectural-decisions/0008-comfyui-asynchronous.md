# 0008 — ComfyUI sits beside the renderer, never on its critical path

- **Status:** Accepted (refined by [ADR 0016](0016-pluggable-surface-generators.md))
- **Date:** 2026-11-18
- **Area:** content / generation
- **Relates to:** ADR 0003, ADR 0004, ADR 0006, ADR 0015, ADR 0016

## Context

The brief includes a ComfyUI integration, so that generated materials and
scene treatments can be authored against the real room. Generation is
slow, fallible and optional. If the projector waits on it, the room goes
dark or stalls. If generation is allowed to invent geometry, spatial
reliability is lost.

## Options considered

1. **ComfyUI on the render path.** The frame, or the surface texture, is
   not shown until a graph returns. Unacceptable for a live installation.
2. **Generation allowed to modify or replace measured geometry.** Novel,
   and it would make “scan once, invent many times” untrue.
3. **ComfyUI as an optional, asynchronous companion.** It generates in
   surface coordinates, into textures or treatments the runtime already
   knows how to display. The renderer proceeds with the last good
   content, or with non-generated content, if generation is slow, fails,
   or is disconnected.

## Decision

Option 3. ComfyUI is attached beside the renderer, not inside it. The
system must run fully without ComfyUI installed. Generative novelty
stays separate from the geometric foundation in the room package.

## Consequences

- Positive: a dropped connection is a missing texture, not a crashed
  installation.
- Positive: the same room can be repainted many times without a new
  scan.
- Trade-off: authors will see stale or placeholder imagery while a graph
  runs; that is preferred to a stall.
- Follow-up: the first milestone does not require a working ComfyUI
  integration. When it arrives, it needs its own PRD and a test that
  generation can fail without interrupting projection.

## Amendment — 2026-11-18

The async / optional / off-critical-path decision stands. **How** generation
attaches is refined in [ADR 0016](0016-pluggable-surface-generators.md): a
pluggable generator interface in Lumur core, a first-class standalone
ComfyUI provider (no Synesyn dependency), and an optional Synesyn Hub
provider inside `lumur_synesyn` only ([ADR 0015](0015-single-lumur-synesyn-bridge.md),
[PRD-002](../product-requirements/PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md)).
Do not read this ADR as requiring Synesyn for ComfyUI, or as forbidding a
direct ComfyUI path in standalone installs.
