"""PRD-003 slice 1: lumur.app manifest validation and room-fit in sim."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from lumur.app import (
    APP_SCHEMA_VERSION,
    FitError,
    RoomServices,
    fit_app_to_room,
    load_app_manifest,
    validate_app_manifest,
)
from lumur.paint.export import export_godot_paint_assets
from lumur.schema.app import build_app_manifest

from tests.test_paint import _scan_room

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "apps" / "examples"
SCENES = ("empty_room", "room_with_box", "noisy_room")


def _room_services(tmp_path: Path, scene: str) -> RoomServices:
    room_dir, _rig, _result = _scan_room(tmp_path / scene, scene=scene)
    export_godot_paint_assets(room_dir)
    return RoomServices.load(room_dir)


def _floor_manifest(**surface_extra) -> dict:
    req = {
        "key": "floor",
        "role": "floor",
        "required": True,
        **surface_extra,
    }
    return build_app_manifest(
        app_id="test.floor",
        name="Floor test",
        version="0.0.1",
        scene="res://apps/examples/ripples/ripple_app.tscn",
        surfaces=[req],
        inputs=["footstep"],
    )


def _wall_manifest(**surface_extra) -> dict:
    req = {
        "key": "panel",
        "role": "wall",
        "min_width_m": 2.0,
        "required": True,
        **surface_extra,
    }
    return build_app_manifest(
        app_id="test.wall",
        name="Wall test",
        version="0.0.1",
        scene="res://apps/examples/wall_panel/wall_panel_app.tscn",
        surfaces=[req],
        inputs=[],
    )


# --- Manifest validation -------------------------------------------------


def test_example_manifests_validate():
    for name in ("ripples", "wall_panel"):
        path = EXAMPLES / name / "lumur.app.json"
        doc = load_app_manifest(path)
        assert doc["schema"] == "lumur.app"
        assert doc["schema_version"] == APP_SCHEMA_VERSION


def test_valid_manifest_ignores_unknown_fields():
    doc = _floor_manifest()
    doc["future_hint"] = {"nested": True}
    doc["surfaces"][0]["hint"] = "ok"
    validate_app_manifest(doc)


def test_invalid_manifest_rejects_pixel_placement():
    doc = _floor_manifest()
    doc["surfaces"][0]["pixel_rect"] = [0, 0, 64, 48]
    with pytest.raises(ValueError, match="placement"):
        validate_app_manifest(doc)


def test_invalid_manifest_rejects_plane_id_and_uv():
    doc = _floor_manifest()
    bad = copy.deepcopy(doc)
    bad["surfaces"][0]["plane_id"] = 3
    with pytest.raises(ValueError, match="placement"):
        validate_app_manifest(bad)
    bad2 = copy.deepcopy(doc)
    bad2["surfaces"][0]["uv_quad"] = [[0, 0], [1, 0], [1, 1], [0, 1]]
    with pytest.raises(ValueError, match="placement"):
        validate_app_manifest(bad2)


def test_invalid_manifest_unknown_input():
    doc = _floor_manifest()
    doc["inputs"] = ["footstep", "telepathy"]
    with pytest.raises(ValueError, match="unknown input"):
        validate_app_manifest(doc)


def test_version_handling_rejects_unsupported_schema_version():
    doc = _floor_manifest()
    doc["schema_version"] = "2.0"
    with pytest.raises(ValueError, match="unsupported schema_version"):
        validate_app_manifest(doc)
    doc["schema_version"] = "0.9"
    with pytest.raises(ValueError, match="unsupported schema_version"):
        validate_app_manifest(doc)


def test_version_handling_rejects_wrong_schema_id():
    doc = _floor_manifest()
    doc["schema"] = "lumur.room"
    with pytest.raises(ValueError, match="expected schema"):
        validate_app_manifest(doc)


def test_duplicate_surface_keys_rejected():
    doc = build_app_manifest(
        app_id="test.dup",
        name="Dup",
        version="0.0.1",
        scene="res://x.tscn",
        surfaces=[
            {"key": "a", "role": "floor"},
            {"key": "a", "role": "wall"},
        ],
        inputs=[],
    )
    with pytest.raises(ValueError, match="duplicate"):
        validate_app_manifest(doc)


# --- Room services facade ------------------------------------------------


@pytest.mark.parametrize("scene", SCENES)
def test_room_services_exposes_surfaces_roles_floor(tmp_path: Path, scene: str):
    room = _room_services(tmp_path, scene)
    assert room.floor_plane_id is not None
    assert room.surface_by_id(room.floor_plane_id) is not None
    assert "floor" in room.role_index
    floor = room.surface_by_role("floor")
    assert floor is not None
    assert floor.width_m > 0.5
    assert 0.0 <= floor.mean_confidence <= 1.0
    assert room.list_roles()
    # Generated handles may be empty; API still present.
    assert isinstance(room.generated_textures, dict)
    assert room.paint_manifest is not None
    # Paint export carries fit metrics for Godot.
    painted = [
        s for s in room.paint_manifest["surfaces"] if s.get("kind") != "non_planar"
    ]
    assert painted and "width_m" in painted[0] and "mean_confidence" in painted[0]


# --- Fit success / failure / determinism ---------------------------------


@pytest.mark.parametrize("scene", SCENES)
def test_fit_floor_success_all_presets(tmp_path: Path, scene: str):
    room = _room_services(tmp_path, scene)
    manifest = load_app_manifest(EXAMPLES / "ripples" / "lumur.app.json")
    # Noisy floor confidence can sit near ~0.23; example asks 0.15.
    result = fit_app_to_room(manifest, room)
    assert result.ok
    binding = result.bindings["floor"]
    assert binding.surface_id == room.floor_plane_id
    assert binding.surface_id == room.role_index["floor"]


def test_fit_wall_ge_2m_room_with_box(tmp_path: Path):
    room = _room_services(tmp_path, "room_with_box")
    walls = [s for s in room.surfaces if s.kind == "wall" or any(
        r.startswith("wall_") for r in s.roles
    )]
    wide = [s for s in walls if s.width_m >= 2.0 and s.mean_confidence >= 0.15]
    assert wide, "room_with_box should expose a wall >= 2 m for the example"
    result = fit_app_to_room(
        load_app_manifest(EXAMPLES / "wall_panel" / "lumur.app.json"), room
    )
    assert result.ok
    sid = result.bindings["panel"].surface_id
    assert sid is not None
    # Deterministic preference: largest width, then lowest id.
    expected = sorted(wide, key=lambda s: (-s.width_m, s.surface_id))[0]
    assert sid == expected.surface_id


def test_fit_wall_hard_fail_empty_room(tmp_path: Path):
    """empty_room scan often lacks kind=wall / wall_* roles → unmet_surface."""
    room = _room_services(tmp_path, "empty_room")
    manifest = load_app_manifest(EXAMPLES / "wall_panel" / "lumur.app.json")
    wall_roles = [r for r in room.list_roles() if r == "wall" or r.startswith("wall_")]
    if wall_roles:
        # If classification improves, still assert required path works when
        # constraints cannot be met by forcing an absurd width.
        manifest = _wall_manifest(min_width_m=50.0)
    with pytest.raises(FitError) as excinfo:
        fit_app_to_room(manifest, room)
    err = excinfo.value
    assert err.result.ok is False
    assert err.result.unmet
    assert err.result.unmet[0].reason == "unmet_surface"
    assert "unmet_surface" in str(err)


def test_fit_optional_fallback_null_binding(tmp_path: Path):
    room = _room_services(tmp_path, "empty_room")
    manifest = _wall_manifest(required=False, min_width_m=50.0)
    result = fit_app_to_room(manifest, room)
    assert result.ok
    assert result.bindings["panel"].surface_id is None
    assert result.bindings["panel"].optional_unmet is True
    assert result.unmet and result.unmet[0].reason == "unmet_surface"


def test_fit_confidence_filter(tmp_path: Path):
    room = _room_services(tmp_path, "noisy_room")
    floor = room.surface_by_role("floor")
    assert floor is not None
    # Ask above observed mean → hard fail.
    manifest = _floor_manifest(min_confidence=min(0.99, floor.mean_confidence + 0.5))
    with pytest.raises(FitError):
        fit_app_to_room(manifest, room)
    # Ask at or below observed mean → success.
    ok_manifest = _floor_manifest(
        min_confidence=max(0.0, floor.mean_confidence - 0.05)
    )
    result = fit_app_to_room(ok_manifest, room)
    assert result.ok
    assert result.bindings["floor"].surface_id == floor.surface_id


@pytest.mark.parametrize("scene", SCENES)
def test_fit_deterministic_binding(tmp_path: Path, scene: str):
    room = _room_services(tmp_path, scene)
    manifest = _floor_manifest(min_confidence=0.05)
    a = fit_app_to_room(manifest, room)
    b = fit_app_to_room(manifest, room)
    assert a.to_dict() == b.to_dict()
    # Re-load package; same binding.
    room2 = RoomServices.load(room.package_dir)
    c = fit_app_to_room(manifest, room2)
    assert c.bindings["floor"].surface_id == a.bindings["floor"].surface_id


def test_fit_prefers_larger_then_lower_id(tmp_path: Path):
    room = _room_services(tmp_path, "room_with_box")
    # Two wall requests: first takes the largest; second takes the next.
    manifest = build_app_manifest(
        app_id="test.two_walls",
        name="Two walls",
        version="0.0.1",
        scene="res://x.tscn",
        surfaces=[
            {"key": "a", "role": "wall", "min_width_m": 0.5, "required": True},
            {"key": "b", "role": "wall", "min_width_m": 0.5, "required": True},
        ],
        inputs=[],
    )
    walls = [
        s
        for s in room.surfaces
        if s.kind == "wall" or any(r.startswith("wall_") for r in s.roles)
    ]
    if len(walls) < 2:
        pytest.skip("need at least two wall candidates")
    ordered = sorted(walls, key=lambda s: (-s.width_m, s.surface_id))
    result = fit_app_to_room(manifest, room)
    assert result.bindings["a"].surface_id == ordered[0].surface_id
    assert result.bindings["b"].surface_id == ordered[1].surface_id


def test_fit_raise_on_unmet_false_returns_result(tmp_path: Path):
    room = _room_services(tmp_path, "empty_room")
    manifest = _wall_manifest(min_width_m=50.0)
    result = fit_app_to_room(manifest, room, raise_on_unmet=False)
    assert result.ok is False
    assert result.unmet[0].to_dict()["reason"] == "unmet_surface"


def test_fit_respects_exclusive_owned(tmp_path: Path):
    room = _room_services(tmp_path, "room_with_box")
    floor_id = room.role_index["floor"]
    manifest = _floor_manifest(min_confidence=0.05)
    with pytest.raises(FitError):
        fit_app_to_room(manifest, room, exclusive_owned={floor_id})


def test_no_synesyn_import_in_core_app_module():
    """Lumur core app layer must not depend on Synesyn (PRD-003)."""
    import lumur.app as app_pkg
    import lumur.schema.app as schema_app

    for mod in (app_pkg, schema_app):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "synesyn" not in src.lower()
        assert "lumur_synesyn" not in src
