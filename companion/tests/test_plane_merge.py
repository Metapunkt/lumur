"""Coplanar merge / tilt reject: empty_room should not explode into surface_*."""

from __future__ import annotations

from lumur.scan.pipeline import scan_from_correspondence
from lumur.sim import SimRig, list_presets

from tests.test_room_scan import _calibration_from_gt, _capture_decode

# Before the merge/tilt-reject work (main @ 6e9e91b) every preset minted 9
# surfaces (floor + many surface_* + non_planar). After: far fewer, and
# empty_room has no surface_* spam.
BEFORE_COUNTS = {
    "empty_room": 9,
    "noisy_room": 9,
    "room_with_box": 9,
    "room_with_walkers": 9,
}


def test_surface_counts_reduced_and_fits_still_ok(tmp_path):
    from pathlib import Path

    from lumur.app.fit import fit_app_to_room
    from lumur.app.room_services import RoomServices
    from lumur.paint.export import export_godot_paint_assets
    from lumur.scan.pipeline import write_scan_package
    from lumur.schema.app import load_app_manifest

    repo = Path(__file__).resolve().parents[2]
    report = {}
    for scene in list_presets():
        rig = SimRig.from_scene_path(scene)
        decoded = _capture_decode(rig)
        calib = _calibration_from_gt(rig)
        result = scan_from_correspondence(decoded, calib, max_reprojection_error_px=4.0)
        n = len(result.segmentation.planes)
        surface_star = sum(1 for p in result.segmentation.planes if p.kind == "surface")
        report[scene] = {
            "before": BEFORE_COUNTS[scene],
            "after": n,
            "surface_star": surface_star,
            "labels": [p.label for p in result.segmentation.planes],
        }
        assert n < BEFORE_COUNTS[scene] or surface_star <= 2, report[scene]
        assert result.segmentation.floor_plane_id is not None

        room = write_scan_package(result, tmp_path / scene, calibration=calib)
        export_godot_paint_assets(room)
        services = RoomServices.load(room)
        for app in ("paint", "ripples"):
            manifest = load_app_manifest(repo / "apps" / app / "lumur.app.json")
            fit = fit_app_to_room(manifest, services)
            assert fit.ok, (scene, app, fit.unmet, report[scene])

    # empty_room specifically: cut the surface_* noise hard.
    assert report["empty_room"]["after"] <= 5
    assert report["empty_room"]["surface_star"] <= 1
    # Print-friendly summary for reviewers (pytest -s).
    print("plane surface counts before→after:", report)
