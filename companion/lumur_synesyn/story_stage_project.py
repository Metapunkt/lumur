"""Project Story Stage layers onto Lumur surfaces via paint mode.

Python reference path used for headless sim verification (REQ-002-016).
Godot mirror lives in ``addons/lumur_synesyn/story_stage_projector.gd``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from lumur.paint.render import PaintAssignment, paint_from_godot_assets
from lumur_synesyn.story_stage_compose import compose_layer_texture
from lumur_synesyn.story_stage_layers import (
    LAYER_AMBIENCE,
    LAYER_BACKDROP,
    LAYER_CAPTION,
    LAYER_CHARACTER,
    LAYER_CLIP,
    StoryStageSnapshot,
    StoryStageSource,
    StubStoryStageSource,
)
from lumur_synesyn.story_stage_layout import (
    StoryStageLayout,
    layout_from_scenario,
    resolve_all_layers,
)


# When character + clip share a surface, clip wins (talking video / FlashHead).
# Caption shares the backdrop wall: compose caption over backdrop in-texture.
_SURFACE_STACK: tuple[tuple[str, ...], ...] = (
    (LAYER_BACKDROP, LAYER_CAPTION),
    (LAYER_CHARACTER, LAYER_CLIP),
    (LAYER_AMBIENCE,),
)


@dataclass
class ProjectedLayer:
    layer: str
    surface_role: str
    surface_id: int
    texture: np.ndarray
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoryStageProjection:
    """Result of mapping a snapshot onto a room's paint assignments."""

    projected: list[ProjectedLayer]
    assignments: list[PaintAssignment]
    layout: StoryStageLayout
    role_binding: dict[str, str | None]
    skipped: list[str] = field(default_factory=list)

    def by_layer(self) -> dict[str, ProjectedLayer]:
        return {p.layer: p for p in self.projected}

    def binding(self) -> dict[str, str | None]:
        return dict(self.role_binding)


def _load_role_index(godot_dir: Path) -> dict[str, int]:
    manifest = json.loads((godot_dir / "paint_manifest.json").read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in manifest.get("role_index", {}).items()}


def project_snapshot(
    snapshot: StoryStageSnapshot,
    role_index: dict[str, int],
    *,
    layout: StoryStageLayout | None = None,
    texture_size: tuple[int, int] = (64, 64),
) -> StoryStageProjection:
    """Resolve layout and compose per-surface textures from a snapshot."""
    layout = layout or layout_from_scenario(snapshot.scenario)
    binding = resolve_all_layers(role_index, layout)
    # Group layers that land on the same surface role.
    by_role: dict[str, list[str]] = {}
    skipped: list[str] = []
    for layer, role in binding.items():
        if layer not in snapshot.frames:
            continue
        if role is None:
            skipped.append(layer)
            continue
        by_role.setdefault(role, []).append(layer)

    projected: list[ProjectedLayer] = []
    # Compose each surface: follow stack order so caption overlays backdrop, etc.
    composed_roles: dict[str, np.ndarray] = {}
    for stack in _SURFACE_STACK:
        for layer in stack:
            role = binding.get(layer)
            if role is None or layer not in snapshot.frames:
                continue
            frame = snapshot.frames[layer]
            tex = compose_layer_texture(
                frame,
                surface_size=texture_size,
                safe_area=layout.safe_area_for(layer),
            )
            if role in composed_roles and layer in (LAYER_CAPTION, LAYER_CLIP):
                # Overlay: use non-black pixels / full blend for caption band & clip.
                base = composed_roles[role]
                if layer == LAYER_CAPTION:
                    # Caption occupies its safe band; paste non-clear pixels.
                    mask = np.any(tex > 0.02, axis=-1)
                    blended = base.copy()
                    blended[mask] = tex[mask]
                    composed_roles[role] = blended
                else:
                    fade = float(frame.meta.get("fade", 1.0))
                    composed_roles[role] = np.clip(
                        base * (1.0 - fade) + tex * fade, 0.0, 1.0
                    )
            else:
                composed_roles[role] = tex
            projected.append(
                ProjectedLayer(
                    layer=layer,
                    surface_role=role,
                    surface_id=int(role_index[role]),
                    texture=composed_roles[role],
                    meta={
                        "fade": float(frame.meta.get("fade", 1.0)),
                        "transition": frame.transition,
                    },
                )
            )

    assignments: list[PaintAssignment] = []
    for role, tex in composed_roles.items():
        assignments.append(
            PaintAssignment(
                surface_id=int(role_index[role]),
                color=(1.0, 1.0, 1.0),
                mode="texture",
                texture=tex,
            )
        )

    return StoryStageProjection(
        projected=projected,
        assignments=assignments,
        layout=layout,
        role_binding=binding,
        skipped=skipped,
    )


def project_from_source(
    source: StoryStageSource,
    godot_dir: str | Path,
    *,
    time_s: float = 0.0,
    layout: StoryStageLayout | None = None,
    texture_size: tuple[int, int] = (64, 64),
) -> tuple[StoryStageProjection, np.ndarray]:
    """Project a source snapshot and paint a projector RGB image."""
    godot_dir = Path(godot_dir)
    role_index = _load_role_index(godot_dir)
    snapshot = source.snapshot(time_s)
    if layout is None:
        layout = layout_from_scenario(snapshot.scenario)
    projection = project_snapshot(
        snapshot, role_index, layout=layout, texture_size=texture_size
    )
    painted = paint_from_godot_assets(godot_dir, projection.assignments)
    return projection, painted


def stub_default_source(scenario: dict[str, Any] | None = None) -> StubStoryStageSource:
    return StubStoryStageSource(scenario=dict(scenario or {}))
