"""Optional Synesyn bridge for Lumur (PRD-002 slices 2–4).

Install with ``pip install -e ".[synesyn]"`` (or just ``pip install -e .`` —
this package ships beside ``lumur`` and is imported only when configured).
Lumur core never imports this module.

Slice 2: Hub surface-generator provider.
Slice 3: Story Stage layer → surface layout + paint projection.
Slice 4: Opt-in audience steering + Story Log / session replay.
"""

from __future__ import annotations

from lumur_synesyn.audience_config import (
    LumurAudienceConfig,
    audience_config_from_scenario,
    is_audience_steering_enabled,
)
from lumur_synesyn.audience_steering import AudienceSteeringBridge
from lumur_synesyn.config import HubConfig, load_hub_config
from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator
from lumur_synesyn.mock_story_stage import MockStoryStageReceiver, StageAction
from lumur_synesyn.replay import replay_session, replay_story_log
from lumur_synesyn.session_record import SessionRecorder, SessionRecording, save_session
from lumur_synesyn.story_stage_layout import (
    StoryStageLayout,
    layout_from_scenario,
    resolve_all_layers,
    resolve_surface_role,
)
from lumur_synesyn.story_stage_layers import StubStoryStageSource
from lumur_synesyn.story_stage_project import project_from_source, project_snapshot

__all__ = [
    "AudienceSteeringBridge",
    "HubConfig",
    "LumurAudienceConfig",
    "MockStoryStageReceiver",
    "SessionRecorder",
    "SessionRecording",
    "StageAction",
    "StoryStageLayout",
    "StubStoryStageSource",
    "SynesynHubSurfaceGenerator",
    "audience_config_from_scenario",
    "is_audience_steering_enabled",
    "layout_from_scenario",
    "load_hub_config",
    "project_from_source",
    "project_snapshot",
    "replay_session",
    "replay_story_log",
    "resolve_all_layers",
    "resolve_surface_role",
    "save_session",
]
