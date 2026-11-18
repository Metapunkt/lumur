"""PRD-003 slice 4: bundled apps + generation from apps (sim / mocks)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lumur.app import (
    AppGenerationService,
    AppLifecycle,
    AppState,
    GenerationDenied,
    Launcher,
    RoomServices,
    bridge_app_roots,
    load_app_manifest,
)
from lumur.generate.comfy_provider import ComfyUISurfaceGenerator
from lumur.generate.presets import surface_role_tag
from lumur.generate.provider import NullSurfaceGenerator
from lumur.generate.types import JobStatus
from lumur.paint.export import export_godot_paint_assets
from lumur.paint.render import PaintAssignment
from lumur.track.footsteps import FootstepEvent

from tests.mock_comfyui import MockComfyUIServer
from tests.mock_synesyn_hub import MockSynesynHubServer
from tests.test_paint import _scan_room

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS = REPO_ROOT / "apps"
RIPPLES = APPS / "ripples"
PAINT = APPS / "paint"
STORY = REPO_ROOT / "addons" / "lumur_synesyn" / "apps" / "story_stage"
PRESETS = ("empty_room", "room_with_box", "noisy_room")


def _room(tmp_path: Path, scene: str = "room_with_box") -> RoomServices:
    room_dir, _rig, _result = _scan_room(tmp_path / scene, scene=scene)
    export_godot_paint_assets(room_dir)
    return RoomServices.load(room_dir)


def _life(tmp_path: Path, scene: str = "room_with_box") -> AppLifecycle:
    return AppLifecycle.create(_room(tmp_path, scene))


# --- Bundled install / launch on presets (REQ-003-015 / 017) --------------


@pytest.mark.parametrize("scene", PRESETS)
def test_bundled_paint_and_ripples_install_launch(tmp_path: Path, scene: str):
    life = _life(tmp_path, scene)
    launcher = Launcher(life)
    found = launcher.discover(APPS)
    ids = {r.app_id for r in found}
    assert "lumur.paint" in ids
    assert "lumur.ripples" in ids

    startable = {e["app_id"] for e in launcher.list_startable()}
    assert "lumur.paint" in startable
    assert "lumur.ripples" in startable
    assert "lumur.synesyn.story_stage" not in startable

    paint = launcher.start("lumur.paint")
    assert paint.state == AppState.RUNNING
    floor_id = life.room.floor_plane_id
    assert floor_id is not None
    assert life.compositor.ownership[floor_id].base_app_id == "lumur.paint"

    # Ripples is a pure overlay (shares=["floor"]) — concurrent, no pause.
    ripples = launcher.start("lumur.ripples")
    assert ripples.state == AppState.RUNNING
    assert life.apps["lumur.paint"].state == AppState.RUNNING
    entry = life.compositor.ownership[floor_id]
    assert entry.base_app_id == "lumur.paint"
    assert ("lumur.ripples", "floor") in entry.overlays


@pytest.mark.parametrize("scene", PRESETS)
def test_ripples_overlay_painted_floor_compose(tmp_path: Path, scene: str):
    life = _life(tmp_path, scene)
    launcher = Launcher(life)
    launcher.discover(RIPPLES, PAINT)
    launcher.start("lumur.paint")
    floor_id = life.room.floor_plane_id
    assert floor_id is not None
    life.compositor.set_content(
        "lumur.paint",
        {floor_id: PaintAssignment(surface_id=floor_id, color=(0.8, 0.1, 0.1))},
    )
    launcher.start("lumur.ripples")
    # Overlay may also set content; base paint remains owned.
    frame = life.compositor.compose(time_s=0.0)
    assert frame.digest
    assert life.compositor.app_controls_surface("lumur.paint", floor_id)
    assert life.compositor.app_controls_surface("lumur.ripples", floor_id)
    assert life.compositor.claims_by_app["lumur.ripples"][floor_id].layer == "overlay"


def test_ripples_receives_only_footstep(tmp_path: Path):
    life = _life(tmp_path, "empty_room")
    launcher = Launcher(life)
    launcher.discover(RIPPLES)
    launcher.start("lumur.ripples")
    bus = life.input_bus
    bus.inject(
        FootstepEvent(
            person_id=1,
            foot="left",
            position_room=(0.0, 0.0, 0.0),
            position_floor=(0.1, 0.2),
            timestamp=1.0,
        )
    )
    bus.inject(
        {
            "type": "zone_enter",
            "person_id": 1,
            "zone_id": "left",
            "position_floor": [0.1, 0.2],
            "timestamp": 1.1,
        }
    )
    stream = bus.streams()["lumur.ripples"]
    assert len(stream) == 1
    assert stream[0]["type"] == "footstep"


# --- Story Stage bridge-only (REQ-003-016) --------------------------------


def test_story_stage_absent_without_bridge_discover(tmp_path: Path):
    life = _life(tmp_path, "room_with_box")
    launcher = Launcher(life)
    launcher.discover(APPS)  # core apps only
    ids = {e["app_id"] for e in launcher.list_installed()}
    assert "lumur.synesyn.story_stage" not in ids
    assert "lumur.paint" in ids


def test_story_stage_present_with_bridge_require_flag(tmp_path: Path):
    life = _life(tmp_path, "room_with_box")
    launcher = Launcher(life, require_bridge=False)
    launcher.discover(APPS, *bridge_app_roots(REPO_ROOT))
    installed = {e["app_id"] for e in launcher.list_installed()}
    assert "lumur.synesyn.story_stage" in installed

    startable = {e["app_id"] for e in launcher.list_startable()}
    assert "lumur.synesyn.story_stage" not in startable
    assert "lumur.paint" in startable

    launcher.require_bridge = True
    startable_bridge = {e["app_id"] for e in launcher.list_startable()}
    assert "lumur.synesyn.story_stage" in startable_bridge

    started = launcher.start("lumur.synesyn.story_stage")
    assert started.state == AppState.RUNNING
    assert started.manifest.get("bridge") == "lumur_synesyn"


# --- Generation from apps (REQ-003-014) ----------------------------------


def test_generation_null_provider_leaves_last_good(tmp_path: Path):
    life = _life(tmp_path, "empty_room")
    launcher = Launcher(life)
    launcher.discover(PAINT)
    launcher.start("lumur.paint")
    gen = AppGenerationService(lifecycle=life, provider=NullSurfaceGenerator())
    entry = gen.request("lumur.paint", "floor", raise_on_deny=True)
    assert entry.status == JobStatus.SKIPPED.value
    assert gen.last_good_for("lumur.paint", "floor") is not None


def test_generation_denied_for_unowned_surface(tmp_path: Path):
    life = _life(tmp_path, "room_with_box")
    launcher = Launcher(life)
    launcher.discover(PAINT, RIPPLES)
    launcher.start("lumur.paint")
    launcher.start("lumur.ripples")  # overlay; generation=false

    gen = AppGenerationService(lifecycle=life, provider=NullSurfaceGenerator())
    with pytest.raises(GenerationDenied) as excinfo:
        gen.request("lumur.ripples", "floor")
    assert excinfo.value.reason == "generation_not_declared"

    # Paint does not control a surface it never claimed — invent a foreign key.
    with pytest.raises(GenerationDenied) as excinfo2:
        gen.request("lumur.paint", "ambience", raise_on_deny=True)
    assert excinfo2.value.reason == "unknown_surface_key"


def test_generation_mocked_comfyui_owned_surface_only(tmp_path: Path):
    life = _life(tmp_path, "empty_room")
    launcher = Launcher(life)
    launcher.discover(PAINT)
    launcher.start("lumur.paint")
    floor_id = life.room.floor_plane_id
    assert floor_id is not None

    with MockComfyUIServer() as server:
        provider = ComfyUISurfaceGenerator(
            base_url=server.base_url,
            timeout_sec=10.0,
            use_websocket_progress=False,
            room_package_dir=life.room.package_dir,
        )
        gen = AppGenerationService(lifecycle=life, provider=provider)
        workflow = {
            "1": {
                "class_type": "EmptyImage",
                "inputs": {"width": 32, "height": 24, "batch_size": 1, "color": 0},
            },
            "2": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "app", "images": ["1", 0]},
            },
        }
        entry = gen.request(
            "lumur.paint",
            "floor",
            width=32,
            height=24,
            workflow=workflow,
            routing={
                "mode": "direct",
                "provider": "comfyui",
                "comfy_base_url": server.base_url,
            },
        )
        assert entry.status == JobStatus.SUCCEEDED.value
        assert entry.surface_id == floor_id
        assert life.compositor.app_controls_surface("lumur.paint", floor_id)


def test_generation_mocked_hub_when_bridge_present(tmp_path: Path):
    from lumur_synesyn.config import HubConfig
    from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator

    life = _life(tmp_path, "room_with_box")
    launcher = Launcher(life, require_bridge=True)
    launcher.discover(APPS, STORY)
    launcher.start("lumur.synesyn.story_stage")
    assert life.apps["lumur.synesyn.story_stage"].state == AppState.RUNNING

    with MockSynesynHubServer() as hub:
        floor_preset = hub.seed_workflow_preset(
            tags=[surface_role_tag("floor")],
            name="hub floor app",
            workflow={
                "1": {
                    "class_type": "EmptyImage",
                    "inputs": {
                        "width": 32,
                        "height": 24,
                        "batch_size": 1,
                        "color": 0,
                    },
                },
                "2": {
                    "class_type": "SaveImage",
                    "inputs": {"filename_prefix": "hub", "images": ["1", 0]},
                },
            },
        )
        cfg = HubConfig(hub_base_url=hub.base_url, auth_enabled=False)
        provider = SynesynHubSurfaceGenerator(
            cfg, room_package_dir=life.room.package_dir
        )
        gen = AppGenerationService(lifecycle=life, provider=provider)
        # Ambience is the required floor binding for Story Stage.
        entry = gen.request(
            "lumur.synesyn.story_stage",
            "ambience",
            width=32,
            height=24,
            workflow={"artifact_id": floor_preset},
            routing={
                "mode": "hub",
                "provider": "comfyui",
                "hub_base_url": hub.base_url,
                "comfy_base_url": "http://127.0.0.1:8188",
            },
        )
        assert entry.status in (
            JobStatus.SUCCEEDED.value,
            JobStatus.FAILED.value,
            JobStatus.SKIPPED.value,
        )
        # Must have been allowed through ownership gate (not denied).
        assert entry.denied_reason is None
        assert entry.surface_id is not None
        assert life.compositor.app_controls_surface(
            "lumur.synesyn.story_stage", entry.surface_id
        )


def test_generation_cannot_write_foreign_base(tmp_path: Path):
    """Paint owns floor; a generation:true wall-only app must not touch floor."""
    life = _life(tmp_path, "room_with_box")
    from lumur.app import build_app_manifest

    paint_m = load_app_manifest(PAINT / "lumur.app.json")
    wall_m = build_app_manifest(
        app_id="test.wall_gen",
        name="Wall gen",
        version="0.0.1",
        scene="res://x.tscn",
        surfaces=[
            {
                "key": "panel",
                "role": "wall",
                "min_width_m": 0.3,
                "min_confidence": 0.05,
                "required": True,
            }
        ],
        inputs=[],
        generation=True,
    )
    life.install(paint_m)
    life.install(wall_m)
    life.launch("lumur.paint")
    life.launch("test.wall_gen", make_foreground=False)

    gen = AppGenerationService(lifecycle=life, provider=NullSurfaceGenerator())
    # Wall app asks for paint's floor key — not in its bindings.
    with pytest.raises(GenerationDenied) as excinfo:
        gen.request("test.wall_gen", "floor")
    assert excinfo.value.reason == "unknown_surface_key"

    # Even if we somehow used paint's surface id via a forged key, ownership
    # gate uses fit bindings — wall app may only request ``panel``.
    ok = gen.request("test.wall_gen", "panel", raise_on_deny=True)
    assert ok.denied_reason is None
    assert ok.surface_id in life.compositor.controlled_surface_ids("test.wall_gen")


# --- Deterministic replay + boundary (REQ-003-017) -----------------------


def test_bundled_replay_deterministic(tmp_path: Path):
    def run_once() -> dict:
        life = _life(tmp_path / "r", "empty_room")
        launcher = Launcher(life)
        launcher.discover(RIPPLES, PAINT)
        launcher.start("lumur.paint")
        launcher.start("lumur.ripples")
        events = [
            FootstepEvent(
                person_id=1,
                foot="left",
                position_room=(0.0, 0.0, 0.0),
                position_floor=(0.1, 0.2),
                timestamp=1.0,
            ),
            {
                "type": "presence",
                "person_ids": [1],
                "count": 1,
                "timestamp": 1.1,
            },
        ]
        life.input_bus.publish_batch(events)
        gen = AppGenerationService(lifecycle=life, provider=NullSurfaceGenerator())
        gen.request("lumur.paint", "floor", raise_on_deny=False)
        replayed = life.input_bus.replay(events)
        gen_fingerprints = [
            {
                "app_id": e.app_id,
                "surface_key": e.surface_key,
                "surface_id": e.surface_id,
                "status": e.status,
                "provider": e.provider,
                "denied_reason": e.denied_reason,
                "layer": e.meta.get("layer"),
            }
            for e in gen.history
        ]
        return {
            "states": life.states(),
            "ownership": life.compositor.ownership_table(),
            "streams": {
                k: [e.get("type") for e in v]
                for k, v in life.input_bus.streams().items()
            },
            "replayed": {
                k: [e.get("type") for e in v] for k, v in replayed.items()
            },
            "gen": gen_fingerprints,
            "history": list(life.history),
        }

    a = run_once()
    b = run_once()
    assert a["states"] == b["states"]
    assert a["ownership"] == b["ownership"]
    assert a["streams"] == b["streams"]
    assert a["replayed"] == b["replayed"]
    assert a["gen"] == b["gen"]
    assert a["history"] == b["history"]
    assert a["streams"].get("lumur.ripples") == ["footstep"]


def test_core_apps_and_addons_have_no_synesyn_imports():
    """CI boundary: core packages must not import the optional bridge."""
    import re

    import_re = re.compile(
        r"(?:^|\n)\s*(?:import|from)\s+(lumur_synesyn|synesyn_core|synesyn)\b"
    )
    roots = [
        REPO_ROOT / "addons" / "lumur",
        REPO_ROOT / "companion" / "lumur",
        REPO_ROOT / "apps" / "ripples",
        REPO_ROOT / "apps" / "paint",
    ]
    offenders: list[str] = []
    for base in roots:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".gd", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            if import_re.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))
            # Godot preload / class paths into the bridge addon.
            if "addons/lumur_synesyn" in text or "res://addons/lumur_synesyn" in text:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []


def test_manifest_files_validate():
    for path in (RIPPLES / "lumur.app.json", PAINT / "lumur.app.json", STORY / "lumur.app.json"):
        doc = load_app_manifest(path)
        assert doc["schema"] == "lumur.app"
    assert load_app_manifest(RIPPLES / "lumur.app.json")["shares"] == ["floor"]
    assert load_app_manifest(PAINT / "lumur.app.json")["generation"] is True
    assert load_app_manifest(STORY / "lumur.app.json")["bridge"] == "lumur_synesyn"
