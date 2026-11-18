"""Deterministic Story Log + audience session replay in the Lumur sim.

Replaying a recorded session re-drives the Story Stage stub and paint output
identically (REQ-002-015). Pattern mirrors Synesyn's ``StoryLogPlaybackHost``
without importing Synesyn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from lumur_synesyn.audience_config import audience_config_from_scenario
from lumur_synesyn.audience_steering import AudienceSteeringBridge
from lumur_synesyn.mock_story_stage import MockStoryStageReceiver, StageAction
from lumur_synesyn.session_record import SessionRecording, load_session
from lumur_synesyn.story_stage_layers import StubStoryStageSource
from lumur_synesyn.story_stage_layout import layout_from_scenario
from lumur_synesyn.story_stage_project import project_from_source


@dataclass
class ReplayResult:
    """Outcome of a deterministic replay pass."""

    receiver: MockStoryStageReceiver
    paint_digests: list[str] = field(default_factory=list)
    state_fingerprint: str = ""
    projections: list[Any] = field(default_factory=list)
    story_log: list[dict[str, Any]] = field(default_factory=list)
    steered_actions: list[dict[str, Any]] = field(default_factory=list)

    def matches(self, other: ReplayResult | SessionRecording) -> bool:
        if isinstance(other, SessionRecording):
            return (
                self.state_fingerprint == (other.state_fingerprint or "")
                or self.paint_digests == list(other.paint_digests)
            )
        return self.state_fingerprint == other.state_fingerprint


def load_story_log_pair(
    path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    path = Path(path)
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("Story Log must be a JSON array of entries")
    prov = None
    alt = path.parent / f"{path.stem}.provenance.json"
    if alt.is_file():
        prov = json.loads(alt.read_text(encoding="utf-8"))
    return [dict(e) for e in entries], prov


def scenario_from_provenance(provenance: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a minimal host scenario dict from Synesyn provenance ``stage``."""
    if not provenance:
        return {}
    stage = provenance.get("stage") or {}
    scenario: dict[str, Any] = {
        "scenario_key": stage.get("scenario_key") or provenance.get("scenario"),
        "scenario_name": stage.get("scenario_name") or provenance.get("scenario"),
        "default_background": stage.get("default_background", ""),
        "cast": list(stage.get("cast") or []),
        "collection": stage.get("collection"),
    }
    # Preserve lumur_* sections if embedded in provenance meta.
    for key in ("lumur_audience", "lumur_layout", "lumur_story_stage"):
        if key in provenance:
            scenario[key] = provenance[key]
        if isinstance(stage, Mapping) and key in stage:
            scenario[key] = stage[key]
    return {k: v for k, v in scenario.items() if v not in (None, "", [])}


def replay_story_log(
    entries: Sequence[Mapping[str, Any]],
    *,
    receiver: MockStoryStageReceiver | None = None,
    scenario: Mapping[str, Any] | None = None,
    choices: Sequence[str] | None = None,
) -> MockStoryStageReceiver:
    """Feed Story Log entries into the mock host (playback host pattern)."""
    recv = receiver or MockStoryStageReceiver(scenario=dict(scenario or {}))
    if scenario:
        recv.scenario = dict(scenario)
    if choices:
        recv.set_choices(choices)
    for entry in entries:
        ts = 0.0
        if entry.get("timestamp_us") is not None:
            ts = float(entry["timestamp_us"]) / 1_000_000.0
        recv.append_log_entry(dict(entry), timestamp=ts)
        # If the entry carries choices, refresh available options.
        if isinstance(entry.get("choices"), list):
            recv.set_choices([str(c) for c in entry["choices"]])
    return recv


def replay_audience_events(
    events: Sequence[Mapping[str, Any] | Any],
    bridge: AudienceSteeringBridge,
) -> list[StageAction]:
    """Re-drive steering from recorded audience events (deterministic)."""
    return bridge.process_batch(list(events))


def replay_stage_actions(
    actions: Sequence[Mapping[str, Any] | StageAction],
    receiver: MockStoryStageReceiver,
    *,
    steered: bool = True,
) -> None:
    for raw in actions:
        action = raw if isinstance(raw, StageAction) else StageAction.from_dict(dict(raw))
        # During pure action replay, force apply regardless of opt-in when
        # ``steered=False`` means "recorded truth" — but for identity with live
        # path we honour steering_enabled when steered=True.
        receiver.apply(action, steered=steered and action.kind != "ambience" and action.kind != "append_log")


