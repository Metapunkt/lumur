"""Pose, predicted-frame subtraction, tracking, and footstep events.

Audience presence / zone / gathering live in ``lumur.audience`` (import that
package directly — avoided here to prevent an import cycle with footsteps).

See docs/companion/tracking.md and ADR 0005 / ADR 0014.
"""

from __future__ import annotations

from lumur.track.footsteps import FootstepDetector, FootstepEvent
from lumur.track.pipeline import TrackingPipeline, TrackingResult
from lumur.track.pose import (
    DetectedPerson,
    Keypoint,
    OraclePoseDetector,
    PoseDetector,
    create_pose_detector,
)
from lumur.track.radiometric import RadiometricModel, calibrate_radiometric
from lumur.track.subtraction import PredictedFrameSubtractor
from lumur.track.tracker import PersonTrack, SimpleByteTracker

__all__ = [
    "Keypoint",
    "DetectedPerson",
    "PoseDetector",
    "OraclePoseDetector",
    "create_pose_detector",
    "RadiometricModel",
    "calibrate_radiometric",
    "PredictedFrameSubtractor",
    "SimpleByteTracker",
    "PersonTrack",
    "FootstepEvent",
    "FootstepDetector",
    "TrackingPipeline",
    "TrackingResult",
]
