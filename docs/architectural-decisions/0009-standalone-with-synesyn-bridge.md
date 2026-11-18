# 0009 — Lumur stays standalone; Synesyn integrates through a thin bridge

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** integration / boundaries
- **Relates to:** ADR 0004, ADR 0006

## Context

Lumur and [Synesyn](https://github.com/Metapunkt/Synesyn) are sibling
Metapunkt projects. Both are Godot-centred and local-first. Synesyn
already treats prompts, images, scenarios and closures as versioned
artefacts with provenance, and it has a Story Stage, a Thinking Map, and
a Hub. The two compose naturally: Synesyn reasons, Lumur can make the
room perform the result.

That closeness is a risk. If Lumur is born inside Synesyn, people who
want interactive walls inherit a hub, an agent stack and a workshop
vocabulary they did not ask for.

## Options considered

1. **Lumur lives in the Synesyn repository**, as another addon family
   that assumes the Hub. Fast for a joint demo; fatal to Lumur as a
   standalone runtime.
2. **No planned integration.** Protects independence; throws away a
   genuine fit.
3. **Lumur is its own runtime and repository.** Synesyn integrates
   through a thin bridge addon that talks to Lumur's existing surface,
   event and room-package interfaces. Neither project is a prerequisite
   for the other.

## Decision

Option 3. Lumur must be useful without Synesyn. When a bridge is built,
it is an addon, not a new core. Ideas such as Story Stage on a real
wall, embodied workshops, room packages as Synesyn artefacts, Story Log
replay as an installation, or booting a room into a Synesyn session are
welcome — and they are applications of the bridge, not reasons to fold
the runtimes together.

A first joint demo, when both sides are ready, was suggested: one
character projected onto a real wall, speaking a saved Story Log. That
suggestion is not a commitment in this ADR.

## Consequences

- Positive: Lumur's first users need only a webcam, a projector and the
  runtime.
- Positive: Synesyn can gain a body without Lumur taking on a mind it
  does not need.
- Trade-off: joint features land later, and require stable Lumur
  interfaces before the bridge can be thin.
