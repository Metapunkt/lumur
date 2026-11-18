# Generation from apps

PRD-003 slice 4: apps with ``generation: true`` may request per-surface
content through the existing `SurfaceGenerator` interface
([ADR 0016](../architectural-decisions/0016-pluggable-surface-generators.md),
[ADR 0018](../architectural-decisions/0018-surface-allocation-and-compositing.md),
[PRD-003](../product-requirements/PRD-003-LUMUR-OS-APPLICATION-LAYER.md)
REQ-003-014).

Standalone ComfyUI: [comfyui.md](../companion/comfyui.md). Optional Hub
provider (bridge only): [synesyn.md](../bridge/synesyn.md). Ownership rules:
[compositor.md](compositor.md).

## Rules

1. Manifest must set `"generation": true`.
2. The app must be **running** and have a fit binding for the surface key.
3. The compositor must show the app **owns or overlays** that surface —
   generation never writes another app’s base layer behind its back.
4. Requests are asynchronous / off the projector path. Null or failing
   providers leave last-good or authored content.
5. Core and bundled non-bridge apps do **not** import Synesyn types or Hub
   URLs. Hub generation is only available when `lumur_synesyn` is present.

## Python

```python
from lumur.app import AppLifecycle, AppGenerationService, Launcher
from lumur.generate.provider import NullSurfaceGenerator

life = AppLifecycle.create(room)
launcher = Launcher(life)
launcher.discover("apps/paint")
launcher.start("lumur.paint")

gen = AppGenerationService(lifecycle=life, provider=NullSurfaceGenerator())
entry = gen.request("lumur.paint", "floor")  # owned surface only
```

With a mocked ComfyUI server, inject `ComfyUISurfaceGenerator`. With the
bridge present, inject `SynesynHubSurfaceGenerator` for Story Stage.

## Godot

`LumurAppGeneration` gates `LumurSurfaceGenerator` the same way. Paint’s
bundled boot requests the floor only when the compositor confirms ownership.

## Tests

```bash
cd companion
pytest tests/test_app_bundled_generation.py
```

## Licence

Source code MIT. This document CC BY-SA 4.0.
