# Lumur scratchpad

Founding brainstorm, recorded 18 November 2026 (Europe/Oslo). This is a
working notebook, not a source of truth. Decisions live in
[architectural decisions](architectural-decisions/README.md); product intent
for the first build lives in
[PRD-001](product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md).

## Origin

The starting point was Microsoft's RoomAlive Toolkit: an MIT-licensed,
Kinect-based, Unity-centred system for projection mapping a living room and
interacting with it. A literal port to Godot was considered, then set aside.
The Kinect was a bottleneck once Microsoft stopped producing it, and a
line-by-line port would preserve a Kinect-era architecture that the project
does not need.

The brief was to do without specialised hardware, using ordinary cameras — a
standard webcam should suffice — and to keep the implementation small. Godot
is the runtime; other tools may couple in through ComfyUI. The system should
be a spiritual successor: measure the room with conventional geometry, and
add AI only where it improves interaction or content.

## Capability tiers

The room is largely static; people move through it. Scan occasionally, track
selected interactions, render continuously. Rendering must not wait on AI or
on ComfyUI.

| Configuration | Built around | Not promised |
| --- | --- | --- |
| One webcam and a projector; no AI | Static room scanning, surface mapping, motion-triggered effects on known surfaces | Dense, reliable depth of freely moving people |
| The same hardware plus a small vision model | Optional segmentation, approximate pose or depth, richer interaction | Kinect-equivalent dynamic depth under all lighting and occlusion |
| Two ordinary cameras and a projector | A later route to more observable dynamic geometry | Effortless stereo on textureless surfaces, or perfect synchronisation |
| ComfyUI attached | Generated materials, scene treatments, semantic authoring | Availability of generation on the render path |

Monocular depth models such as Depth Anything V2 may be useful later. Relative
depth is not a calibrated room measurement, and even a metric variant is a
prediction, not a substitute for validating projector alignment against
observed geometry. Licence claims heard in passing — that Depth Anything V2
Small is Apache-2.0, and that larger variants are non-commercial — are
**to verify** before any model is adopted. Godot camera capabilities cited in
early discussion are likewise **to verify**.

Default projection is surface-native: content lives in each surface's own
coordinates. View-dependent illusion, for one privileged viewer, is a later
concern, not a prerequisite.

## Design principles

**Geometry decides where; AI suggests what.** The projector doubles as the
missing depth sensor. Project known patterns, observe them with the webcam,
and triangulate the surfaces. A single camera–projector pair can do this; it
is established structured-light practice, not a speculative AI workaround.
Gray-code patterns are the planned first method.

Further ideas, not all of them in the first milestone:

- **Paint the room without a 3D model.** The scan establishes a correspondence
  field between camera pixels and projector pixels. Appearance can be
  transferred through that field, which is enough for painting walls, outlining
  architectural features, or placing graphics. Arbitrary 3D viewpoints and
  reliable mapping onto moving surfaces are not part of this mode.
- **A room-native physics canvas.** Derive an adjacency graph from the room
  mesh so effects understand floor–wall boundaries, table-to-wall crossings,
  light that travels around a corner, and doorways as protected interruption
  zones. This is a content abstraction, not something that must be ported from
  RoomAlive.
- **Scan once, invent many times.** Persist measured geometry and confidence,
  calibration, named surfaces, exclusions and interaction zones. ComfyUI can
  repaint the same room without touching its geometric foundation.
- **Graceful fallback.** If tracking fails, the room remains a
  projection-mapped artwork. If AI is disabled, deterministic interactions
  remain. If full reconstruction is poor, correspondence-based painting
  remains. The system should lose sophistication, not collapse.
- **Projective reconstruction up to scale** is enough to render through the
  projector. A checkerboard target is optional. One tape-measured distance,
  or optionally a phone LiDAR scan, supplies real-world units for physics.
- **Bake distortion into a lookup texture.** The scan already yields a dense
  camera-to-projector map, so lens distortion can be a UV lookup in a final
  shader pass, without fitting a distortion model for rendering.
