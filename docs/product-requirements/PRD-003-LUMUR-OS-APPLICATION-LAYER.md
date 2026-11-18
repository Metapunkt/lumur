---
id: PRD-003
title: Lumur OS application layer
status: draft
version: "0.1"
owner: Ayodele Arigbabu
last_reviewed: 2026-11-18
primary_users: [author, installer, visitor, workshop facilitator]
supersedes: null
---

# Lumur OS application layer

## Problem and outcome

PRD-001 and PRD-002 leave a mapped room with paint, ripples, pluggable
surface generation, and an optional Synesyn bridge — but experiences are
still hard-wired demos, not installable apps. Authors need a small
application layer on top of the room runtime
([ADR 0006](../architectural-decisions/0006-room-as-os-runtime.md)): a
manifest that asks for kinds of surfaces and inputs, a compositor that
fits those requests to whatever room was scanned, and a lifecycle so more
than one experience can share the projector without rewriting coordinates.

The outcome: an app authored in one room installs in another by retargeting
surfaces; audience events from PRD-002 slice 4 become room input devices
with per-app permissions; generation stays optional through the existing
`SurfaceGenerator` interface; Lumur core never depends on Synesyn. The later
appliance boot image ([ADR 0007](../architectural-decisions/0007-lumur-os-as-appliance.md))
is explicitly out of scope — this PRD is the runtime those boots into.

## Users and jobs

- **Author:** When they have a scanned room, they need to ship a Godot
  scene plus a small manifest (surfaces by role/size/confidence; declared
  inputs), so the same app fits another room without editing pixels or UV.
- **Installer / CI:** When validating without hardware, they need install,
  launch, pause, switch, and compositing to run headlessly against sim
  presets (`--backend sim`), so acceptance never requires a physical room.
- **Visitor:** When several apps are available, they need the room to stay
  coherent — one surface owned clearly, confidence-masked projection, and
  optional zone-based app switching — so walking the floor feels intentional.
- **Workshop facilitator:** When Story Stage is present via
  `lumur_synesyn`, they need it to appear as a normal Lumur app (bridge
  only), so Synesyn stays optional and core remains standalone.

## Success measures

- A minimal app manifest declares surface *kinds* (role, minimum extent,
  confidence floor) and input kinds; the runtime allocates concrete surface
  ids from the current `lumur.room` package without the app naming pixels.
- Two bundled core apps (footstep ripples, paint-the-room) install and run
  under that format in sim; Story Stage installs only when `lumur_synesyn`
  is enabled.
- An app receives only the event types its manifest declares; undeclared
  types never reach its handlers.
- The compositor assigns exclusive ownership (or explicit shared layers) per
  surface/region, applies confidence masking from paint mode, and leaves
  unowned or low-confidence pixels unclaimed rather than inventing geometry.
- Launch, pause, and switch are observable in sim; a simple launcher lists
  installed apps; optional zone→app switching works when configured.
- Apps may request generation through `SurfaceGenerator`; with no provider
  (or Synesyn absent), projection continues. Core has no Synesyn import.
- Every requirement is verifiable headlessly in the existing sim; physical
  hardware is not required to mark a slice complete-in-sim.

## Scope

### In scope

- **App model:** Godot scene + versioned manifest (`lumur.app`); surface
  requests by kind/role/size/confidence; declared inputs; runtime fit to
  the scanned room ([ADR 0017](../architectural-decisions/0017-app-manifest-format.md)).
- **Room services:** Treat the versioned `lumur.room` package (and Godot
  paint export) as the room “file system”: surfaces, roles, ids, floor
  plane, confidence, generated textures ([ADR 0012](../architectural-decisions/0012-versioned-room-package.md)).
- **Input event bus:** Companion audience events (`presence`, `zone_enter`,
  `zone_leave`, `gathering`, `footstep`) as room input devices, with
  per-app permission filtering from the manifest
  ([ADR 0019](../architectural-decisions/0019-app-input-permissions.md);
  builds on [ADR 0014](../architectural-decisions/0014-udp-json-event-transport.md)
  and PRD-002 REQ-002-013).
