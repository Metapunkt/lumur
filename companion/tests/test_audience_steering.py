"""PRD-002 slice 4: opt-in audience steering + Story Log replay (sim)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from lumur.audience import AudienceDetector, AudienceEvent, FloorZone
from lumur.events.udp_json import EventReceiver, EventSender, encode_event
from lumur.paint.export import export_godot_paint_assets
from lumur.sim import SimRig
from lumur.sim.geometry import Plane
from lumur.sim.people import AnimatedPerson, PeopleSim, WalkPath
from lumur.track.footsteps import FootstepDetector
from lumur.track.pipeline import TrackingPipeline
from lumur.track.pose import OraclePoseDetector
from lumur.track.subtraction import PredictedFrameSubtractor
from lumur.track.tracker import SimpleByteTracker
from lumur_synesyn.audience_config import (
    audience_config_from_scenario,
    is_audience_steering_enabled,
)
from lumur_synesyn.audience_steering import AudienceSteeringBridge
from lumur_synesyn.mock_story_stage import MockStoryStageReceiver
from lumur_synesyn.replay import replay_session
from lumur_synesyn.room_artifact import register_room_package
from lumur_synesyn.session_record import (
    SessionRecorder,
    register_session_with_hub,
    save_session,
)

from tests.mock_synesyn_hub import MockSynesynHubServer
from tests.test_paint import _scan_room


# ---------------------------------------------------------------------------
# Config / opt-in
# ---------------------------------------------------------------------------


def test_audience_opt_in_requires_section():
    assert not is_audience_steering_enabled({})
    assert not is_audience_steering_enabled({"vis_story": {"enabled": "true"}})
    assert not is_audience_steering_enabled(
        {"lumur_audience": {"enabled": "false"}}
    )
    cfg = audience_config_from_scenario(
        {
            "lumur_audience": {
                "enabled": "true",
                "min_dwell_s": 2.0,
                "zones": [
                    {
                        "zone_id": "left",
                        "kind": "rect",
                        "u_min": -1.0,
                        "u_max": 0.0,
                        "v_min": 0.0,
                        "v_max": 1.0,
                    }
                ],
                "zone_actions": {"left": "option:0"},
            }
        }
    )
    assert cfg.enabled
    assert cfg.min_dwell_s == 2.0
    assert len(cfg.zones) == 1
    assert cfg.action_for_zone("left").option_index == 0


def test_opt_out_never_steers_story():
    recv = MockStoryStageReceiver()
    recv.set_choices(["Stay", "Leave"])
    bridge = AudienceSteeringBridge.from_scenario(
        {"vis_story": {"enabled": "true"}}, receiver=recv
    )
    assert not bridge.enabled
    events = [
        AudienceEvent(
            type="zone_enter",
            timestamp=0.0,
            person_id=1,
            person_ids=(1,),
            zone_id="left",
        ),
        AudienceEvent(
            type="gathering",
            timestamp=2.0,
            person_ids=(1, 2),
            count=2,
            zone_id="left",
        ),
    ]
    applied = bridge.process_batch(events, timestamp=3.0)
    assert applied == []
    assert recv.steered_actions == []
    assert recv.beat_index == 0
    assert len(recv.ambience_events) == 2  # still ambience (REQ-002-012)


def test_opt_in_zone_dwell_chooses_option():
    scenario = {
        "lumur_audience": {
            "enabled": True,
            "min_dwell_s": 1.0,
            "debounce_s": 0.1,
            "zone_actions": {"left": {"action": "choose_option", "option_index": 1}},
        }
    }
    recv = MockStoryStageReceiver()
    recv.set_choices(["Stay", "Leave"])
    bridge = AudienceSteeringBridge.from_scenario(scenario, receiver=recv)
    bridge.process_event(
        AudienceEvent(
            type="zone_enter",
            timestamp=0.0,
            person_id=1,
            person_ids=(1,),
            zone_id="left",
        )
    )
    # Too early — no fire.
    assert bridge.tick(0.5) == []
    applied = bridge.tick(1.2)
    assert len(applied) == 1
    assert applied[0].kind == "choose_option"
    assert applied[0].option_index == 1
    assert recv.steered_actions
    assert recv.story_log[-1]["message"] == "Leave"
    assert recv.beat_index == 1


def test_debounce_rejects_passers_by():
    scenario = {
        "lumur_audience": {
            "enabled": True,
            "min_dwell_s": 1.5,
            "debounce_s": 0.5,
            "zone_actions": {"gate": "option:0"},
        }
    }
    recv = MockStoryStageReceiver()
    recv.set_choices(["A", "B"])
    bridge = AudienceSteeringBridge.from_scenario(scenario, receiver=recv)
    # Passer-by: enter and leave before min dwell.
    bridge.process_event(
        AudienceEvent(
            type="zone_enter",
            timestamp=0.0,
            person_id=1,
            zone_id="gate",
            person_ids=(1,),
        )
    )
    bridge.process_event(
        AudienceEvent(
            type="zone_leave",
            timestamp=0.4,
            person_id=1,
            zone_id="gate",
            person_ids=(1,),
        )
    )
    assert bridge.tick(2.0) == []
    assert recv.steered_actions == []
    assert any(r["reason"] == "dwell_too_short" for r in bridge.rejected)


# ---------------------------------------------------------------------------
# Core audience detector + walking figures
# ---------------------------------------------------------------------------


def _floor(rig: SimRig) -> Plane:
    return next(p for p in rig.scene.room.planes if p.name == "floor")


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


def test_walking_figures_emit_presence_and_zone_events():
    """Sim walkers produce presence / zone events on floor coordinates."""
    # Stationary-ish person near a zone centre (slow closed path inside zone).
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
            )
        ]
    )
    rig = SimRig.from_scene_path(
        "empty_room", latency_frames=1, frame_dt=1.0 / 20.0, retain_color=True
    )
    rig.set_people(people)
    zones = [FloorZone.rect("centre", -0.5, 0.8, 0.2, 0.9)]
    pipeline = _pipeline_with_audience(rig, zones)
    saw_presence = False
    saw_enter = False
    for _ in range(40):
        buf = rig.render_buffers(pattern=None, include_people=True, retain_color=True)
        result = pipeline.step(buf.image, timestamp=rig.time_s)
        for ev in result.audience_events:
            if ev.type == "presence" and ev.count >= 1:
                saw_presence = True
            if ev.type == "zone_enter" and ev.zone_id == "centre":
                saw_enter = True
        rig.advance()
    assert saw_presence
    assert saw_enter
    assert pipeline.audience_detector.state.count >= 1


def test_sim_opt_out_walkers_never_steer():
    people = PeopleSim(
        people=[
            AnimatedPerson(
                person_id=1,
                path=WalkPath(
                    waypoints=[[-0.2, 0.0, 0.4], [0.3, 0.0, 0.6]],
                    closed=True,
                    speed_m_s=0.2,
                ),
            )
        ]
    )
    rig = SimRig.from_scene_path(
        "empty_room", latency_frames=1, frame_dt=1.0 / 20.0, retain_color=True
    )
    rig.set_people(people)
    zones = [FloorZone.rect("A", -1.0, 1.0, 0.0, 1.2)]
    pipeline = _pipeline_with_audience(rig, zones)
    bridge = AudienceSteeringBridge.from_scenario(
        {"lumur_layout": {"ambience": "floor"}},  # no lumur_audience
        receiver=MockStoryStageReceiver(),
    )
    for _ in range(30):
        buf = rig.render_buffers(pattern=None, include_people=True, retain_color=True)
        result = pipeline.step(buf.image, timestamp=rig.time_s)
        bridge.process_batch(result.audience_events, timestamp=rig.time_s)
        rig.advance()
    assert bridge.receiver.steered_actions == []
    assert bridge.receiver.ambience_events  # presence still forwarded


def test_sim_opt_in_zone_choice_with_dwelling_walker():
    """Slow walker dwelling in zone_left picks option 0 when opted in."""
    people = PeopleSim(
        people=[
            AnimatedPerson(
                person_id=1,
                path=WalkPath(
                    waypoints=[[-0.6, 0.0, 0.5], [-0.45, 0.0, 0.55]],
                    closed=True,
                    speed_m_s=0.05,
                ),
            )
        ]
    )
    rig = SimRig.from_scene_path(
        "empty_room", latency_frames=1, frame_dt=1.0 / 15.0, retain_color=True
    )
    rig.set_people(people)
    zones = [FloorZone.rect("left", -1.0, -0.2, 0.2, 0.9)]
    pipeline = _pipeline_with_audience(rig, zones)
    scenario = {
        "lumur_audience": {
            "enabled": True,
            "min_dwell_s": 0.8,
            "debounce_s": 0.2,
            "zones": [z.to_dict() for z in zones],
            "zone_actions": {"left": {"action": "choose_option", "option_index": 0}},
        }
    }
    recv = MockStoryStageReceiver()
    recv.set_choices(["Restore", "Disrupt"])
    bridge = AudienceSteeringBridge.from_scenario(scenario, receiver=recv)
    for _ in range(50):
        buf = rig.render_buffers(pattern=None, include_people=True, retain_color=True)
        result = pipeline.step(buf.image, timestamp=rig.time_s)
        bridge.process_batch(
            result.audience_events,
            timestamp=rig.time_s,
            state=pipeline.audience_detector.state,
        )
        rig.advance()
        if any(a.kind == "choose_option" for a in recv.steered_actions):
            break
    assert any(a.kind == "choose_option" for a in recv.steered_actions)
    assert recv.story_log[-1]["message"] == "Restore"


def test_sim_fast_passerby_rejected_by_dwell():
    people = PeopleSim(
        people=[
            AnimatedPerson(
                person_id=1,
                path=WalkPath(
                    waypoints=[[-1.5, 0.0, 0.5], [1.5, 0.0, 0.5]],
                    closed=False,
                    speed_m_s=2.5,
                ),
            )
        ]
    )
    # Closed=False with two waypoints: walks once across.
    people.people[0].path.closed = False
    rig = SimRig.from_scene_path(
        "empty_room", latency_frames=1, frame_dt=1.0 / 20.0, retain_color=True
    )
    rig.set_people(people)
    zones = [FloorZone.rect("gate", -0.15, 0.15, 0.3, 0.7)]
    pipeline = _pipeline_with_audience(rig, zones)
    scenario = {
        "lumur_audience": {
            "enabled": True,
            "min_dwell_s": 1.2,
            "debounce_s": 0.3,
            "zone_actions": {"gate": "option:0"},
        }
    }
    recv = MockStoryStageReceiver()
    recv.set_choices(["A"])
    bridge = AudienceSteeringBridge.from_scenario(scenario, receiver=recv)
    for _ in range(60):
        buf = rig.render_buffers(pattern=None, include_people=True, retain_color=True)
        result = pipeline.step(buf.image, timestamp=rig.time_s)
        bridge.process_batch(result.audience_events, timestamp=rig.time_s)
        rig.advance()
    assert not any(a.kind == "choose_option" for a in recv.steered_actions)
    assert any(r.get("reason") == "dwell_too_short" for r in bridge.rejected)


# ---------------------------------------------------------------------------
# UDP mock Godot receiver + Story Stage mock
# ---------------------------------------------------------------------------


def test_udp_audience_events_into_python_godot_mock():
    receiver = EventReceiver(host="127.0.0.1", port=18770)
    receiver.bind()
    sender = EventSender(host="127.0.0.1", port=18770)
    try:
        ev = AudienceEvent(
            type="presence",
            timestamp=1.5,
            person_ids=(1, 2),
            count=2,
        )
        sender.send_audience(ev)
        sender.send_audience(
            AudienceEvent(
                type="zone_enter",
                timestamp=1.6,
                person_id=1,
                zone_id="left",
                person_ids=(1,),
                position_floor=(-0.5, 0.4),
            )
        )
        time.sleep(0.05)
        msgs = receiver.poll()
        types = [m["event"]["type"] for m in msgs]
        assert "presence" in types
        assert "zone_enter" in types
        assert msgs[0]["schema"] == "lumur.event"
    finally:
        sender.close()
        receiver.close()


def test_mock_story_stage_receiver_fingerprint_stable():
    recv = MockStoryStageReceiver(steering_enabled=True)
    recv.set_choices(["One", "Two"])
    recv.choose_option(option_index=0, timestamp=1.0)
    recv.set_parameter("intensity", 0.5, timestamp=1.1)
    recv.record_paint_digest("abc123")
    fp1 = recv.state_fingerprint()
    recv2 = MockStoryStageReceiver(steering_enabled=True)
    recv2.set_choices(["One", "Two"])
    recv2.choose_option(option_index=0, timestamp=1.0)
    recv2.set_parameter("intensity", 0.5, timestamp=1.1)
    recv2.record_paint_digest("abc123")
    assert recv2.state_fingerprint() == fp1


# ---------------------------------------------------------------------------
# Session recording + deterministic replay
# ---------------------------------------------------------------------------


def test_replay_determinism_with_room_package(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)
    scenario = {
        "lumur_audience": {
            "enabled": True,
            "min_dwell_s": 0.5,
            "debounce_s": 0.1,
            "zone_actions": {"left": {"action": "choose_option", "option_index": 0}},
        },
        "lumur_layout": {"ambience": "floor", "backdrop": "wall_1"},
    }
    events = [
        AudienceEvent(
            type="presence", timestamp=0.0, person_ids=(1,), count=1
        ).to_dict(),
        AudienceEvent(
            type="zone_enter",
            timestamp=0.1,
            person_id=1,
            zone_id="left",
            person_ids=(1,),
        ).to_dict(),
    ]
    # Simulate dwell by ticking via process_batch at later time with a no-op event.
    # record_and_fingerprint uses process_batch once — inject a late presence so tick fires.
    events.append(
        AudienceEvent(
            type="presence", timestamp=1.0, person_ids=(1,), count=1
        ).to_dict()
    )
    # Manually ensure dwell watch fires: use bridge then record actions.
    recv = MockStoryStageReceiver()
    recv.set_choices(["Yes", "No"])
    bridge = AudienceSteeringBridge.from_scenario(scenario, receiver=recv)
    bridge.process_event(AudienceEvent.from_dict(events[1]))
    bridge.tick(1.0)
    story_log = [
        {
            "sender": "Narrator",
            "message": "The room waits.",
            "timestamp_us": 0,
        },
        {
            "sender": "The Seeker",
            "message": "I step left.",
            "timestamp_us": 500000,
        },
    ]
    recorder = SessionRecorder(
        room_package_ref=str(room_dir), scenario=scenario
    )
    recorder.record_audience_batch(
        [AudienceEvent.from_dict(e) for e in events]
    )
    recorder.record_actions(recv.actions)
    combined_log = list(story_log) + [
        e for e in recv.story_log if e.get("sender") == "_audience"
    ]
    recorder.set_story_log(combined_log)
    recording = recorder.finalize(story_log=combined_log)
    recording.stage_actions = [a.to_dict() for a in recv.actions]

    r1 = replay_session(
        recording,
        room_package_dir=room_dir,
        texture_size=(32, 32),
        choices=["Yes", "No"],
    )
    r2 = replay_session(
        recording,
        room_package_dir=room_dir,
        texture_size=(32, 32),
        choices=["Yes", "No"],
    )
    assert r1.state_fingerprint == r2.state_fingerprint
    assert r1.paint_digests == r2.paint_digests
    assert r1.paint_digests  # paint actually ran
    # Story Stage stub + audience choice both present.
    assert any(e.get("sender") == "Narrator" for e in r1.story_log)
    assert any(e.get("sender") == "_audience" for e in r1.story_log)

    path = save_session(recording, tmp_path / "session.json")
    r3 = replay_session(path, room_package_dir=room_dir, texture_size=(32, 32), choices=["Yes", "No"])
    assert r3.state_fingerprint == r1.state_fingerprint


def test_metaprompt_audience_state_summary():
    scenario = {"lumur_audience": {"enabled": True}}
    bridge = AudienceSteeringBridge.from_scenario(scenario)
    from lumur.audience import AudienceState

    state = AudienceState(
        timestamp=1.0,
        person_ids=(1, 2),
        count=2,
        positions={1: (0.1, 0.2), 2: (-0.3, 0.4)},
        occupants={"left": (1,)},
        gatherings={},
    )
    summary = bridge.audience_state_for_metaprompt(state)
    assert summary["enabled"] is True
    assert "2 present" in summary["text"]
    assert summary["state"]["count"] == 2

    off = AudienceSteeringBridge.from_scenario({})
    assert off.audience_state_for_metaprompt(state)["enabled"] is False
    assert off.audience_state_for_metaprompt(state)["text"] == ""


def test_session_and_room_hub_registration(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)
    with MockSynesynHubServer() as hub:
        from lumur_synesyn.config import HubConfig
        from lumur_synesyn.hub_client import SynesynHubClient

        client = SynesynHubClient(HubConfig(hub_base_url=hub.base_url, auth_enabled=False))
        room = register_room_package(client, room_dir)
        assert room["ok"]
        recorder = SessionRecorder(
            room_package_ref=str(room_dir),
            scenario={"lumur_audience": {"enabled": True}},
            room_artifact_id=room["artifact_id"],
        )
        recorder.record_audience(
            AudienceEvent(type="presence", timestamp=0.0, person_ids=(1,), count=1)
        )
        recording = recorder.finalize()
        result = register_session_with_hub(
            client, recording, register_room=False, room_package_dir=room_dir
        )
        assert result["ok"]
        assert result["artifact_type"] == "json.lumur_session"
        assert result["room_artifact_id"] == room["artifact_id"]


def test_encode_audience_event_envelope():
    raw = encode_event(
        AudienceEvent(
            type="gathering",
            timestamp=3.0,
            zone_id="centre",
            person_ids=(1, 2),
            count=2,
        ).to_dict()
    )
    doc = json.loads(raw)
    assert doc["schema"] == "lumur.event"
    assert doc["event"]["type"] == "gathering"


def test_core_has_no_synesyn_imports_for_audience():
    root = Path(__file__).resolve().parents[2]
    hits = []
    for path in (root / "companion" / "lumur" / "audience").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import lumur_synesyn" in text or "from lumur_synesyn" in text:
            hits.append(str(path))
        if "import synesyn_core" in text or "from synesyn_core" in text:
            hits.append(str(path))
    assert hits == []
