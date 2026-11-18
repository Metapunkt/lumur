"""Discover SynPunkt ``json.workflow`` presets tagged ``lumur:surface_role=…``."""

from __future__ import annotations

from typing import Any

from lumur.generate.presets import select_preset, surface_role_tag
from lumur_synesyn.hub_client import SynesynHubClient

# Re-export for callers / tests.
__all__ = [
    "discover_hub_workflow_presets",
    "select_hub_preset",
    "surface_role_tag",
]


def _normalize_hub_preset(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Hub artifact row into the shape ``select_preset`` understands."""
    art_id = str(rec.get("id") or "").strip()
    if not art_id:
        return None
    meta = rec.get("metadata") if isinstance(rec.get("metadata"), dict) else {}
    preset_meta = meta.get("preset") if isinstance(meta.get("preset"), dict) else {}
    tags = preset_meta.get("tags") or meta.get("tags") or []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    name = str(preset_meta.get("name") or art_id)
    # Workflow body may be inline on the record (mock) or fetched later via artifact_id.
    workflow = rec.get("inline_json")
    if not isinstance(workflow, dict):
        workflow = {}
    return {
        "id": art_id,
        "schema": "synesyn.json.workflow",
        "name": name,
        "metadata": {"preset": {"tags": tags, **{k: v for k, v in preset_meta.items() if k != "tags"}}},
        "workflow": workflow,
        "artifact_id": art_id,
        "artifact_type": "json.workflow",
        "uri": rec.get("uri"),
        "controls": dict(preset_meta.get("controls") or meta.get("controls") or {}),
        "control_nodes": dict(preset_meta.get("control_nodes") or meta.get("control_nodes") or {}),
        "size_patches": list(
            preset_meta.get("size_patches")
            or meta.get("size_patches")
            or rec.get("_size_patches")
            or []
        ),
        "_hub_record": rec,
    }


def discover_hub_workflow_presets(
    client: SynesynHubClient, *, limit: int = 100
) -> list[dict[str, Any]]:
    rows = client.query_artifacts_by_type("json.workflow", limit=limit)
    found: list[dict[str, Any]] = []
    for rec in rows:
        preset = _normalize_hub_preset(rec)
        if preset is None:
            continue
        found.append(preset)
    return found


def select_hub_preset(
    presets: list[dict[str, Any]],
    *,
    surface_role: str,
    room_id: str | None = None,
    scenario_key: str | None = None,
    preset_id: str | None = None,
) -> dict[str, Any] | None:
    """Most-specific ``lumur:surface_role`` match (same fallback as Lumur local presets)."""
    return select_preset(
        presets,
        surface_role=surface_role,
        room_id=room_id,
        scenario_key=scenario_key,
        preset_id=preset_id,
    )


def resolve_workflow_inline(
    client: SynesynHubClient, preset: dict[str, Any]
) -> dict[str, Any]:
    """Return the ComfyUI API graph for a Hub preset (fetch if needed)."""
    inline = preset.get("workflow")
    if isinstance(inline, dict) and inline:
        return dict(inline)
    art_id = str(preset.get("artifact_id") or preset.get("id") or "").strip()
    if not art_id:
        raise ValueError("hub preset missing artifact_id / workflow")
    return client.get_artifact_json(art_id)
