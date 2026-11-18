# 0007 — Lumur OS is a later appliance image, not a custom kernel

- **Status:** Proposed
- **Date:** 2026-11-18
- **Area:** packaging / distribution
- **Relates to:** ADR 0006

## Context

The name “Lumur OS” invites a literal reading: write an operating system.
A kernel, device drivers, process scheduling, filesystems and a security
model are years of work, and Linux already does them well. None of that
work improves projection onto a wall.

There is a middle path that would still feel like an OS to someone
setting up a room: a dedicated appliance that boots straight into the
Lumur runtime.

This decision is proposed, not accepted. It is a later phase, and it
must not shape the first milestone.

## Options considered

1. **A real operating system** (a custom kernel or a from-scratch user
   space). Rejected as a first — and likely any — move. It rebuilds
   existing machinery and delays the only part Lumur uniquely does.
2. **A desktop application indefinitely.** Correct for development and
   for the first installations. It never becomes “turn the box on and
   the room wakes”.
3. **A minimal Linux appliance image**, in the spirit of a Raspberry Pi
   kiosk build or SteamOS, that boots fullscreen into the Lumur runtime
   on the projector. Candidate hardware named in discussion: a mini PC
   or a Raspberry Pi 5. This is packaging of the runtime in ADR 0006,
   not a new architecture.

## Decision

Option 3 is the intended later form of “Lumur OS”, and only once the
runtime works. Build the runtime first. Do not invent a kernel. Do not
block calibration, painting or the first interaction on an image build.

Status remains **Proposed** until there is a runtime worth packaging and
a concrete image recipe to accept.

## Consequences

- Positive: the name stays honest without a kernel project; the
  development path stays a Godot application plus a companion process.
- Trade-off: early users will install and launch Lumur themselves.
- Follow-up: when this is accepted, record hardware targets, image
  build, and how updates are applied — as a PRD and contracts, not by
  silently expanding this proposal.
