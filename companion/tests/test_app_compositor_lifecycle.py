"""PRD-003 slice 3: compositor ownership, lifecycle, launcher, zone switch (sim)."""

from __future__ import annotations

from pathlib import Path

import pytest

from lumur.app import (
    AppLifecycle,
    AppState,
    Launcher,
    LifecycleError,
    RoomServices,
    ZoneAppSwitcher,
    ZoneSwitchConfig,
    build_app_manifest,
)
from lumur.audience import AudienceEvent, DwellGate
from lumur.paint.export import export_godot_paint_assets
from lumur.paint.render import PaintAssignment
from lumur.sim import SimRig
from lumur.sim.geometry import Plane
from lumur.track.footsteps import FootstepEvent

from tests.test_paint import _scan_room

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "apps" / "examples"


def _room(tmp_path: Path, scene: str = "room_with_box") -> RoomServices:
    room_dir, _rig, _result = _scan_room(tmp_path / scene, scene=scene)
    export_godot_paint_assets(room_dir)
    return RoomServices.load(room_dir)


def _floor_app(app_id: str = "test.floor_a", **surface_extra) -> dict:
    req = {
        "key": "floor",
        "role": "floor",
        "min_confidence": 0.05,
        "required": True,
        **surface_extra,
    }
    return build_app_manifest(
        app_id=app_id,
        name=f"Floor {app_id}",
        version="0.0.1",
        scene="res://apps/examples/ripples/ripple_app.tscn",
        surfaces=[req],
        inputs=["footstep"],
    )


def _wall_app(app_id: str = "test.wall_a", **surface_extra) -> dict:
    req = {
        "key": "panel",
        "role": "wall",
        "min_width_m": 0.5,
        "min_confidence": 0.05,
        "required": True,
        **surface_extra,
    }
    return build_app_manifest(
        app_id=app_id,
        name=f"Wall {app_id}",
        version="0.0.1",
        scene="res://apps/examples/wall_panel/wall_panel_app.tscn",
        surfaces=[req],
        inputs=[],
    )


def _floor(rig: SimRig) -> Plane:
    return next(p for p in rig.scene.room.planes if p.name == "floor")


# --- Compositor ownership / conflict / fallback --------------------------


def test_two_apps_contend_for_one_wall(tmp_path: Path):
    """REQ-003-008: second exclusive claim on the same wall does not launch."""
    room = _room(tmp_path, "room_with_box")
    walls = [
        s
        for s in room.surfaces
        if s.kind == "wall" or any(r.startswith("wall_") for r in s.roles)
    ]
    if len(walls) < 1:
        pytest.skip("need a wall surface")
    # Force both apps onto the single largest wall via absurd width filter
    # that only the top wall passes, or via named role when available.
    top = sorted(walls, key=lambda s: (-s.width_m, s.surface_id))[0]
    role = next((r for r in top.roles if r.startswith("wall_")), "wall")
    a = _wall_app("test.wall_a", role=role, min_width_m=0.1)
    b = _wall_app("test.wall_b", role=role, min_width_m=0.1)

    life = AppLifecycle.create(room)
    life.install(a)
    life.install(b)
    life.launch("test.wall_a")
    assert life.apps["test.wall_a"].state == AppState.RUNNING
    owned = life.compositor.exclusive_owned_ids()
    assert top.surface_id in owned

    with pytest.raises(LifecycleError) as excinfo:
        life.launch("test.wall_b")
    assert excinfo.value.reason in ("unmet_surface", "exclusive_conflict")
    assert life.apps["test.wall_b"].state == AppState.INSTALLED
    assert life.compositor.ownership[top.surface_id].base_app_id == "test.wall_a"


def test_fallback_when_surface_missing(tmp_path: Path):
    """Optional unmet → null binding; compositor claims nothing for that key."""
    room = _room(tmp_path, "empty_room")
    manifest = _wall_app(required=False, min_width_m=50.0)
    life = AppLifecycle.create(room)
    life.install(manifest)
    # Launch succeeds degraded (optional null); no exclusive ownership invented.
    # fit with required=False returns ok with null — launch uses raise_on_unmet True
    # only for required. Optional unmet still ok from fit.
    record = life.launch(manifest["id"])
    assert record.state == AppState.RUNNING
    assert record.fit is not None
    assert record.fit.bindings["panel"].surface_id is None
    assert life.compositor.exclusive_owned_ids() == set()


