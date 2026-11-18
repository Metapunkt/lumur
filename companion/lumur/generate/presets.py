"""Lumur workflow presets with Synesyn-aligned tag selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PRESET_SCHEMA = "lumur.workflow_preset"
PRESET_SCHEMA_VERSION = "1.0"
TAG_SURFACE_ROLE = "lumur:surface_role"
TAG_ROOM = "lumur:room"
TAG_SCENARIO = "lumur:scenario"


def default_presets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "presets" / "workflows"


def load_preset(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != PRESET_SCHEMA:
        raise ValueError(f"expected schema {PRESET_SCHEMA!r}, got {data.get('schema')!r}")
    if str(data.get("schema_version")) != PRESET_SCHEMA_VERSION:
        raise ValueError(f"unsupported preset schema_version {data.get('schema_version')!r}")
    if not isinstance(data.get("workflow"), dict):
        raise ValueError("preset.workflow must be a ComfyUI API graph object")
    data.setdefault("id", path.stem)
    data["_path"] = str(path)
    return data


def discover_presets(directories: list[str | Path] | None = None) -> list[dict[str, Any]]:
    dirs = [Path(d) for d in (directories or [default_presets_dir()])]
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            try:
                preset = load_preset(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            pid = str(preset.get("id") or path.stem)
            if pid in seen:
                continue
            seen.add(pid)
            found.append(preset)
    return found


def preset_tags(preset: dict[str, Any]) -> list[str]:
    meta = dict(preset.get("metadata") or {})
    preset_meta = dict(meta.get("preset") or {})
    tags = preset_meta.get("tags") or preset.get("tags") or []
    return [str(t).strip() for t in tags if str(t).strip()]


def has_tag(tags: list[str], wanted: str) -> bool:
    wanted = wanted.strip()
    return any(t == wanted for t in tags)


def tag_value(tags: list[str], prefix: str) -> str | None:
    prefix = prefix if prefix.endswith("=") else f"{prefix}="
    for t in tags:
        if t.startswith(prefix):
            return t[len(prefix) :]
    return None


def surface_role_tag(role: str) -> str:
    return f"{TAG_SURFACE_ROLE}={_slug(role)}"


def _slug(value: str) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def select_preset(
    presets: list[dict[str, Any]],
    *,
    surface_role: str,
    room_id: str | None = None,
    scenario_key: str | None = None,
    preset_id: str | None = None,
) -> dict[str, Any] | None:
    """Pick the most specific preset for a surface role.

    Fallback order (mirrors ScenSyn / SynPunkt tag scoring):
    role + room + scenario → role + room → role + scenario → role → any
    tagged role match. Explicit ``preset_id`` wins when present.
    """
    if preset_id:
        for p in presets:
            if str(p.get("id") or "") == preset_id:
                return p
        return None

    role_tag = surface_role_tag(surface_role)
    room_tag = f"{TAG_ROOM}={_slug(room_id)}" if room_id else None
    scenario_tag = f"{TAG_SCENARIO}={_slug(scenario_key)}" if scenario_key else None

    best: dict[str, Any] | None = None
    best_score = -10_000
    for preset in presets:
        tags = preset_tags(preset)
        if not has_tag(tags, role_tag):
            continue
        score = 1
        has_room = bool(room_tag and has_tag(tags, room_tag))
        has_scenario = bool(scenario_tag and has_tag(tags, scenario_tag))
        if has_room:
            score += 10
        if has_scenario:
            score += 100
        # Penalise mismatched declared scope (same idea as ScenSyn).
        declared_room = tag_value(tags, TAG_ROOM)
        if declared_room and room_id and declared_room != _slug(room_id):
            score -= 50
        declared_scenario = tag_value(tags, TAG_SCENARIO)
        if declared_scenario and scenario_key and declared_scenario != _slug(scenario_key):
            score -= 50
        if score > best_score:
            best_score = score
            best = preset
    return best
