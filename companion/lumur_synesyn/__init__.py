"""Optional Synesyn Hub bridge for Lumur (PRD-002 slice 2).

Install with ``pip install -e ".[synesyn]"`` (or just ``pip install -e .`` —
this package ships beside ``lumur`` and is imported only when configured).
Lumur core never imports this module.
"""

from __future__ import annotations

from lumur_synesyn.config import HubConfig, load_hub_config
from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator

__all__ = [
    "HubConfig",
    "SynesynHubSurfaceGenerator",
    "load_hub_config",
]