- **Lift 2D pose into 3D with the room.** Cast a ray from the camera through
  each detected ankle and intersect it with the scanned floor. The same trick
  works for hands near a known wall.

RoomAlive Toolkit ideas, calibration knowledge, and perhaps isolated
algorithms may be reused under its MIT licence. Its architecture should not
be preserved. A claim of fewer total lines of code is not promised until the
system is implemented: robust calibration and diagnostics still take real
engineering. The aim is much less *mandatory* machinery.

## Camera contamination and people tracking

Projected content falls into the webcam, which can fool a person detector
and can also land on people's bodies.

An infrared approach was considered: a webcam with its IR-cut filter
removed, a visible-light-blocking filter, and an 850 nm illuminator, so the
tracking camera cannot see the projection. The project owner rejected
hardware hacks of this kind.

The chosen approach is software. A pose model (MediaPipe, YOLO-pose, or
similar — exact model **to choose**) runs on the *raw* webcam frame, not on
a subtracted image. Predicted-frame subtraction supplies a mask of where the
image differs from what was just projected, and that mask is used to reject
false detections (for example, a projected figure on the wall). This needs:

- locked auto-exposure and white balance, or the predicted image drifts;
- a rough radiometric (colour and brightness) calibration;
- a short buffer of recent renders, because USB webcams typically lag by
  tens of milliseconds, and the predicted frame must match the frame the
  camera actually caught.

Limits to plan around:

- Strong, fast-moving imagery on a person's torso can make joint detection
  jittery, especially in a dark room with bright content.
- Modern pose models handle several people in one frame. Occlusion and
  identity are harder: with one camera, a person standing behind another
  loses joints, and identities can swap when paths cross unless a tracker
  such as ByteTrack is added.
- The floor-intersection trick still gives each visible person a 3D foot
  position. Two to four people in a living-room-sized space should be enough
  for ripples, follow-me creatures, or avoid-zones. Dense crowds or precise
  per-person hand interaction would need a second camera.

Prototype order: lock exposure, run pose on the raw frames, then add the
subtraction mask once the actual false detections are visible. Less
subtraction may be needed than expected.

## Naming

Working titles considered, and set aside, included Lumen Room, Godot Alive,
Projectile, Wallflower, Room Sense, Wallpaper.gd and other Wallpaper-
compounds, Feral Wallpaper, Wallop, Papergeist, Wallwyrm, Unpaper,
Mural.exe, Sigil, Trompe, Penumbra, Fresco and Scry.

A more productive vein used *mur* (wall). From that list — Lumimur,
Kinemur, Murix, MurOS, Muryx, Lumur, Synmur, Animur, Lumuros — **Lumur**
was chosen: two syllables, lumen plus mur, with “Lumur OS” available as a
tagline and, later, as an appliance image. *Muros* already means “walls” in
Spanish and Portuguese, which made MurOS attractive, but Lumur is the more
confident brand. The planned repository name is `lumur`.

## Lumur OS

“OS” is the right architecture if it means an operating system *for rooms*,
not a kernel, drivers and a scheduler of our own. Linux already does that
work. Rebuilding it would not make walls come alive any better.

The runtime metaphor, kept small:

- **Hardware abstraction.** Cameras and projectors are devices with a
  calibration “driver”. Apps never touch OpenCV; they ask for surfaces.
- **A file system for the room.** The scanned room is a saved package:
  surfaces, names, exclusions, connections. Apps read it like files (“give
  me the floor”, “is the doorway clear?”).
- **Input events.** Footstep, hover, presence, enter and leave zone,
  delivered like pointer events. Apps subscribe without caring about pose
  models.
- **A display server.** Lumur owns the projector output and can, later,
  composite several apps onto different surfaces. The multi-app compositor
  waits until there are real apps that need it.
