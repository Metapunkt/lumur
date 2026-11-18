"""Python mock of the Godot / Story Stage receiver (PRD-002 slice 4 tests).

Mirrors the seam ``lumur_synesyn`` uses to drive Synesyn Story Stage without
importing Godot or ``story_stage``. Records advances, choices, parameters,
story-log appends, and projected paint digests for deterministic replay checks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class StageAction:
    """One steering or replay action applied to the stage."""

    kind: str  # advance_beat | choose_option | set_parameter | append_log | ambience
    timestamp: float = 0.0
    option_index: int | None = None
    option_label: str | None = None
    parameter: str | None = None
    value: Any = None
    entry: dict[str, Any] | None = None
    source_event: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "kind": self.kind,
            "timestamp": float(self.timestamp),
        }
        if self.option_index is not None:
            doc["option_index"] = int(self.option_index)
        if self.option_label is not None:
            doc["option_label"] = self.option_label
        if self.parameter is not None:
            doc["parameter"] = self.parameter
        if self.value is not None:
            doc["value"] = self.value
        if self.entry is not None:
            doc["entry"] = dict(self.entry)
        if self.source_event is not None:
            doc["source_event"] = dict(self.source_event)
        if self.meta:
            doc["meta"] = dict(self.meta)
        return doc

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> StageAction:
        return cls(
            kind=str(raw["kind"]),
            timestamp=float(raw.get("timestamp", 0.0)),
            option_index=(
                int(raw["option_index"]) if raw.get("option_index") is not None else None
            ),
            option_label=(
                str(raw["option_label"]) if raw.get("option_label") is not None else None
            ),
            parameter=str(raw["parameter"]) if raw.get("parameter") is not None else None,
            value=raw.get("value"),
            entry=dict(raw["entry"]) if isinstance(raw.get("entry"), dict) else None,
            source_event=(
                dict(raw["source_event"])
                if isinstance(raw.get("source_event"), dict)
                else None
            ),
            meta=dict(raw.get("meta") or {}),
        )


@dataclass
class MockStoryStageReceiver:
    """Headless stand-in for Godot Story Stage + paint output.

    Call :meth:`apply` (or the typed helpers) the same way the live bridge
    would call ``commit_local_line`` / choice buttons / ambient parameters.
    """

    scenario: dict[str, Any] = field(default_factory=dict)
    story_log: list[dict[str, Any]] = field(default_factory=list)
    choices_available: list[str] = field(default_factory=list)
    beat_index: int = 0
    parameters: dict[str, Any] = field(default_factory=dict)
    actions: list[StageAction] = field(default_factory=list)
    steered_actions: list[StageAction] = field(default_factory=list)
    ambience_events: list[dict[str, Any]] = field(default_factory=list)
    # Deterministic paint digests recorded when layers are projected.
    paint_digests: list[str] = field(default_factory=list)
    steering_enabled: bool = False

    def reset(self) -> None:
        self.story_log.clear()
        self.choices_available.clear()
        self.beat_index = 0
        self.parameters.clear()
        self.actions.clear()
        self.steered_actions.clear()
        self.ambience_events.clear()
        self.paint_digests.clear()

    def set_choices(self, choices: Sequence[str]) -> None:
        self.choices_available = [str(c) for c in choices]

    def apply(self, action: StageAction, *, steered: bool = False) -> bool:
        """Apply an action. Returns False if steered=True but steering is off."""
        if steered and not self.steering_enabled:
            # Still allow ambience-only kinds through.
            if action.kind != "ambience":
                return False
        self.actions.append(action)
        if steered and action.kind != "ambience":
            self.steered_actions.append(action)

        if action.kind == "advance_beat":
            self.beat_index += 1
        elif action.kind == "choose_option":
            idx = action.option_index
            label = action.option_label
            if idx is not None and 0 <= idx < len(self.choices_available):
                label = self.choices_available[idx]
            entry = {
                "sender": "_audience",
                "message": label or f"option:{idx}",
                "timestamp_us": int(action.timestamp * 1_000_000),
                "choices": list(self.choices_available),
            }
            self.story_log.append(entry)
            self.beat_index += 1
        elif action.kind == "set_parameter":
            if action.parameter is not None:
                self.parameters[action.parameter] = action.value
        elif action.kind == "append_log":
            if action.entry:
                self.story_log.append(dict(action.entry))
        elif action.kind == "ambience":
            if action.source_event:
                self.ambience_events.append(dict(action.source_event))
        return True

    def advance_beat(self, timestamp: float = 0.0, **meta: Any) -> bool:
        return self.apply(
            StageAction(kind="advance_beat", timestamp=timestamp, meta=dict(meta)),
            steered=True,
        )

    def choose_option(
        self,
        option_index: int | None = None,
        option_label: str | None = None,
        timestamp: float = 0.0,
        **meta: Any,
    ) -> bool:
        return self.apply(
            StageAction(
                kind="choose_option",
                timestamp=timestamp,
                option_index=option_index,
                option_label=option_label,
                meta=dict(meta),
            ),
            steered=True,
        )

    def set_parameter(self, name: str, value: Any, timestamp: float = 0.0) -> bool:
        return self.apply(
            StageAction(
                kind="set_parameter",
                timestamp=timestamp,
                parameter=name,
                value=value,
            ),
            steered=True,
        )

    def append_log_entry(self, entry: dict[str, Any], timestamp: float = 0.0) -> bool:
        return self.apply(
            StageAction(kind="append_log", timestamp=timestamp, entry=entry),
            steered=False,
        )

    def forward_ambience(self, event: dict[str, Any], timestamp: float | None = None) -> bool:
        ts = float(timestamp if timestamp is not None else event.get("timestamp", 0.0))
        return self.apply(
            StageAction(kind="ambience", timestamp=ts, source_event=event),
            steered=False,
        )

    def record_paint_digest(self, digest: str) -> None:
        self.paint_digests.append(digest)

    def record_paint_array(self, arr: Any) -> str:
        """Hash a numpy-like array (or bytes) into a stable paint digest."""
        import numpy as np

        a = np.ascontiguousarray(arr)
        digest = hashlib.sha256(a.tobytes()).hexdigest()[:16]
        self.record_paint_digest(digest)
        return digest

    def state_fingerprint(self) -> str:
        """Canonical fingerprint of stage + paint for replay determinism."""
        payload = {
            "beat_index": self.beat_index,
            "parameters": self.parameters,
            "story_log": self.story_log,
            "steered": [a.to_dict() for a in self.steered_actions],
            "paint_digests": self.paint_digests,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
