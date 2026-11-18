# Lumur

Projection-mapping runtime for Godot that makes rooms come alive
with just a webcam and a projector. A spiritual successor to Microsoft's
RoomAlive providing structured-light room scanning, surface-aware apps, interaction
through people's movement, and optional ComfyUI driven content generation. No Kinect
required.

The name joins *lumen* (light) with *mur* (French, from Latin *murus*: wall).

Geometry is authoritative: the system measures the room occasionally, tracks
only the interactions that matter, and renders continuously. Experiences are
apps that target named surfaces, so the same app can be installed in another
room.

**Status:** early implementation. Founding intent lives in the
[scratchpad](docs/scratchpad.md),
[architectural decisions](docs/architectural-decisions/README.md) and
[product requirements](docs/product-requirements/README.md). The first code
slice is the Python calibration companion under [`companion/`](companion/).

## Documentation

Start at [`docs/`](docs/README.md). Calibration runbook and JSON schema:
[`docs/companion/calibration.md`](docs/companion/calibration.md).

## Licence

© 2026 “Lumur” by Ayodele Arigbabu

Source code is MIT. Text, documentation, and other website material are
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). See
[`LICENSE`](LICENSE).

## Credits

Built by **Ayodele Arigbabu** with the help of cheerful AI agents for the Metapunkt project.
