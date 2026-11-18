# Bundled Lumur apps (PRD-003 slice 4)

Installable `lumur.app` packages that prove the application layer.

| App | Path | Notes |
| --- | --- | --- |
| **Paint the room** | [`paint/`](paint/) | Exclusive floor (+ optional wall); `generation: true` |
| **Footstep ripples** | [`ripples/`](ripples/) | Floor overlay via `shares: ["floor"]`; `inputs: ["footstep"]` |
| **Story Stage** | [`../addons/lumur_synesyn/apps/story_stage/`](../addons/lumur_synesyn/apps/story_stage/) | Bridge-only (`"bridge": "lumur_synesyn"`); absent from core `list_startable` |

Schema fixtures used by earlier slices remain under [`examples/`](examples/).

Authoring guide: [docs/apps/manifest.md](../docs/apps/manifest.md).
Generation from apps: [docs/apps/generation.md](../docs/apps/generation.md).