- **Apps as Godot scenes.** An app is a scene plus a small manifest
  declaring the surfaces it needs. Lumur assigns those surfaces in
  whatever room it is installed in. Portability is the surprise: a “tidal
  pool” built in one flat should fit itself to another.

The literal “Lumur OS” is a later appliance: a minimal Linux image, in the
spirit of a Raspberry Pi kiosk or SteamOS, that boots straight into the
Lumur runtime, fullscreen on the projector. Flash it to a mini PC or a
Pi 5, mount it, and the room wakes when the box is turned on. That is
where the name becomes literally true. The runtime is built first; the
image is packaging, not a prerequisite.

## Cross-pollination with Synesyn

[Synesyn](https://github.com/Metapunkt/Synesyn) is a sibling Metapunkt
project: local-first, Godot, reusable addons with applications on top,
everything stored as a versioned artefact with provenance. The two fit.
Synesyn reasons; Lumur can make the room perform the result.

Ideas in play, none of them required for Lumur's first milestone:

- **Story Stage leaves the screen.** The room becomes the stage: a
  character appears on a real wall, the scenario backdrop wraps the space,
  and a voice comes from where the figure stands.
- **Workshops become embodied.** The Thinking Map could spread across
  walls. Accept, reject and defer could be places people walk to. Review
  could become walking between futures, including a “do nothing” corner.
  Presence and zone events turn movement into deliberation input.
- **The room as an artefact.** A scanned room package, a projection state,
  or a generated wall texture can carry provenance in Synesyn's store. A
  workshop's spatial setup becomes traceable and replayable.
- **Story Log replay as installation.** A recorded session played back on
  Lumur becomes a gallery piece: the deliberation re-performed in the room.
- **Architecture.** Lumur can later appear as an addon family that talks
  to the Synesyn Hub, and Lumur OS can boot a room into a Synesyn session.
  The first striking demo, when both sides are ready, would be Story Stage
  on Lumur: one character projected onto a real wall, speaking a saved
  Story Log.

Lumur must remain a standalone runtime that Synesyn *uses*. People who
want interactive walls should never need the Hub or the agent stack. The
join is a thin bridge addon.

## Proposed first build

Start with one fixed webcam, one projector, Gray-code calibration (a
printed target optional), a structured-light scan, a Godot surface
renderer, correspondence-based painting, and one satisfying interaction:
footstep ripples, from pose ankles ray-cast to the scanned floor.

A suggested sequence, later refined in PRD-001:

1. Alignment — calibration and a mapped plane; a projected grid aligns at
   the centre and the edges; residuals are recorded.
2. Room scan — structured-light capture and a confidence-filtered mesh; no
   unsupported triangles bridging gaps.
3. Godot experience — stable surface coordinates and a small effects
   library; the renderer does not depend on Python inference or ComfyUI.
4. Interaction — floor ripples; measure end-to-end latency and false
   triggers under the actual projected content.
5. ComfyUI — asynchronous surface-texture generation; failure or
   disconnection must not interrupt projection.
6. Extensions — optional pose refinements, segmentation, viewer tracking,
   additional projectors; each with its own accuracy and performance tests.

Postponed: dense live reconstruction, multi-person viewpoint correction,
automatic room semantics, multi-projector blending, and the appliance
image.

## Open questions

- The public repository is to be created at
  [Metapunkt/lumur](https://github.com/Metapunkt/lumur); it did not exist
  when this note was written.
- Licence: decided 2026-11-18. Source code is MIT; text and documentation
  are CC BY-SA 4.0, matching Synesyn. See [`LICENSE`](../LICENSE).
- Target Godot 4 minor version: not yet chosen.
- A recommended projector and webcam hardware list: not yet written.
- Python companion versus a GDExtension long-term: Python and OpenCV are
  the starting boundary; whether calibration and scan later move in-process
  is open.
- Exact pose model and tracker: MediaPipe, YOLO-pose, ByteTrack and
  similar were named as examples, not as a selection.
- Depth Anything V2 variant licences, and any Godot camera features we
  intend to rely on: **to verify**.
