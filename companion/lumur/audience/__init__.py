"""Audience presence / zone / gathering events (PRD-002 slice 4).

Derived from tracking on floor surface coordinates. Lumur core — no Synesyn.
Opt-in story steering lives in the optional bridge package only; these events
may always drive ambience and PRD-001 ripples (REQ-002-012).
"""

from __future__ import annotations

from lumur.audience.detector import AudienceDetector, AudienceState
from lumur.audience.dwell import DwellFire, DwellGate, DwellWatch
from lumur.audience.events import AudienceEvent
from lumur.audience.zones import FloorZone, point_in_zone

__all__ = [
    "AudienceDetector",
    "AudienceEvent",
    "AudienceState",
    "DwellFire",
    "DwellGate",
    "DwellWatch",
    "FloorZone",
    "point_in_zone",
]