def test_overlay_share_does_not_steal_base(tmp_path: Path):
    room = _room(tmp_path, "empty_room")
    base = _floor_app("test.paint")
    overlay = build_app_manifest(
        app_id="test.ripples",
        name="Ripples overlay",
        version="0.0.1",
        scene="res://apps/examples/ripples/ripple_app.tscn",
        surfaces=[
            {"key": "floor", "role": "floor", "min_confidence": 0.05, "required": True}
        ],
        inputs=["footstep"],
        shares=["floor"],
    )
    life = AppLifecycle.create(room)
    life.install(base)
    life.install(overlay)
    life.launch("test.paint")
    floor_id = room.floor_plane_id
    assert floor_id is not None

    # share_keys let fit bind an owned floor; claim becomes overlay (ADR 0018).
    life.launch("test.ripples", make_foreground=False)
    entry = life.compositor.ownership[floor_id]
    assert entry.base_app_id == "test.paint"
    assert ("test.ripples", "floor") in entry.overlays
    assert life.apps["test.ripples"].state == AppState.RUNNING


def test_masking_output_digest_stable(tmp_path: Path):
    """REQ-003-009: confidence masking digest is deterministic across composes."""
    room = _room(tmp_path, "noisy_room")
    life = AppLifecycle.create(room)
    life.install(_floor_app())
    life.launch("test.floor_a")
    floor_id = room.floor_plane_id
    assert floor_id is not None
    life.compositor.set_content(
        "test.floor_a",
        {floor_id: PaintAssignment(surface_id=floor_id, color=(1.0, 0.0, 0.0))},
    )
    frame_a = life.compositor.compose(time_s=0.0)
    frame_b = life.compositor.compose(time_s=0.0)
    assert frame_a.digest == frame_b.digest
    assert frame_a.digest
    assert frame_a.total_pixels > 0
    # Low-confidence / invalid pixels stay masked (not painted).
    assert frame_a.masked_pixels >= 0
    assert frame_a.painted_pixels + frame_a.masked_pixels <= frame_a.total_pixels
    # Raising threshold cannot invent coverage — painted count must not grow.
    life.compositor.confidence_threshold = 0.99
    frame_hi = life.compositor.compose(time_s=0.0)
    assert frame_hi.painted_pixels <= frame_a.painted_pixels


def test_switch_and_pause_handoff(tmp_path: Path):
    """REQ-003-010/011: cut handoff on pause/switch; ownership moves."""
    room = _room(tmp_path, "room_with_box")
    life = AppLifecycle.create(room)
    life.install(_floor_app("app.a"))
    life.install(_wall_app("app.b", min_width_m=0.5))
    life.launch("app.a")
    floor_id = room.floor_plane_id
    assert life.compositor.ownership[floor_id].base_app_id == "app.a"

    life.pause("app.a")
    assert life.apps["app.a"].state == AppState.PAUSED
    assert floor_id not in life.compositor.ownership
    assert any(t.reason == "pause" and t.kind == "cut" for t in life.compositor.transitions)

    life.launch("app.b")
    assert life.foreground_app_id == "app.b"
    life.switch("app.a")
    assert life.apps["app.a"].state == AppState.RUNNING
    assert life.apps["app.b"].state == AppState.PAUSED
    assert life.foreground_app_id == "app.a"
    assert life.compositor.ownership[floor_id].base_app_id == "app.a"
    assert any(t.reason in ("switch", "resume", "launch") for t in life.compositor.transitions)


