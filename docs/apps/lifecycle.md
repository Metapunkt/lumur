# App lifecycle and launcher

PRD-003 slice 3: install, launch, pause, resume, switch, stop; a headless
launcher; optional zone→app switching
([PRD-003](../product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
REQ-003-011–013). Compositor ownership: [compositor.md](compositor.md).
Input permissions: [input.md](input.md).

## States

| State | Meaning |
| --- | --- |
| `installed` | Manifest registered; not claiming surfaces |
| `running` | Fitted, claimed, receiving permitted inputs |
| `paused` | Ownership released (cut); **no** input-bus events |
| `stopped` | Unregistered from the bus; claims cleared |

Paused apps keep their install record and may resume (re-fit + re-claim).
Input subscriptions follow lifecycle: a paused session is skipped by
`AppInputBus` / `LumurAppInputBus` fan-out.

## Launcher

Headless API (required for complete-in-sim):

```python
from lumur.app import AppLifecycle, Launcher

life = AppLifecycle.create(room)
launcher = Launcher(life)
launcher.discover("apps/examples")
print(launcher.list_startable())
launcher.start("lumur.examples.ripples")
```

- `list_startable()` omits apps with a non-null manifest `bridge` field so
  bridge-hosted apps stay optional.
- Starting a second app pauses the current foreground and launches/resumes
  the target (`switch`).

Godot: `LumurLauncher` on `LumurRoomRuntime.launcher`.

## Zone→app switching (optional)

Configuration maps floor zone ids to installed app ids. Standing in a zone
for `min_dwell_s` (with `debounce_s`) switches the active app. Absent that
configuration, zones do **not** switch apps (they may still feed permitted
inputs).

Dwell / debounce reuse the shared core gate
(`lumur.audience.dwell.DwellGate` / `LumurDwellGate`) — same passer-by
rejection as audience steering, without requiring the bridge package.

```python
from lumur.app import ZoneAppSwitcher, ZoneSwitchConfig

cfg = ZoneSwitchConfig(
    zone_to_app={"left": "app.left", "right": "app.right"},
    min_dwell_s=1.5,
    debounce_s=0.8,
)
switcher = ZoneAppSwitcher(lifecycle=life, config=cfg)
switcher.attach_bus()  # privileged host path for zone_enter / zone_leave
switcher.process_event({"type": "zone_enter", "zone_id": "right", ...})
switcher.tick(timestamp)
```

The host path is **not** an ordinary app permission (ADR 0019).

## Tests

```bash
cd companion
pytest tests/test_app_compositor_lifecycle.py
```

Covers pause silence, launcher discover/start, zone dwell vs passers-by,
and deterministic replay of lifecycle + bus streams.

Godot headless smoke: `demo/scripts/headless_app_lifecycle.gd`.

## Licence

Source code MIT. This document CC BY-SA 4.0.
