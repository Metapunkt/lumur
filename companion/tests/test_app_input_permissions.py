"""PRD-003 slice 2: per-app input permissions on the room event bus (sim)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from lumur.app import (
    AppInputBus,
    RoomServices,
    build_app_manifest,
    fit_app_to_room,
    load_app_manifest,
)
from lumur.audience import AudienceDetector, AudienceEvent, FloorZone
from lumur.events.udp_json import encode_event
from lumur.paint.export import export_godot_paint_assets
from lumur.sim import SimRig
from lumur.sim.geometry import Plane
from lumur.sim.people import AnimatedPerson, PeopleSim, WalkPath
from lumur.track.footsteps import FootstepDetector, FootstepEvent
from lumur.track.pipeline import TrackingPipeline
from lumur.track.pose import OraclePoseDetector
from lumur.track.subtraction import PredictedFrameSubtractor
from lumur.track.tracker import SimpleByteTracker

from tests.test_paint import _scan_room

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = REPO_ROOT / "apps" / "examples"


def _floor(rig: SimRig) -> Plane:
    return next(p for p in rig.scene.room.planes if p.name == "floor")


def _room_and_fit(tmp_path: Path, manifest: dict):
    room_dir, _rig, _result = _scan_room(tmp_path / "room", scene="empty_room")
    export_godot_paint_assets(room_dir)
    room = RoomServices.load(room_dir)
    fit = fit_app_to_room(manifest, room)
    return room, fit


def _ripples_manifest() -> dict:
    return load_app_manifest(EXAMPLES / "ripples" / "lumur.app.json")


def _zones_manifest() -> dict:
    return build_app_manifest(
        app_id="test.zones",
        name="Zone listener",
        version="0.0.1",
        scene="res://apps/examples/wall_panel/wall_panel_app.tscn",
        surfaces=[
            {
                "key": "floor",
                "role": "floor",
                "min_confidence": 0.1,
                "required": True,
            }
        ],
        inputs=["presence", "zone_enter", "zone_leave", "gathering"],
    )


def _pipeline_with_audience(
    rig: SimRig, zones: list[FloorZone], *, gathering_dwell_s: float = 0.3
) -> TrackingPipeline:
    gt = rig.ground_truth()
    cam = rig.scene.camera
    proj = rig.scene.projector
    subtractor = PredictedFrameSubtractor.from_sim_ground_truth(
        gt,
        ambient=cam.ambient,
        exposure=cam.exposure,
        gamma=proj.gamma,
        latency_frames=rig.latency_frames,
    )
    detector = OraclePoseDetector(
        joint_records_fn=rig.ground_truth_joints, noise_std_px=0.3, seed=2
    )
    audience = AudienceDetector(
        zones=zones,
        gathering_min_count=2,
        gathering_dwell_s=gathering_dwell_s,
        proximity_radius_m=1.2,
    )
    return TrackingPipeline(
        detector=detector,
        tracker=SimpleByteTracker(match_thresh_px=55.0, max_time_lost=20),
        footstep_detector=FootstepDetector.from_sim(
            _floor(rig), cam, refractory_s=0.25, velocity_thresh=0.7
        ),
        subtractor=subtractor,
        audience_detector=audience,
        frame_dt=rig.frame_dt,
    )


# --- Allowlist filtering -------------------------------------------------


def test_declared_footstep_delivered_undeclared_zone_not(tmp_path: Path):
    """REQ-003-006/007: ripples-only app never sees zone/presence/gathering."""
    manifest = _ripples_manifest()
    _room, fit = _room_and_fit(tmp_path, manifest)
    bus = AppInputBus()
    session = bus.register_app(manifest, fit=fit)
    assert session.allows("footstep")
    assert not session.allows("zone_enter")

    assert bus.subscribe(manifest["id"], "footstep") is True
    assert bus.subscribe(manifest["id"], "zone_enter") is False
    assert bus.refused[-1].reason == "undeclared_input"

    bus.inject(
        FootstepEvent(
            person_id=1,
            foot="left",
            position_room=(0.1, 0.0, 0.4),
            position_floor=(0.1, 0.4),
            timestamp=1.0,
        )
    )
    bus.inject(
        AudienceEvent(
            type="zone_enter",
            timestamp=1.1,
            person_id=1,
            zone_id="left",
            person_ids=(1,),
            position_floor=(-0.5, 0.4),
        )
    )
    bus.inject(
        AudienceEvent(type="presence", timestamp=1.2, person_ids=(1,), count=1)
    )
    bus.inject(
        AudienceEvent(
            type="gathering",
            timestamp=1.3,
            person_ids=(1, 2),
            count=2,
            zone_id="left",
        )
    )

    types = session.types_seen()
    assert types == ["footstep"]
    assert "zone_enter" not in types
    assert "presence" not in types
    assert "gathering" not in types


def test_empty_inputs_display_only(tmp_path: Path):
    manifest = build_app_manifest(
        app_id="test.display",
        name="Display only",
        version="0.0.1",
        scene="res://x.tscn",
        surfaces=[{"key": "floor", "role": "floor", "required": True}],
        inputs=[],
    )
    _room, fit = _room_and_fit(tmp_path, manifest)
    bus = AppInputBus()
    session = bus.register_app(manifest, fit=fit)
    bus.inject(
        AudienceEvent(type="presence", timestamp=0.0, person_ids=(1,), count=1)
    )
    bus.inject(
        FootstepEvent(
            person_id=1,
            foot="right",
            position_room=(0.0, 0.0, 0.0),
            position_floor=(0.0, 0.0),
            timestamp=0.1,
        )
    )
    assert session.delivered == []
    assert bus.subscribe(manifest["id"], "footstep") is False


def test_multiple_apps_different_allowlists(tmp_path: Path):
    ripples = _ripples_manifest()
    zones = _zones_manifest()
    room_dir, _rig, _result = _scan_room(tmp_path / "room", scene="empty_room")
    export_godot_paint_assets(room_dir)
    room = RoomServices.load(room_dir)
    fit_r = fit_app_to_room(ripples, room)
    # Second app also wants floor — slice 1 exclusive owned would block; for
    # input-only tests, fit independently (compositor ownership is slice 3).
    fit_z = fit_app_to_room(zones, room)

    bus = AppInputBus()
    bus.register_app(ripples, fit=fit_r)
    bus.register_app(zones, fit=fit_z)

    events = [
        FootstepEvent(
            person_id=1,
            foot="left",
            position_room=(0.2, 0.0, 0.3),
            position_floor=(0.2, 0.3),
            timestamp=0.5,
        ),
        AudienceEvent(
            type="zone_enter",
            timestamp=0.6,
            person_id=1,
            zone_id="A",
            person_ids=(1,),
            position_floor=(0.1, 0.2),
        ),
        AudienceEvent(type="presence", timestamp=0.7, person_ids=(1,), count=1),
    ]
    bus.publish_batch(events)
    streams = bus.streams()
    assert streams[ripples["id"]][0]["type"] == "footstep"
    assert len(streams[ripples["id"]]) == 1
    assert [e["type"] for e in streams[zones["id"]]] == [
        "zone_enter",
        "presence",
    ]


def test_undeclared_subscription_refused_and_logged(caplog: pytest.LogCaptureFixture):
    manifest = _ripples_manifest()
    bus = AppInputBus()
    bus.register_app(manifest)
    with caplog.at_level(logging.WARNING, logger="lumur.app.input_bus"):
        ok = bus.subscribe(manifest["id"], "gathering")
    assert ok is False
    assert any(r.reason == "undeclared_input" for r in bus.refused)
    assert any("refused input subscription" in rec.message for rec in caplog.records)


def test_fitted_surface_coordinates_on_delivery(tmp_path: Path):
    """Positioned events get surface_key / surface_id / position_surface."""
    manifest = _ripples_manifest()
    room, fit = _room_and_fit(tmp_path, manifest)
    floor_id = fit.bindings["floor"].surface_id
    assert floor_id is not None
    assert room.surface_by_id(floor_id) is not None

    bus = AppInputBus()
    bus.register_app(manifest, fit=fit)
    bus.inject(
        FootstepEvent(
            person_id=3,
            foot="left",
            position_room=(0.5, 0.0, 0.5),
            position_floor=(0.5, 0.5),
            timestamp=2.0,
        )
    )
    ev = bus.streams()[manifest["id"]][0]
    assert ev["surface_key"] == "floor"
    assert ev["surface_id"] == floor_id
    assert ev["position_surface"] == [0.5, 0.5]
    assert ev["position_floor"] == [0.5, 0.5]
    # Never invent projector pixels.
    assert "pixel_rect" not in ev
    assert "projector_uv" not in ev


def test_deterministic_ordering_and_seq():
    bus = AppInputBus()
    bus.register_app(_ripples_manifest())
    for i, foot in enumerate(("left", "right", "left")):
        bus.inject(
            FootstepEvent(
                person_id=1,
                foot=foot,
                position_room=(0.0, 0.0, 0.0),
                position_floor=(float(i), 0.0),
                timestamp=float(i),
            )
        )
    stream = bus.streams()["lumur.examples.ripples"]
    assert [e["_bus_seq"] for e in stream] == [1, 2, 3]
    assert [e["position_floor"][0] for e in stream] == [0.0, 1.0, 2.0]


def test_envelope_unwrap_and_handlers():
    seen: list[str] = []
    bus = AppInputBus()
    bus.register_app(_ripples_manifest())
    assert bus.subscribe(
        "lumur.examples.ripples",
        "footstep",
        handler=lambda e: seen.append(e["type"]),
    )
    raw = encode_event(
        {
            "type": "footstep",
            "person_id": 1,
            "foot": "left",
            "position_room": [0, 0, 0],
            "position_floor": [0.1, 0.2],
            "timestamp": 0.0,
            "confidence": 1.0,
        }
    )
    # decode path via inject of envelope dict
    import json

    bus.inject(json.loads(raw.decode("utf-8")))
    assert seen == ["footstep"]


# --- Walking figures in sim ----------------------------------------------


def test_walking_figures_filter_per_app(tmp_path: Path):
    """REQ-003-005/007: sim walkers → full vocabulary; apps see allowlists only."""
    people = PeopleSim(
        people=[
            AnimatedPerson(
                person_id=1,
                path=WalkPath(
                    waypoints=[[0.1, 0.0, 0.5], [0.25, 0.0, 0.55]],
                    closed=True,
                    speed_m_s=0.15,
                ),
                height=1.7,
            ),
            AnimatedPerson(
                person_id=2,
                path=WalkPath(
                    waypoints=[[-0.2, 0.0, 0.4], [0.0, 0.0, 0.5]],
                    closed=True,
                    speed_m_s=0.12,
                ),
                height=1.65,
            ),
        ]
    )
    rig = SimRig.from_scene_path(
        "empty_room", latency_frames=1, frame_dt=1.0 / 20.0, retain_color=True
    )
    rig.set_people(people)
    zones = [FloorZone.rect("centre", -0.5, 0.8, 0.2, 0.9)]
    pipeline = _pipeline_with_audience(rig, zones)

    ripples = _ripples_manifest()
    zones_app = _zones_manifest()
    room_dir, _, _ = _scan_room(tmp_path / "room", scene="empty_room")
    export_godot_paint_assets(room_dir)
    room = RoomServices.load(room_dir)
    bus = AppInputBus()
    bus.register_app(ripples, fit=fit_app_to_room(ripples, room))
    bus.register_app(zones_app, fit=fit_app_to_room(zones_app, room))

    recorded: list[dict] = []
    for _ in range(45):
        buf = rig.render_buffers(pattern=None, include_people=True, retain_color=True)
        result = pipeline.step(buf.image, timestamp=rig.time_s)
        for ev in result.audience_events:
            recorded.append(ev.to_dict())
            bus.publish(ev)
        for ev in result.footsteps:
            recorded.append(ev.to_dict())
            bus.publish(ev)
        rig.advance()

    assert recorded, "expected audience/footstep events from walkers"
    assert any(e["type"] == "presence" for e in recorded)
    assert any(e["type"] == "zone_enter" for e in recorded)

    ripples_types = set(bus.get(ripples["id"]).types_seen())
    zones_types = set(bus.get(zones_app["id"]).types_seen())
    assert ripples_types <= {"footstep"}
    assert "zone_enter" not in ripples_types
    assert "presence" not in ripples_types
    assert "footstep" not in zones_types
    assert zones_types & {"presence", "zone_enter", "zone_leave", "gathering"}


def test_replay_recorded_session_identical_streams(tmp_path: Path):
    """Replaying a recorded session yields identical per-app event streams."""
    ripples = _ripples_manifest()
    zones_app = _zones_manifest()
    room, _ = _room_and_fit(tmp_path, ripples)
    fit_r = fit_app_to_room(ripples, room)
    fit_z = fit_app_to_room(zones_app, room)

    session_events = [
        AudienceEvent(
            type="presence", timestamp=0.0, person_ids=(1,), count=1
        ).to_dict(),
        FootstepEvent(
            person_id=1,
            foot="left",
            position_room=(0.1, 0.0, 0.2),
            position_floor=(0.1, 0.2),
            timestamp=0.1,
        ).to_dict(),
        AudienceEvent(
            type="zone_enter",
            timestamp=0.2,
            person_id=1,
            zone_id="centre",
            person_ids=(1,),
            position_floor=(0.0, 0.3),
        ).to_dict(),
        AudienceEvent(
            type="gathering",
            timestamp=0.3,
            person_ids=(1, 2),
            count=2,
            zone_id="centre",
        ).to_dict(),
        FootstepEvent(
            person_id=2,
            foot="right",
            position_room=(-0.1, 0.0, 0.4),
            position_floor=(-0.1, 0.4),
            timestamp=0.4,
        ).to_dict(),
        AudienceEvent(
            type="zone_leave",
            timestamp=0.5,
            person_id=1,
            zone_id="centre",
            person_ids=(1,),
            position_floor=(0.2, 0.1),
        ).to_dict(),
    ]

    def _run() -> dict[str, list[dict]]:
        bus = AppInputBus()
        bus.register_app(ripples, fit=fit_r)
        bus.register_app(zones_app, fit=fit_z)
        bus.publish_batch(session_events)
        # Drop volatile identity of nested dicts via replay for fingerprint.
        return bus.streams()

    live = _run()
    bus2 = AppInputBus()
    bus2.register_app(ripples, fit=fit_r)
    bus2.register_app(zones_app, fit=fit_z)
    replayed = bus2.replay(session_events)

    assert live[ripples["id"]] == replayed[ripples["id"]]
    assert live[zones_app["id"]] == replayed[zones_app["id"]]
    # Second replay on same bus stays identical.
    again = bus2.replay(session_events)
    assert again == replayed
    assert [e["type"] for e in again[ripples["id"]]] == ["footstep", "footstep"]
    assert [e["type"] for e in again[zones_app["id"]]] == [
        "presence",
        "zone_enter",
        "gathering",
        "zone_leave",
    ]


def test_host_may_subscribe_to_zones_while_app_sees_footsteps_only(tmp_path: Path):
    """ADR 0019: launcher host path is separate from app allowlists."""
    manifest = _ripples_manifest()
    _room, fit = _room_and_fit(tmp_path, manifest)
    bus = AppInputBus()
    bus.register_app(manifest, fit=fit)
    bus.register_host("launcher", allowed=["zone_enter", "zone_leave"])

    bus.inject(
        AudienceEvent(
            type="zone_enter",
            timestamp=1.0,
            person_id=1,
            zone_id="switch",
            person_ids=(1,),
        )
    )
    bus.inject(
        FootstepEvent(
            person_id=1,
            foot="left",
            position_room=(0, 0, 0),
            position_floor=(0, 0),
            timestamp=1.1,
        )
    )
    assert bus.get(manifest["id"]).types_seen() == ["footstep"]
    assert bus.get("launcher").types_seen() == ["zone_enter"]


def test_no_synesyn_import_in_input_bus_module():
    import lumur.app.input_bus as mod

    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "import synesyn" not in src
    assert "from synesyn" not in src
    assert "lumur_synesyn" not in src
    # Core app layer must not depend on the optional bridge package.
    import lumur.app as app_pkg

    assert not any(name.startswith("lumur_synesyn") for name in dir(app_pkg))