def test_paused_apps_receive_no_events(tmp_path: Path):
    """REQ-003-011: input bus subscriptions follow lifecycle — paused = silence."""
    room = _room(tmp_path, "empty_room")
    life = AppLifecycle.create(room)
    life.install(_floor_app("app.ripples"))
    life.launch("app.ripples")
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
    assert len(bus.streams()["app.ripples"]) == 1

    life.pause("app.ripples")
    session = bus.get("app.ripples")
    assert session is not None and session.paused
    before = len(session.delivered)
    bus.inject(
        FootstepEvent(
            person_id=1,
            foot="right",
            position_room=(0.0, 0.0, 0.0),
            position_floor=(0.2, 0.3),
            timestamp=2.0,
        )
    )
    assert len(session.delivered) == before

    life.resume("app.ripples")
    bus.inject(
        FootstepEvent(
            person_id=1,
            foot="left",
            position_room=(0.0, 0.0, 0.0),
            position_floor=(0.3, 0.4),
            timestamp=3.0,
        )
    )
    assert len(session.delivered) == before + 1


def test_launcher_flow_lists_and_starts(tmp_path: Path):
    """REQ-003-012: discover examples, list, start one headlessly."""
    room = _room(tmp_path, "room_with_box")
    life = AppLifecycle.create(room)
    launcher = Launcher(life)
    found = launcher.discover(EXAMPLES)
    assert found
    ids = {r.app_id for r in found}
    assert "lumur.examples.ripples" in ids
    assert "lumur.examples.wall_panel" in ids

    listed = launcher.list_startable()
    assert all(not (e.get("bridge")) for e in listed)

    started = launcher.start("lumur.examples.ripples")
    assert started.state == AppState.RUNNING
    assert life.foreground_app_id == "lumur.examples.ripples"

    # Starting another switches/pauses the first.
    launcher.start("lumur.examples.wall_panel")
    assert life.apps["lumur.examples.ripples"].state == AppState.PAUSED
    assert life.apps["lumur.examples.wall_panel"].state == AppState.RUNNING


def test_zone_switch_ignores_passers_by(tmp_path: Path):
    """REQ-003-013: dwell required; short visits do not switch apps."""
    room = _room(tmp_path, "empty_room")
    life = AppLifecycle.create(room)
    life.install(_floor_app("app.left"))
    life.install(
        build_app_manifest(
            app_id="app.right",
            name="Right",
            version="0.0.1",
            scene="res://x.tscn",
            surfaces=[
                {
                    "key": "floor",
                    "role": "floor",
                    "min_confidence": 0.05,
                    "required": True,
                }
            ],
            inputs=[],
        )
    )
    life.launch("app.left")
    cfg = ZoneSwitchConfig(
        zone_to_app={"left": "app.left", "right": "app.right"},
        min_dwell_s=1.5,
        debounce_s=0.5,
        enabled=True,
    )
    switcher = ZoneAppSwitcher(lifecycle=life, config=cfg)
    switcher.attach_bus()

    # Passer-by: enter and leave before dwell.
    switcher.process_event(
        AudienceEvent(
            type="zone_enter",
            timestamp=1.0,
            person_id=1,
            zone_id="right",
            person_ids=(1,),
            position_floor=(0.5, 0.5),
        )
    )
    switcher.process_event(
        AudienceEvent(
            type="zone_leave",
            timestamp=1.4,
            person_id=1,
            zone_id="right",
            person_ids=(),
            position_floor=(0.5, 0.5),
        )
    )
    assert life.foreground_app_id == "app.left"
    assert any(r.get("reason") == "dwell_too_short" for r in switcher.rejected)
    assert switcher.switches == []

    # Dwelling visitor: enter, tick past min_dwell.
    switcher.process_event(
        AudienceEvent(
            type="zone_enter",
            timestamp=2.0,
            person_id=2,
            zone_id="right",
            person_ids=(2,),
            position_floor=(0.5, 0.5),
        )
    )
    applied = switcher.tick(3.6)
    assert applied
    assert life.foreground_app_id == "app.right"
    assert life.apps["app.left"].state == AppState.PAUSED