- **Compositor:** Which app owns which surface or region; layering;
  transitions; confidence masking; builds on paint mode
  ([ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md),
  [paint-mode.md](../godot/paint-mode.md)).
- **Lifecycle:** Install, launch, pause, switch; a simple launcher UI or
  headless launcher API; optional audience switching by standing in a zone.
- **Optional generation:** Apps request per-surface content through the
  existing `SurfaceGenerator` interface (standalone ComfyUI or Hub via
  bridge). No Synesyn dependency in core
  ([ADR 0016](../architectural-decisions/0016-pluggable-surface-generators.md)).
- **Bundled apps:** Repackage footstep ripples, paint-the-room, and Story
  Stage (Story Stage only via optional `lumur_synesyn`) as the first apps
  that prove the manifest format.
- **Verification:** Headless sim / companion tests / Godot headless or
  xvfb, same posture as PRD-001/002.

### Out of scope

- Lumur OS appliance image, boot-to-launcher packaging, OTA updates
  ([ADR 0007](../architectural-decisions/0007-lumur-os-as-appliance.md)).
  This PRD supplies the runtime the appliance would later boot into.
- Changing PRD-001 calibrate / scan / paint / ripple behaviour, except to
  consume them through the app + compositor path.
- Changing PRD-002 generator / bridge / Story Stage contracts, except to
  present Story Stage as a bridge-hosted app.
- App stores, code signing, sandboxed filesystem isolation, multi-user
  accounts, or network app distribution.
- Multi-projector blending, view-dependent rendering, second camera,
  custom kernels.
- Edits to `Metapunkt/Synesyn` main.

## Critical journey

1. Author (or CI) has a scanned room package with Godot paint assets
   (PRD-001).
2. They install a bundled app by placing its scene + `lumur.app` manifest
   where the runtime discovers packages.
3. The runtime reads surface requests (for example “one wall ≥ 2 m wide”,
   “the floor”) and input declarations (`footstep`, …), allocates matching
   surfaces from the room package, and refuses or degrades per policy when
   a request cannot be met ([ADR 0017](../architectural-decisions/0017-app-manifest-format.md),
   [ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md)).
4. On launch, the app receives only declared inputs; paint / effects land
   on allocated surfaces through the compositor (confidence masking
   unchanged from paint mode).
5. A second app can be paused/switched; ownership moves without tearing the
   projector path. Optionally, standing in a named zone switches the active
   app.
6. If the app requests generation and a provider is configured, textures
   arrive asynchronously; if not, last-good / authored content remains.
7. Story Stage, when present, installs only through `lumur_synesyn` and
   follows the same manifest + compositor rules; without the bridge, core
   apps still run.

## Requirements

### Manifest and room fit

- **REQ-003-001:** An app must be a Godot scene (or scene tree entry)
  plus a versioned `lumur.app` manifest. The manifest must declare identity
  (`id`, `name`, `version`), schema version, surface requests, and input
  permissions. Apps must not hard-code projector pixel coordinates or raw
  UV for placement.
- **REQ-003-002:** Surface requests must express *kinds* of surfaces — at
  minimum role (`floor`, `wall`, named role), optional minimum extent
  (metres along a major axis), and optional minimum confidence — never
  absolute projector resolution or pixel rects. Exact JSON shape is
  [ADR 0017](../architectural-decisions/0017-app-manifest-format.md).
- **REQ-003-003:** At install or launch against a room package, the runtime
  must bind each surface request to concrete surface id(s) / roles from
  `lumur.room` (+ Godot paint `role_index`). Binding must succeed or follow
  the fallback / fail policy in
  [ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md);
  it must not invent geometry.
- **REQ-003-004:** Room services must expose surfaces, roles, ids, floor
  plane, confidence, and generated-texture handles from the current room
  package as the app-facing “file system”. Apps read through that API /
  facade (`LumurRoomRuntime` and successors), not by opening OpenCV or
  companion internals.

### Input bus and permissions

- **REQ-003-005:** The runtime must treat companion audience events
  (`presence`, `zone_enter`, `zone_leave`, `gathering`, `footstep`) as room
  input devices on the existing `lumur.event` transport (ADR 0014).
