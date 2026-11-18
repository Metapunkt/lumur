# Surface compositor

PRD-003 slice 3: which launched app owns which surface, how conflicts resolve,
and how paint-mode confidence masking stays authoritative
([ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md),
[paint-mode.md](../godot/paint-mode.md),
[PRD-003](../product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
REQ-003-008–010).

Manifest fit: [manifest.md](manifest.md). Lifecycle / launcher:
[lifecycle.md](lifecycle.md).

## Ownership and layering

| Rule | Behaviour |
| --- | --- |
| Exclusive by default | One running app owns a bound surface’s **base** layer |
| Declared overlays | Manifest `shares: ["floor"]` may draw an overlay without stealing base |
| Conflict at launch | Second exclusive claim on the same surface fails; app stays installed |
| Regions | v1 allocates whole surfaces (plane ids); no sub-surface split |
| No geometry invention | Allocation never synthesises planes or fills low-confidence gaps |

Matching / fallback for a single app’s fit remain slice 1
(`fit_app_to_room` / `LumurAppFit`). The compositor adds the **ownership
table** across launched apps and refuses silent splits of one wall.

## Confidence masking

Compositing reuses paint-mode correspondence and the confidence threshold
from the room’s Godot export. Low-confidence / invalid projector pixels stay
unpainted. Apps cannot raise coverage by overriding the threshold on the
compositor path — the masking digest used in tests records painted vs
masked owned pixels under that threshold.

## Transitions

On pause, switch, or stop the compositor performs a deterministic **cut**:
release ownership and clear that app’s content on the next frame. Optional
crossfade may be added later without changing ownership rules. No room
rescan is required.

## APIs

**Python**

```python
from lumur.app import AppLifecycle
from lumur.paint.render import PaintAssignment

life = AppLifecycle.create(room)
life.install(manifest_a)
life.launch(manifest_a["id"])
life.compositor.set_content(app_id, {surface_id: PaintAssignment(...)})
frame = life.compositor.compose()
print(frame.digest, frame.painted_pixels, frame.masked_pixels)
life.pause(app_id)  # cut handoff
```

**Godot** (`addons/lumur`)

- `LumurCompositor` — ownership table, claim / release, cut transitions
- `LumurRoomRuntime.compositor` / `exclusive_owned_surface_ids`
- Paint clears on `pause_app` before ownership release

## Tests

```bash
cd companion
pytest tests/test_app_compositor_lifecycle.py
```

Covers two apps contending for one wall, optional missing-surface fallback,
masking digest stability, and switch/pause handoff on sim presets.

## Licence

Source code MIT. This document CC BY-SA 4.0.