def test_zone_switch_absent_config_does_nothing(tmp_path: Path):
    room = _room(tmp_path, "empty_room")
    life = AppLifecycle.create(room)
    life.install(_floor_app("app.only"))
    life.launch("app.only")
    switcher = ZoneAppSwitcher(
        lifecycle=life, config=ZoneSwitchConfig.from_dict(None)
    )
    assert not switcher.enabled
    switcher.process_event(
        AudienceEvent(
            type="zone_enter",
            timestamp=1.0,
            person_id=1,
            zone_id="left",
            person_ids=(1,),
        )
    )
    assert switcher.switches == []
    assert life.foreground_app_id == "app.only"


def test_deterministic_replay_lifecycle_and_bus(tmp_path: Path):
    """Replay the same install/launch/event sequence → identical streams + ownership."""
    room = _room(tmp_path, "room_with_box")

    def run_once() -> dict:
        life = AppLifecycle.create(room)
        life.install(_floor_app("app.a"))
        life.install(_wall_app("app.b", min_width_m=0.5))
        life.launch("app.a")
        events = [
            FootstepEvent(
                person_id=1,
                foot="left",
                position_room=(0.0, 0.0, 0.0),
                position_floor=(0.1, 0.2),
                timestamp=1.0,
            ),
            AudienceEvent(
                type="presence", timestamp=1.1, person_ids=(1,), count=1
            ),
        ]
        life.input_bus.publish_batch(events)
        life.pause("app.a")
        life.launch("app.b")
        life.switch("app.a")
        life.input_bus.inject(
            FootstepEvent(
                person_id=1,
                foot="right",
                position_room=(0.0, 0.0, 0.0),
                position_floor=(0.2, 0.3),
                timestamp=2.0,
            )
        )
        # Replay bus events for identical delivery to the running app.
        replayed = life.input_bus.replay(
            [
                FootstepEvent(
                    person_id=1,
                    foot="left",
                    position_room=(0.0, 0.0, 0.0),
                    position_floor=(0.1, 0.2),
                    timestamp=1.0,
                ),
                AudienceEvent(
                    type="presence", timestamp=1.1, person_ids=(1,), count=1
                ),
                FootstepEvent(
                    person_id=1,
                    foot="right",
                    position_room=(0.0, 0.0, 0.0),
                    position_floor=(0.2, 0.3),
                    timestamp=2.0,
                ),
            ]
        )
        return {
            "states": life.states(),
            "foreground": life.foreground_app_id,
            "ownership": life.compositor.ownership_table(),
            "streams": {k: [dict(e) for e in v] for k, v in life.input_bus.streams().items()},
            "replayed_types": {
                k: [e.get("type") for e in v] for k, v in replayed.items()
            },
            "history": list(life.history),
        }

    a = run_once()
    b = run_once()
    assert a["states"] == b["states"]
    assert a["foreground"] == b["foreground"]
    assert a["ownership"] == b["ownership"]
    assert a["replayed_types"] == b["replayed_types"]
    assert a["history"] == b["history"]
    # Paused wall app must not appear in footstep deliveries after replay.
    assert a["streams"]["app.a"]
    assert all(e["type"] == "footstep" for e in a["streams"]["app.a"])
    assert "app.b" not in a["streams"] or a["streams"].get("app.b") == []


def test_dwell_gate_shared_helper_rejects_short_visit():
    gate = DwellGate(min_dwell_s=1.5, debounce_s=0.5)
    gate.on_zone_enter(person_id=1, zone_id="z", timestamp=0.0)
    gate.on_zone_leave(person_id=1, zone_id="z", timestamp=0.5)
    assert gate.tick(1.0) == []
    assert gate.rejected[0]["reason"] == "dwell_too_short"


def test_no_synesyn_import_in_slice3_modules():
    """Core compositor/lifecycle must not import the bridge package."""
    import lumur.app as app_pkg
    import lumur.app.compositor as c
    import lumur.app.lifecycle as life
    import lumur.app.launcher as launcher
    import lumur.app.zone_switch as zs
    import lumur.audience.dwell as dwell

    for mod in (app_pkg, c, life, launcher, zs, dwell):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "import lumur_synesyn" not in src
        assert "from lumur_synesyn" not in src
        assert "import synesyn" not in src
