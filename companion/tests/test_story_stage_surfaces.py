"""PRD-002 slice 3: Story Stage layer → surface mapping in the Lumur sim."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from lumur.paint.export import export_godot_paint_assets
from lumur.sim.render import render_camera_view
from lumur_synesyn.story_stage_compose import (
    aspect_fit_size,
    compose_layer_texture,
    frame_to_rgb,
    safe_box,
)
from lumur_synesyn.story_stage_layers import (
    LAYER_AMBIENCE,
    LAYER_BACKDROP,
    LAYER_CAPTION,
    LAYER_CHARACTER,
    LAYER_CLIP,
    LayerFrame,
    StubStoryStageSource,
)
from lumur_synesyn.story_stage_layout import (
    StoryStageLayout,
    layout_from_scenario,
    resolve_surface_role,
)
from lumur_synesyn.story_stage_project import project_from_source

from tests.test_paint import _scan_room


def test_default_layout_preferences():
    layout = StoryStageLayout()
    assert layout.preference_for(LAYER_BACKDROP)[0] == "wall_1"
    assert layout.preference_for(LAYER_CHARACTER)[0] == "wall_2"
    assert layout.preference_for(LAYER_AMBIENCE)[0] == "floor"
    assert layout.preference_for(LAYER_CAPTION)[0] == "wall_1"
    assert layout.preference_for("portrait")[0] == "wall_2"
    assert layout.preference_for("flashhead")[0] == "wall_2"


def test_layout_fallback_when_side_wall_missing():
    roles = {"floor": 1, "wall_1": 2}
    layout = StoryStageLayout()
    assert resolve_surface_role(LAYER_CHARACTER, roles, layout) == "wall_1"
    assert resolve_surface_role(LAYER_BACKDROP, roles, layout) == "wall_1"
    assert resolve_surface_role(LAYER_AMBIENCE, roles, layout) == "floor"
    assert resolve_surface_role(LAYER_CHARACTER, {"floor": 1}, layout) == "floor"
    assert resolve_surface_role(LAYER_BACKDROP, set(), layout) is None


def test_scenario_layout_override_and_unknown_sections_ignored():
    scenario = {
        "vis_story": {"enabled": "true", "prompt": "ignored by lumur"},
        "lull_protocol": {"enabled": "true"},
        "lumur_audience": {"enabled": "true"},  # slice 4 — ignored here
        "lumur_layout": {
            "backdrop": "wall_2",
            "character": "wall_1",
            "ambience": "floor",
            "safe_areas": {"caption": {"left": 0.1, "right": 0.1, "top": 0.8, "bottom": 0.05}},
            "mystery_future_key": {"should": "be ignored"},
        },
    }
    layout = layout_from_scenario(scenario)
    assert layout.overrides[LAYER_BACKDROP] == "wall_2"
    assert layout.overrides[LAYER_CHARACTER] == "wall_1"
    assert layout.safe_area_for(LAYER_CAPTION).top == pytest.approx(0.8)
    # Defaults still present for clip when not overridden.
    assert layout.preference_for(LAYER_CLIP)[0] == "wall_2"


def test_aspect_fit_and_safe_area_compose():
    frame = LayerFrame(layer=LAYER_CHARACTER, color=(0.0, 1.0, 0.0))
    # Tall content into a wide safe box → pillarbox.
    fw, fh = aspect_fit_size(10, 20, 40, 20)
    assert fw == 10 and fh == 20
    area = StoryStageLayout().safe_area_for(LAYER_CAPTION)
    x0, y0, x1, y1 = safe_box(64, 64, area)
    assert y0 >= int(0.72 * 64) - 1  # caption band is lower wall region
    tex = compose_layer_texture(frame, surface_size=(64, 64), safe_area=area)
    assert tex.shape == (64, 64, 3)
    # Outside the caption band stays near clear (black).
    assert float(tex[10, 32].mean()) < 0.05
    # Inside the band is green-dominant.
    cy = (y0 + y1) // 2
    assert 0 <= cy < 64
    assert float(tex[cy, 32, 1]) > 0.8


def test_clip_crossfade_transition():
    prev = np.zeros((16, 16, 3), dtype=np.float32)
    prev[:] = (0.0, 1.0, 0.0)
    frame = LayerFrame(
        layer=LAYER_CLIP,
        color=(1.0, 0.5, 0.0),
        transition="crossfade",
        transition_from=prev,
        meta={"fade": 0.5},
    )
    rgb = frame_to_rgb(frame, width=16, height=16)
    # Mid-fade: green channel between character and clip.
    assert 0.2 < float(rgb[..., 1].mean()) < 0.9
    assert float(rgb[..., 0].mean()) > 0.2


def test_stub_snapshot_timeline():
    src = StubStoryStageSource(include_clip=True, clip_start_s=0.5, clip_fade_s=0.25)
    early = src.snapshot(0.0)
    assert LAYER_CLIP not in early.frames
    assert LAYER_BACKDROP in early.frames
    late = src.snapshot(1.0)
    assert LAYER_CLIP in late.frames
    mid = src.snapshot(0.6)
    assert mid.frames[LAYER_CLIP].transition == "crossfade"
    assert 0.0 < float(mid.frames[LAYER_CLIP].meta["fade"]) < 1.0


def test_project_binding_on_scanned_room(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    godot_dir = export_godot_paint_assets(room_dir)
    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    role_index = {str(k): int(v) for k, v in manifest["role_index"].items()}
    assert "floor" in role_index
    wall_roles = [
        k
        for k in role_index
        if k.startswith("wall_") and k.split("_", 1)[1].isdigit()
    ]
    assert wall_roles

    src = StubStoryStageSource()
    projection, painted = project_from_source(src, godot_dir, time_s=0.0)
    binding = projection.binding()
    assert binding[LAYER_BACKDROP] == "wall_1"
    assert binding[LAYER_AMBIENCE] == "floor"
    if "wall_2" in role_index:
        assert binding[LAYER_CHARACTER] == "wall_2"
    else:
        assert binding[LAYER_CHARACTER] == "wall_1"
    assert painted.shape[2] == 3
    assert painted.max() > 0.5


def _agree_masks(godot_dir: Path, result, buffers):
    sid_cam = result.segmentation.surface_id
    sid_proj = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    assert sid_proj is not None
    pu = np.rint(buffers.proj_u).astype(np.int32)
    pv = np.rint(buffers.proj_v).astype(np.int32)
    ph, pw = sid_proj.shape
    lit = buffers.valid_proj & (buffers.depth > 0)
    inside = lit & (pu >= 0) & (pu < pw) & (pv >= 0) & (pv < ph)
    proj_sid = np.zeros(sid_cam.shape, dtype=np.int32)
    proj_sid[inside] = sid_proj[pv[inside], pu[inside]]
    agree = inside & (proj_sid == sid_cam)
    return agree, sid_cam


def test_stub_layers_land_on_intended_surfaces_through_sim(tmp_path: Path):
    """Stub Story Stage → layout → paint → sim projector→camera chromaticity."""
    room_dir, rig, result = _scan_room(tmp_path)
    rig.scene.camera.noise_std = 0.0
    rig.scene.camera.blur_sigma = 0.0
    rig.scene.camera.ambient = 2.0

    godot_dir = export_godot_paint_assets(room_dir)
    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    role_index = {str(k): int(v) for k, v in manifest["role_index"].items()}
    floor_id = int(role_index["floor"])
    wall_1 = int(role_index["wall_1"])
    has_wall_2 = "wall_2" in role_index
    wall_2 = int(role_index["wall_2"]) if has_wall_2 else wall_1

    src = StubStoryStageSource(include_clip=False)
    projection, painted = project_from_source(src, godot_dir, time_s=0.0)
    assert projection.role_binding[LAYER_BACKDROP] == "wall_1"
    assert projection.role_binding[LAYER_AMBIENCE] == "floor"
    if has_wall_2:
        assert projection.role_binding[LAYER_CHARACTER] == "wall_2"

    pattern = np.clip(painted * 255.0, 0, 255).astype(np.uint8)
    buffers = render_camera_view(
        rig.scene.room,
        rig.scene.camera,
        rig.scene.projector,
        pattern,
        retain_color=True,
        rng=np.random.default_rng(0),
    )
    cam = buffers.image.astype(np.float32)
    agree, sid_cam = _agree_masks(godot_dir, result, buffers)

    floor_sel = agree & (sid_cam == floor_id)
    wall1_sel = agree & (sid_cam == wall_1)
    assert int(floor_sel.sum()) > 10
    assert int(wall1_sel.sum()) > 10

    floor_rgb = cam[floor_sel]
    wall1_rgb = cam[wall1_sel]
    # Ambience (red) on floor; backdrop (blue) on wall_1.
    assert float(floor_rgb[:, 0].mean()) > float(floor_rgb[:, 2].mean()) * 1.2
    assert float(wall1_rgb[:, 2].mean()) > float(wall1_rgb[:, 0].mean()) * 1.15

    if has_wall_2 and wall_2 != wall_1:
        wall2_sel = agree & (sid_cam == wall_2)
        if int(wall2_sel.sum()) > 10:
            wall2_rgb = cam[wall2_sel]
            # Character (green) on side wall.
            assert float(wall2_rgb[:, 1].mean()) > float(wall2_rgb[:, 0].mean()) * 1.1
            assert float(wall2_rgb[:, 1].mean()) > float(wall2_rgb[:, 2].mean()) * 1.1


def test_scenario_override_swaps_surfaces_in_sim(tmp_path: Path):
    room_dir, rig, result = _scan_room(tmp_path)
    rig.scene.camera.noise_std = 0.0
    rig.scene.camera.blur_sigma = 0.0
    rig.scene.camera.ambient = 2.0
    godot_dir = export_godot_paint_assets(room_dir)
    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    role_index = {str(k): int(v) for k, v in manifest["role_index"].items()}
    if "wall_2" not in role_index:
        pytest.skip("room_with_box needs wall_2 for swap check")

    scenario = {
        "lumur_layout": {
            "backdrop": "wall_2",
            "character": "wall_1",
            "ambience": "floor",
        },
        "vis_story": {"enabled": "true"},
    }
    src = StubStoryStageSource(scenario=scenario, include_clip=False)
    projection, painted = project_from_source(src, godot_dir, time_s=0.0)
    assert projection.role_binding[LAYER_BACKDROP] == "wall_2"
    assert projection.role_binding[LAYER_CHARACTER] == "wall_1"

    pattern = np.clip(painted * 255.0, 0, 255).astype(np.uint8)
    buffers = render_camera_view(
        rig.scene.room,
        rig.scene.camera,
        rig.scene.projector,
        pattern,
        retain_color=True,
        rng=np.random.default_rng(1),
    )
    cam = buffers.image.astype(np.float32)
    agree, sid_cam = _agree_masks(godot_dir, result, buffers)
    wall1 = int(role_index["wall_1"])
    wall2 = int(role_index["wall_2"])
    w1 = cam[agree & (sid_cam == wall1)]
    w2 = cam[agree & (sid_cam == wall2)]
    assert int((agree & (sid_cam == wall1)).sum()) > 10
    assert int((agree & (sid_cam == wall2)).sum()) > 10
    # Character green on wall_1; backdrop blue on wall_2.
    assert float(w1[:, 1].mean()) > float(w1[:, 2].mean()) * 1.05
    assert float(w2[:, 2].mean()) > float(w2[:, 0].mean()) * 1.1


def test_core_lumur_has_no_synesyn_story_stage_imports():
    """Boundary: core must not import the bridge or Synesyn packages."""
    root = Path(__file__).resolve().parents[2]
    forbidden_imports = ("lumur_synesyn", "synesyn_core", "story_stage")
    hits: list[str] = []
    for base in [root / "addons" / "lumur", root / "companion" / "lumur"]:
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".gd", ".py"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for token in forbidden_imports:
                # Match import / preload paths, not provenance field name comments.
                if f"import {token}" in text or f"from {token}" in text:
                    hits.append(f"{path.relative_to(root)}:import {token}")
                if f"res://addons/{token}" in text:
                    hits.append(f"{path.relative_to(root)}:preload {token}")
    assert hits == [], f"Synesyn leakage into core: {hits}"