def replay_session(
    recording: SessionRecording | str | Path,
    *,
    room_package_dir: str | Path | None = None,
    texture_size: tuple[int, int] = (32, 32),
    project_paint: bool = True,
    choices: Sequence[str] | None = None,
    prefer_recorded_actions: bool = True,
) -> ReplayResult:
    """Replay a session: Story Log + audience/actions → stub stage + paint.

    When ``prefer_recorded_actions`` is True (default), the recorded
    ``stage_actions`` stream is applied directly — this is the authoritative
    deterministic path. Audience events are still available for re-derivation
    tests via :func:`replay_session_from_events`.
    """
    if not isinstance(recording, SessionRecording):
        recording = load_session(recording)

    scenario = dict(recording.scenario)
    cfg = audience_config_from_scenario(scenario)
    recv = MockStoryStageReceiver(scenario=scenario)
    recv.steering_enabled = cfg.enabled
    if choices:
        recv.set_choices(choices)
    elif recording.story_log:
        # Infer choices from first entry that lists them.
        for entry in recording.story_log:
            if isinstance(entry.get("choices"), list) and entry["choices"]:
                recv.set_choices([str(c) for c in entry["choices"]])
                break

    # 1) Story Log dialogue pacing.
    if recording.story_log:
        replay_story_log(recording.story_log, receiver=recv, scenario=scenario)

    # 2) Authoritative stage actions (steering + ambience).
    if prefer_recorded_actions and recording.stage_actions:
        replay_stage_actions(recording.stage_actions, recv, steered=True)
    elif recording.audience_events:
        bridge = AudienceSteeringBridge(config=cfg, receiver=recv)
        bridge.process_batch(recording.audience_events)

    # 3) Paint projection from stub source (same path as slice 3).
    paint_digests: list[str] = []
    projections: list[Any] = []
    pkg = Path(room_package_dir or recording.room_package_ref or "")
    godot_dir = pkg / "godot" if (pkg / "godot").is_dir() else pkg
    if project_paint and godot_dir.is_dir() and (godot_dir / "paint_manifest.json").is_file():
        layout = layout_from_scenario(scenario)
        times = [0.0]
        if recording.story_log:
            times = []
            for entry in recording.story_log:
                if entry.get("timestamp_us") is not None:
                    times.append(float(entry["timestamp_us"]) / 1_000_000.0)
                else:
                    times.append(float(len(times)))
        if not times:
            times = [0.0]
        intensity = float(recv.parameters.get(cfg.intensity_parameter, 0.0) or 0.0)
        from lumur_synesyn.story_stage_layers import STUB_LAYER_COLORS, LAYER_AMBIENCE

        colors = dict(STUB_LAYER_COLORS)
        if intensity > 0:
            # Tint ambience so steered intensity affects paint digests.
            base = np.asarray(colors[LAYER_AMBIENCE], dtype=np.float32)
            colors[LAYER_AMBIENCE] = tuple(
                float(x) for x in np.clip(base * (0.5 + 0.5 * intensity), 0.0, 1.0)
            )
        src = StubStoryStageSource(
            scenario=scenario, include_clip=False, colors=colors
        )
        for t in times:
            projection, painted = project_from_source(
                src,
                godot_dir,
                time_s=t,
                layout=layout,
                texture_size=texture_size,
            )
            projections.append(projection)
            paint_digests.append(recv.record_paint_array(painted))
    elif recording.paint_digests:
        # No room package available — reuse recorded digests for fingerprint.
        for d in recording.paint_digests:
            recv.record_paint_digest(d)
        paint_digests = list(recording.paint_digests)

    fingerprint = recv.state_fingerprint()
    return ReplayResult(
        receiver=recv,
        paint_digests=paint_digests,
        state_fingerprint=fingerprint,
        projections=projections,
        story_log=list(recv.story_log),
        steered_actions=[a.to_dict() for a in recv.steered_actions],
    )


def replay_session_from_events(
    recording: SessionRecording,
    *,
    room_package_dir: str | Path | None = None,
    texture_size: tuple[int, int] = (32, 32),
    choices: Sequence[str] | None = None,
) -> ReplayResult:
    """Re-derive steering from audience events (for debounce / opt-in tests)."""
    clone = SessionRecording.from_dict(recording.to_dict())
    clone.stage_actions = []  # force event re-derivation
    return replay_session(
        clone,
        room_package_dir=room_package_dir,
        texture_size=texture_size,
        choices=choices,
        prefer_recorded_actions=False,
    )


def record_and_fingerprint(
    *,
    room_package_dir: str | Path,
    scenario: Mapping[str, Any],
    audience_events: Sequence[Any],
    story_log: Sequence[Mapping[str, Any]] | None = None,
    choices: Sequence[str] | None = None,
    texture_size: tuple[int, int] = (32, 32),
) -> tuple[SessionRecording, ReplayResult]:
    """Helper: process events once, finalize session, replay for fingerprint."""
    from lumur_synesyn.session_record import SessionRecorder

    cfg = audience_config_from_scenario(scenario)
    recv = MockStoryStageReceiver(scenario=dict(scenario))
    recv.steering_enabled = cfg.enabled
    if choices:
        recv.set_choices(choices)
    bridge = AudienceSteeringBridge(config=cfg, receiver=recv)
    applied = bridge.process_batch(list(audience_events))
    if story_log:
        for entry in story_log:
            recv.append_log_entry(dict(entry))

    rec = SessionRecorder(
        room_package_ref=str(room_package_dir),
        scenario=dict(scenario),
    )
    rec.record_audience_batch(audience_events)
    rec.record_actions(list(recv.actions))
    if story_log:
        rec.set_story_log(story_log)

    draft = rec.finalize(story_log=recv.story_log)
    draft.stage_actions = [a.to_dict() for a in recv.actions]
    result = replay_session(
        draft,
        room_package_dir=room_package_dir,
        texture_size=texture_size,
        choices=choices,
        prefer_recorded_actions=True,
    )
    draft.paint_digests = list(result.paint_digests)
    draft.state_fingerprint = result.state_fingerprint
    return draft, result
