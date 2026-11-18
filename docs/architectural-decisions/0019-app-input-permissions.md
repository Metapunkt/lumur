# 0019 — Per-app input permissions for room events

- **Status:** Accepted
- **Date:** 2026-11-18
- **Area:** runtime / input / apps
- **Relates to:** ADR 0006, ADR 0014, ADR 0015, ADR 0017; PRD-002, PRD-003
- **Refines:** ADR 0006 (apps subscribe to input events; they do not own
  the pose model) and ADR 0014 (transport unchanged; delivery is filtered)

## Context

PRD-001 delivers `footstep` over local UDP JSON ([ADR 0014](0014-udp-json-event-transport.md)).
PRD-002 slice 4 adds `presence`, `zone_enter`, `zone_leave`, and
`gathering` in core (`lumur.audience`) and optional Story Stage steering
in `lumur_synesyn`. Today every Godot listener that binds
`LumurEventReceiver` can see the full stream.

PRD-003 apps declare what they need in a manifest
([ADR 0017](0017-app-manifest-format.md)). Without a permission filter,
a paint app could observe zone events meant for a launcher or for Story
Stage steering, and the “room input device” metaphor has no access
control — only a shared firehose.

## Options considered

1. **Global bus, no filter.** Simplest; every app sees every event.
   Rejected for multi-app and for least-privilege demos.
2. **OS-style capability prompts at install.** Heavy UX; no installer UI
   yet. Rejected for v1.
3. **Manifest-declared allowlist enforced by the runtime.** Companion still
   emits the full vocabulary; the Godot (and test) delivery path drops
   types not listed in the active app’s `inputs`. Chosen.

## Decision

Option 3.

### Binding rules

1. **Vocabulary** remains PRD-002 REQ-002-013 / ADR 0014 envelopes:
   `footstep`, `presence`, `zone_enter`, `zone_leave`, `gathering`. New
   types require a schema / ADR bump, not silent invention by an app.
2. **Manifest `inputs`** is an allowlist. Empty list → app receives no
   room events (display-only). Unknown names in the manifest → install
   validation error.
3. **Enforcement point.** Filtering happens in the runtime event fan-out
   (Godot receiver / app host), after UDP decode (or after test injection).
   Apps must not bypass it by opening a raw UDP socket to the companion
   port in bundled code; demos and tests use the filtered API.
4. **Multiple apps.** Each launched app gets its own filtered view.
   Overlay and base apps are filtered independently. The launcher may
   subscribe to `zone_*` for optional zone→app switching
   (PRD-003 REQ-003-013) as a privileged host path, not as an ordinary
   app permission.
5. **Bridge steering is separate.** `lumur_synesyn` audience steering
   ([audience-steering.md](../bridge/audience-steering.md)) remains
   opt-in per *scenario* (REQ-002-011). App input permissions do not
   grant story steering; they only govern whether an app’s handlers see
   events. A Story Stage app still needs the bridge + scenario opt-in to
   steer.
6. **Transport unchanged.** Still local UDP JSON, lossy, loopback-friendly.
   Permissions are not authentication and not a security boundary against
   a malicious local process — they are an API contract for well-behaved
   apps and for tests.

### Example

Ripples manifest: `"inputs": ["footstep"]` — `zone_enter` injected in sim
never reaches `ripple_layer` handlers.

Launcher host (not an app manifest): may listen for `zone_enter` with
dwell to switch apps, even while the foreground app only declared
`footstep`.

## Consequences

- Positive: least privilege for bundled apps; permission bugs are unit-test
  cheap (inject, assert silence).
- Positive: keeps ADR 0014 and `lumur.audience` as-is; no second event
  schema.
- Trade-off: not a sandbox — a hand-written scene can still open UDP.
  Honest apps and CI are the bar for v1.
- Trade-off: host/launcher privileges must stay narrow and documented so
  they do not become a back door for every demo scene.
- Follow-up: done in PRD-003 slice 2 — `AppInputBus` /
  `LumurAppInputBus` filter beside `LumurEventReceiver`; extend envelopes
  only via versioned schema when new device kinds appear.
