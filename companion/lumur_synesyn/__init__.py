"""Optional Synesyn bridge for Lumur (PRD-002 slices 2–3).

Install with ``pip install -e ".[synesyn]"`` (or just ``pip install -e .`` —
this package ships beside ``lumur`` and is imported only when configured).
Lumur core never imports this module.

Slice 2: Hub surface-generator provider.
Slice 3: Story Stage layer → surface layout + paint projection (stub source
for headless sim; live ``story_stage`` observed non-invasively from Godot).
"""

from __future__ import annotations

from lumur_synesyn.config import HubConfig, load_hub_config
from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator
from lumur_synesyn.story_stage_layout import (
    StoryStageLayout,
    layout_from_scenario,
    resolve_all_layers,
    resolve_surface_role,
)
from lumur_synesyn.story_stage_layers import StubStoryStageSource
from lumur_synesyn.story_stage_project import project_from_source, project_snapshot

__all__ = [
    "HubConfig",
    "StoryStageLayout",
    "StubStoryStageSource",
    "SynesynHubSurfaceGenerator",
    "layout_from_scenario",
    "load_hub_config",
    "project_from_source",
    "project_snapshot",
    "resolve_all_layers",
    "resolve_surface_role",
]