- **REQ-003-006:** An app must receive only event types listed in its
  manifest permissions. Events outside that set must not be delivered to
  the app’s handlers, even if the companion emits them
  ([ADR 0019](../architectural-decisions/0019-app-input-permissions.md)).
- **REQ-003-007:** Permission filtering must be enforceable in sim with
  injected events (no hardware). A test app that declares only `footstep`
  must not observe `zone_enter` / `gathering` / `presence`.

### Compositor

- **REQ-003-008:** The compositor must decide which launched app owns which
  allocated surface or region, including exclusive ownership by default and
  explicit shared/layered cases when manifests allow it
  ([ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md)).
- **REQ-003-009:** Compositing must reuse paint-mode correspondence and
  confidence masking: low-confidence / invalid projector pixels stay
  unpainted; apps cannot override the confidence threshold to invent
  coverage ([paint-mode.md](../godot/paint-mode.md)).
- **REQ-003-010:** When apps switch or pause, the compositor must hand off
  surface ownership with a defined transition (at least cut; crossfade
  optional) without stalling the projector path or requiring a room rescan.

### Lifecycle and launcher

- **REQ-003-011:** The runtime must support install (discover/register
  manifest + scene), launch, pause, resume, and stop for an app against a
  loaded room package, with observable state in sim.
- **REQ-003-012:** A simple launcher must list installed apps and start one
  (headless API required; a minimal on-projector UI is allowed but not
  required for complete-in-sim).
- **REQ-003-013:** Optionally, standing in a configured floor zone for a
  dwell time may switch the active app. Zone→app mapping is configuration,
  not hard-coded in apps. Absent that configuration, zones do not switch
  apps (they may still feed permitted inputs).

### Generation from apps

- **REQ-003-014:** Apps may request per-surface content through the
  existing `SurfaceGenerator` interface (ADR 0016). Requests remain
  asynchronous; missing / failing providers leave last-good or authored
  content. Core and bundled non-bridge apps must not import Synesyn types
  or Hub URLs.

### Bundled apps

- **REQ-003-015:** Footstep ripples and paint-the-room must ship as bundled
  apps under the `lumur.app` manifest format, proving surface requests and
  (for ripples) `footstep` input permission.
- **REQ-003-016:** Story Stage must be packageable as a Lumur app only via
  the optional `lumur_synesyn` bridge. Without the bridge, the launcher
  must not require Story Stage; core remains fully useful.

### Verification

- **REQ-003-017:** Every in-scope requirement above must be verifiable
  headlessly with the existing sim (`--backend sim` presets), companion
  tests, and/or Godot headless / xvfb. Physical projector/webcam validation
  is deferred. Owner acceptance for this PRD does not depend on hardware.

## Acceptance

Automated (target, as slices land):

- Parse and validate `lumur.app` manifests; reject pixel/UV placement fields
  (REQ-003-001, REQ-003-002) — companion and/or Godot unit tests.
- Fit manifests to sim room packages (`empty_room`, `room_with_box`,
  `noisy_room`, wall-poor presets): allocation, fallback, and hard-fail
  cases (REQ-003-003, REQ-003-004, REQ-003-008) —
  companion tests against exported `lumur.room` / Godot assets.
- Inject audience events; permission filter delivers only declared types
  (REQ-003-005–007).
- Two apps sequentially or concurrently on disjoint surfaces; confidence
  mask still drops invalid pixels; switch/pause handoff (REQ-003-008–011).
- Launcher lists and starts bundled apps headlessly (REQ-003-012, 015).
- Zone→app switch with dwell when configured; no switch when not
  (REQ-003-013).
- App generation request with null / ComfyUI stub provider; no Synesyn
  imports under `addons/lumur/**` (REQ-003-014, 016).
- Story Stage app entry appears only with bridge enabled (REQ-003-016).
- No live hardware required (REQ-003-017).

Manual (later hardware):

- Live launcher on a real projector; zone switch with walkers.
- Side-by-side authoring of a third-party demo app against two physical
  rooms.

## Suggested slicing

