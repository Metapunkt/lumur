"""Session recording: room package + audience events + Story Log refs.

Schema ``lumur.session`` v1. Together with a Story Log (+ provenance sidecar)
and the room package, this is enough to replay in the Lumur sim (REQ-002-015).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from lumur_synesyn.hub_client import HubError, SynesynHubClient
from lumur_synesyn.mock_story_stage import StageAction
from lumur_synesyn.room_artifact import register_room_package

SESSION_SCHEMA = "lumur.session"
SESSION_SCHEMA_VERSION = "1.0"
SESSION_ARTIFACT_TYPE = "json.lumur_session"


@dataclass
class SessionRecording:
    """One recorded installation / workshop session."""

    session_id: str
    room_package_ref: str  # local path and/or Hub artifact id
    room_artifact_id: str | None = None
    scenario: dict[str, Any] = field(default_factory=dict)
    audience_events: list[dict[str, Any]] = field(default_factory=list)
    stage_actions: list[dict[str, Any]] = field(default_factory=list)
    story_log: list[dict[str, Any]] = field(default_factory=list)
    story_log_ref: str | None = None
    story_log_provenance: dict[str, Any] | None = None
    paint_digests: list[str] = field(default_factory=list)
    state_fingerprint: str | None = None
    started_at: str = ""
    ended_at: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SESSION_SCHEMA,
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": self.session_id,
            "room_package_ref": self.room_package_ref,
            "room_artifact_id": self.room_artifact_id,
            "scenario": dict(self.scenario),
            "audience_events": list(self.audience_events),
            "stage_actions": list(self.stage_actions),
            "story_log": list(self.story_log),
            "story_log_ref": self.story_log_ref,
            "story_log_provenance": self.story_log_provenance,
            "paint_digests": list(self.paint_digests),
            "state_fingerprint": self.state_fingerprint,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "meta": dict(self.meta),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> SessionRecording:
        if raw.get("schema") not in (None, SESSION_SCHEMA):
            raise ValueError(f"unexpected session schema {raw.get('schema')!r}")
        return cls(
            session_id=str(raw.get("session_id") or uuid.uuid4().hex),
            room_package_ref=str(raw.get("room_package_ref") or ""),
            room_artifact_id=(
                str(raw["room_artifact_id"])
                if raw.get("room_artifact_id") is not None
                else None
            ),
            scenario=dict(raw.get("scenario") or {}),
            audience_events=[dict(e) for e in (raw.get("audience_events") or [])],
            stage_actions=[dict(a) for a in (raw.get("stage_actions") or [])],
            story_log=[dict(e) for e in (raw.get("story_log") or [])],
            story_log_ref=(
                str(raw["story_log_ref"]) if raw.get("story_log_ref") is not None else None
            ),
            story_log_provenance=(
                dict(raw["story_log_provenance"])
                if isinstance(raw.get("story_log_provenance"), dict)
                else None
            ),
            paint_digests=[str(x) for x in (raw.get("paint_digests") or [])],
            state_fingerprint=(
                str(raw["state_fingerprint"])
                if raw.get("state_fingerprint") is not None
                else None
            ),
            started_at=str(raw.get("started_at") or ""),
            ended_at=str(raw.get("ended_at") or ""),
            meta=dict(raw.get("meta") or {}),
        )


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class SessionRecorder:
    """Accumulate audience events + stage actions during a live / sim run."""

    room_package_ref: str
    scenario: dict[str, Any] = field(default_factory=dict)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    room_artifact_id: str | None = None
    audience_events: list[dict[str, Any]] = field(default_factory=list)
    stage_actions: list[dict[str, Any]] = field(default_factory=list)
    story_log: list[dict[str, Any]] = field(default_factory=list)
    story_log_ref: str | None = None
    story_log_provenance: dict[str, Any] | None = None
    paint_digests: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=_utc_now)
    meta: dict[str, Any] = field(default_factory=dict)

    def record_audience(self, event: Any) -> None:
        if hasattr(event, "to_dict"):
            self.audience_events.append(event.to_dict())
        else:
            self.audience_events.append(dict(event))

    def record_audience_batch(self, events: Sequence[Any]) -> None:
        for ev in events:
            self.record_audience(ev)

    def record_action(self, action: StageAction | dict[str, Any]) -> None:
        if isinstance(action, StageAction):
            self.stage_actions.append(action.to_dict())
        else:
            self.stage_actions.append(dict(action))

    def record_actions(self, actions: Sequence[StageAction | dict[str, Any]]) -> None:
        for a in actions:
            self.record_action(a)

    def set_story_log(
        self,
        entries: Sequence[Mapping[str, Any]],
        *,
        ref: str | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> None:
        self.story_log = [dict(e) for e in entries]
        if ref is not None:
            self.story_log_ref = ref
        if provenance is not None:
            self.story_log_provenance = dict(provenance)

    def load_story_log_files(self, path: str | Path) -> None:
        """Load Synesyn Story Log JSON (+ optional ``.provenance.json`` sidecar)."""
        path = Path(path)
        entries = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(entries, list):
            raise ValueError("Story Log must be a JSON array")
        self.story_log = [dict(e) for e in entries]
        self.story_log_ref = str(path)
        side = path.with_suffix(path.suffix + ".provenance.json")
        # Synesyn uses stem.provenance.json beside stem.json
        alt = path.parent / f"{path.stem}.provenance.json"
        for candidate in (alt, side):
            if candidate.is_file():
                self.story_log_provenance = json.loads(
                    candidate.read_text(encoding="utf-8")
                )
                break

    def finalize(
        self,
        *,
        paint_digests: Sequence[str] | None = None,
        state_fingerprint: str | None = None,
        story_log: Sequence[Mapping[str, Any]] | None = None,
    ) -> SessionRecording:
        if paint_digests is not None:
            self.paint_digests = [str(x) for x in paint_digests]
        if story_log is not None:
            self.story_log = [dict(e) for e in story_log]
        return SessionRecording(
            session_id=self.session_id,
            room_package_ref=self.room_package_ref,
            room_artifact_id=self.room_artifact_id,
            scenario=dict(self.scenario),
            audience_events=list(self.audience_events),
            stage_actions=list(self.stage_actions),
            story_log=list(self.story_log),
            story_log_ref=self.story_log_ref,
            story_log_provenance=self.story_log_provenance,
            paint_digests=list(self.paint_digests),
            state_fingerprint=state_fingerprint,
            started_at=self.started_at,
            ended_at=_utc_now(),
            meta=dict(self.meta),
        )


def save_session(recording: SessionRecording, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(recording.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_session(path: str | Path) -> SessionRecording:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return SessionRecording.from_dict(raw)


def register_session_with_hub(
    client: SynesynHubClient,
    recording: SessionRecording,
    *,
    register_room: bool = True,
    room_package_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register session (+ optional room package) as Hub artifacts.

    Uses generic ``POST /substrate/artifacts`` (same pattern as
    ``json.lumur_room``). Official type docs remain a Synesyn-side touchpoint.
    """
    room_art = recording.room_artifact_id
    room_result = None
    if register_room and room_package_dir is not None:
        room_result = register_room_package(
            client, room_package_dir, room_id=None, metadata=metadata
        )
        room_art = room_result.get("artifact_id")
        recording.room_artifact_id = room_art

    payload = recording.to_dict()
    payload["room_artifact_id"] = room_art
    meta = {
        "provenance": {
            "generated_by": "lumur_synesyn.session_record",
            "session_id": recording.session_id,
            "room_artifact_id": room_art,
        },
        "ui": {"display_name": f"Lumur session {recording.session_id[:8]}"},
        "lumur": {"kind": "session", "touchpoint": SESSION_ARTIFACT_TYPE},
    }
    if metadata:
        meta.update(metadata)

    try:
        art_id = client.create_artifact_json(
            SESSION_ARTIFACT_TYPE, payload, metadata=meta
        )
    except HubError:
        raise
    return {
        "ok": True,
        "artifact_id": art_id,
        "artifact_type": SESSION_ARTIFACT_TYPE,
        "session_id": recording.session_id,
        "room_artifact_id": room_art,
        "room_registration": room_result,
    }
