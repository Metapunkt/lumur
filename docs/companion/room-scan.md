# Structured-light room scan

Second slice of [PRD-001](../product-requirements/PRD-001-CALIBRATE-PAINT-RIPPLE.md):
dense triangulation from Gray-code correspondences, per-pixel confidence,
robust floor/wall planes, and a versioned room package for Godot
([ADR 0012](../architectural-decisions/0012-versioned-room-package.md)).

Requires a calibration document from
[calibration.md](calibration.md). Development and CI use the simulated rig
([simulation.md](simulation.md), [ADR 0011](../architectural-decisions/0011-simulated-projector-camera-rig.md));
physical hardware is not required.

## Install

```bash
cd companion
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run (simulated)

Calibrate first, then scan. Prefer `room_with_box` when you care about
metric depth: plane-only calibration on a nearly planar room leaves
translation direction weakly constrained (see Limitations).

```bash
# 1) calibration
lumur-calibrate \
  --backend sim --scene room_with_box \
  --distance-m 1.08 \
  --point-a 31.2,17.2 --point-b 49.0,22.1 \
  -o /tmp/sim-calibration.json \
  --correspondence-out /tmp/sim-corr.npz

# 2) room scan (re-captures Gray-code, or reuse --correspondence)
lumur-scan \
  --backend sim --scene room_with_box \
  --calibration /tmp/sim-calibration.json \
  -o /tmp/sim-room

# Optional: evaluate geometry with sim ground-truth pose
lumur-scan \
  --backend sim --scene room_with_box \
  --calibration /tmp/sim-calibration.json \
  --use-sim-gt-pose \
  -o /tmp/sim-room-gt
```

The CLI prints a JSON coverage report (valid fraction, mean confidence,
worst region, plane-fit residuals) and writes the room package directory.

## Run (OpenCV hardware)

```bash
lumur-scan \
  --backend opencv \
  --camera 0 \
  --projector-width 1920 --projector-height 1080 \
  --monitor 1 \
  --calibration room/calibration.json \
  -o room/scan
```

## Room package schema (`lumur.room` v1.0)

Package directory layout:

| File | Role |
| --- | --- |
| `room.json` | Versioned manifest + planes + report |
| `points.npz` | Dense per-camera-pixel arrays |
| `projector_map.npz` | Dense projector→camera correspondence |

### `room.json`

| Field | Meaning |
| --- | --- |
| `schema` | Always `"lumur.room"`. |
| `schema_version` | `"1.0"` for this slice. |
| `created_at` | UTC ISO-8601 timestamp. |
| `projector_resolution` / `camera_resolution` | `[width, height]`. |
| `calibration_ref` | Path to the source calibration JSON when known. |
| `calibration` | Embedded summary (`camera`, `projector`, `stereo`, `method`). |
| `coordinate_frame` | `"camera"` — points live in the calibration camera frame. |
| `planes[]` | `{plane_id, normal, d, inlier_count, residual_rms_m, kind, label}` with `kind` in `floor`, `wall`, `surface`, `non_planar`. Plane equation: `normal · X + d = 0`. |
| `floor_plane_id` | Id of the floor plane, or `null` if unidentified. |
| `arrays` | Filenames for `points` and `projector_map`. |
| `mask_codes` | Legend for the `mask` array (0 valid … 4 outlier). |
| `report` | Coverage / confidence summary (see below). |

### `points.npz`

All arrays are shaped like the camera image `(H, W)` unless noted.

| Array | Dtype | Meaning |
| --- | --- | --- |
| `points` | float32 HxWx3 | Triangulated XYZ in camera frame; NaN where invalid. |
| `depth` | float32 HxW | Optical-axis Z (metres); NaN where invalid. |
| `normals` | float32 HxWx3 | Plane-derived normals; NaN off assigned planes. |
| `confidence` | float32 HxW | Combined decode × angle × residual confidence in `[0, 1]`. |
| `mask` | uint8 HxW | 0 valid, 1 invalid/shadowed, 2 low confidence, 3 bad triangulation, 4 outlier. |
| `surface_id` | int32 HxW | Stable plane/surface id; 0 = unassigned. |
| `proj_u` / `proj_v` | float32 HxW | Camera→projector Gray-code correspondence. |
| `reprojection_error_px` | float32 HxW | Max cam/proj reprojection error. |
| `triangulation_angle_deg` | float32 HxW | Angle at the 3D point between device centres. |

### `projector_map.npz`

Shaped like the projector image `(proj_H, proj_W)`. Built by scattering
camera→projector samples (highest confidence wins). Used later for
paint-the-room without an authored mesh.

| Array | Meaning |
| --- | --- |
| `cam_u` / `cam_v` | Camera pixel for this projector pixel (NaN if unknown). |
| `confidence` | Confidence of the winning sample. |
| `valid` | Bool coverage mask. |

## Confidence and coverage report

Printed by `lumur-scan` and stored under `report` in `room.json`:

- `covered_fraction` — pixels with a finite depth estimate.
- `valid_fraction` — pixels with `mask == valid`.
- `mean_confidence` / `median_confidence` — over valid pixels.
- `mask_histogram` — counts per mask code.
- `worst_region` — tile with lowest mean confidence (`bbox` in camera pixels).
- `plane_residuals` — per-plane RMS (metres) and inlier counts.
- `floor_plane_id` — echoed for convenience.

## How the scan works

1. Decode Gray-code (or load a saved correspondence `.npz`).
2. Triangulate each valid camera pixel against its projector correspondence
   using calibration intrinsics and stereo `R`/`T`.
3. Combine confidence from decode contrast, triangulation angle, and
   reprojection residual; mask shadowed / degenerate / outlier pixels.
4. Fit dominant planes with sequential RANSAC; label the floor (upright
   OpenCV camera: gravity ≈ `+Y`); keep leftover points as `non_planar`
   instead of bridging gaps.
5. Write the room package.

## Limitations

- **Planar pose ambiguity.** Homography-based calibration on a mostly planar
  room constrains translation direction only weakly. For metric depth checks,
  use `room_with_box`, refine pose, or pass `--use-sim-gt-pose` on the sim.
- **Pattern resolution.** Preset sim projectors are 64×48 so tests stay fast;
  Gray-code quantisation dominates absolute depth error there. Relative
  ray-depth error is the fair metric at that resolution.
- **No mesh yet.** Normals come from fitted planes. A confidence-filtered
  triangle mesh is optional later work; paint-the-room only needs the
  correspondence maps.
- **Floor heuristic.** Floor identification assumes an approximately upright
  camera (OpenCV `+Y` with gravity). Mounting that breaks the assumption
  will need an explicit gravity / up vector later.

## Tests

```bash
cd companion
pytest tests/test_room_scan.py -q
```

## Licence

Companion source is MIT. This document is CC BY-SA 4.0.
