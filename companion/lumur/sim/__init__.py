"""Simulated projector–camera rig for hardware-free development.

See docs/companion/simulation.md and ADR 0011.
"""

from __future__ import annotations

from lumur.sim.backend import SimCamera, SimDisplay, SimRig
from lumur.sim.scene import list_presets, load_scene, preset_path
from lumur.sim.ground_truth import GroundTruth

__all__ = [
    "SimRig",
    "SimCamera",
    "SimDisplay",
    "GroundTruth",
    "load_scene",
    "list_presets",
    "preset_path",
]
