"""Simulated projector–camera rig for hardware-free development.

See docs/companion/simulation.md and ADR 0011.
"""

from __future__ import annotations

from lumur.sim.backend import SimCamera, SimDisplay, SimRig
from lumur.sim.ground_truth import GroundTruth
from lumur.sim.people import (
    AnimatedPerson,
    PeopleSim,
    PersonPose3D,
    default_crossing_people,
)
from lumur.sim.scene import list_presets, load_scene, preset_path

__all__ = [
    "SimRig",
    "SimCamera",
    "SimDisplay",
    "GroundTruth",
    "PeopleSim",
    "AnimatedPerson",
    "PersonPose3D",
    "default_crossing_people",
    "load_scene",
    "list_presets",
    "preset_path",
]