| Slice | Delivers | Primary REQs |
| --- | --- | --- |
| **1 — Manifest + room fit** | `lumur.app` schema; room-service facade; allocate surfaces for one app in sim; fail/fallback policy tests. | 001–004, 017 |
| **2 — Input permissions** | Event bus filter from manifest; inject presence/zone/gathering/footstep; tests that undeclared events never arrive. | 005–007, 017 |
| **3 — Compositor + lifecycle** | Ownership / layering / confidence mask; install–launch–pause–switch; headless launcher; optional zone→app switch. | 008–013, 017 |
| **4 — Bundled apps + generation** | Repackage ripples + paint-the-room; Story Stage app via bridge only; app-side `SurfaceGenerator` requests; CI boundary check (no Synesyn in core). | 014–017 |

Slices 1–2 unblock authors and tests without multi-app UI. Slice 3 is the
first true “OS” behaviour. Slice 4 proves the format with real content and
keeps Synesyn optional.

## Constraints and dependencies

- [ADR 0006: runtime for rooms](../architectural-decisions/0006-room-as-os-runtime.md)
  — refined by ADR 0017–0019 for manifest, compositing, and input
  permissions; multi-app compositor was deferred there until apps needed it.
- [ADR 0007: appliance image](../architectural-decisions/0007-lumur-os-as-appliance.md)
  — Proposed; boots into this runtime later; out of scope here.
- [ADR 0009: standalone with Synesyn bridge](../architectural-decisions/0009-standalone-with-synesyn-bridge.md)
- [ADR 0012: versioned room package](../architectural-decisions/0012-versioned-room-package.md)
- [ADR 0013: Godot paint asset export](../architectural-decisions/0013-godot-paint-asset-export.md)
- [ADR 0014: UDP JSON event transport](../architectural-decisions/0014-udp-json-event-transport.md)
- [ADR 0015: single `lumur_synesyn` bridge](../architectural-decisions/0015-single-lumur-synesyn-bridge.md)
- [ADR 0016: pluggable surface generators](../architectural-decisions/0016-pluggable-surface-generators.md)
- [ADR 0017: app manifest format](../architectural-decisions/0017-app-manifest-format.md)
- [ADR 0018: surface allocation and compositing](../architectural-decisions/0018-surface-allocation-and-compositing.md)
- [ADR 0019: app input permissions](../architectural-decisions/0019-app-input-permissions.md)
- [PRD-001](PRD-001-CALIBRATE-PAINT-RIPPLE.md) (complete-in-sim)
- [PRD-002](PRD-002-SYNESYN-BRIDGE-STORY-STAGE.md) (complete-in-sim)

## Open questions and risks

- Exact units and measurement for “≥ 2 m wide”: derived from plane
  inliers / bounding extent in the room package vs. a simpler role-only
  match for v1.
- Whether one app may claim multiple walls of the same role in one
  request (`count: 2`) in schema v1.0 or only via repeated requests.
- Shared-layer policy: allow only ambience-style overlays (ripples on
  floor under another app) vs. general alpha stacks in v1.
- Launcher UX on-projector vs. headless-only for complete-in-sim (headless
  is mandatory; on-projector may wait).
- Zone→app switching vs. Story Stage `[LUMUR_AUDIENCE]` steering: both may
  listen to zones; configuration must avoid accidental double-binding.
- Package discovery path (directory convention under the project vs.
  explicit install registry file).
- Whether `lumur.app` schema_version bumps independently of `lumur.room`
  (expected yes; record compatibility matrix when both move).

## Evidence map

- User workflow: [paint-mode.md](../godot/paint-mode.md),
  [ripples.md](../godot/ripples.md),
  [tracking.md](../companion/tracking.md),
  [audience-steering.md](../bridge/audience-steering.md),
  [story-stage.md](../bridge/story-stage.md),
  [room-scan.md](../companion/room-scan.md)
- Normative contract: `lumur.app` (ADR 0017); allocation / compositing
  (ADR 0018); input permissions (ADR 0019); existing `lumur.room` /
  `lumur.event` / `SurfaceGenerator`
- Architectural decision: ADR 0006–0007, 0009, 0012–0019
- Implementation tracker: none yet (draft PRD)
- Executable specification: to land per slice under `companion/tests/`
  (and optional Godot headless scripts), following PRD-001/002 sim posture
- Founding notes: [scratchpad](../scratchpad.md)
