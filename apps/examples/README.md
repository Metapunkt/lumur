# Example app manifests (PRD-003)

Minimal ``lumur.app`` fixtures for room-fit and schema tests. Full bundled
scenes live under [`../ripples`](../ripples) and [`../paint`](../paint)
(slice 4); Story Stage ships only with the optional bridge.

| App | Requests | Notes |
| --- | --- | --- |
| [`ripples/`](ripples/) | floor + `footstep` input | Fits any sim room with a floor plane |
| [`wall_panel/`](wall_panel/) | one wall ≥ 2 m | Hard-fails on wall-poor scans (e.g. `empty_room`) |

See [docs/apps/manifest.md](../../docs/apps/manifest.md).
