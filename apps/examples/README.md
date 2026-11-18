# Example app manifests (PRD-003 slice 1)

Minimal ``lumur.app`` examples for room-fit tests. Full repackaging of the
bundled ripples / paint / Story Stage demos is **slice 4** — these packages
only prove the manifest shape and surface-request vocabulary.

| App | Requests | Notes |
| --- | --- | --- |
| [`ripples/`](ripples/) | floor + `footstep` input | Fits any sim room with a floor plane |
| [`wall_panel/`](wall_panel/) | one wall ≥ 2 m | Hard-fails on wall-poor scans (e.g. `empty_room` as classified today) |

See [docs/apps/manifest.md](../../docs/apps/manifest.md).
