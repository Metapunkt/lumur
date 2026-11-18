"""End-to-end tracking: raw pose → subtraction filter → track → footsteps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from lumur.track.footsteps import FootstepDetector, FootstepEvent
from lumur.track.pose import DetectedPerson, PoseDetector
from lumur.track.subtraction import PredictedFrameSubtractor, SubtractionResult
from lumur.track.tracker import PersonTrack, SimpleByteTracker


@dataclass
class TrackingResult:
    detections: list[DetectedPerson]
    filtered_detections: list[DetectedPerson]
    tracks: list[PersonTrack]
    footsteps: list[FootstepEvent]
    subtraction: SubtractionResult | None
    timestamp: float
    rejected_count: int = 0


@dataclass
class TrackingPipeline:
    """Compose ADR 0005 pieces into one step callable from the companion."""

    detector: PoseDetector
    tracker: SimpleByteTracker
    footstep_detector: FootstepDetector
    subtractor: PredictedFrameSubtractor | None = None
    min_ankle_keep: int = 1  # ankles that must survive the mask
    timestamp: float = 0.0
    frame_dt: float = 1.0 / 30.0
    events: list[FootstepEvent] = field(default_factory=list)

    def push_projector_frame(self, pattern: np.ndarray | None) -> None:
        if self.subtractor is not None:
            self.subtractor.push_projector_frame(pattern)

    def filter_detections(
        self,
        detections: list[DetectedPerson],
        projected_mask: np.ndarray,
    ) -> tuple[list[DetectedPerson], int]:
        """Drop detections explained by projected content (ADR 0005).

        Ankles on a lit floor often *agree* with the empty-room prediction, so
        the filter keys off upper-body / majority keypoints: a painted
        silhouette on the wall matches the prediction everywhere; a real
        person occludes and disagrees at torso/head.
        """
        kept: list[DetectedPerson] = []
        rejected = 0
        upper = (
            "nose",
            "left_shoulder",
            "right_shoulder",
            "left_hip",
            "right_hip",
        )
        assert self.subtractor is not None
        for det in detections:
            pts = []
            for name in upper:
                kp = det.keypoints.get(name)
                if kp is not None and kp.visible:
                    pts.append((kp.u, kp.v))
            if len(pts) < 2:
                # Fall back to all visible joints.
                pts = [
                    (kp.u, kp.v)
                    for kp in det.keypoints.values()
                    if kp.visible
                ]
            if not pts:
                rejected += 1
                continue
            flags = self.subtractor.filter_keypoints(pts, projected_mask)
            # Keep when at least half the upper-body samples look like foreground.
            if sum(flags) < max(1, (len(flags) + 1) // 2):
                rejected += 1
                continue
            kept.append(det)
        return kept, rejected

    def step(
        self,
        frame_bgr: np.ndarray,
        *,
        timestamp: float | None = None,
        advance_time: bool = True,
    ) -> TrackingResult:
        if timestamp is None:
            if advance_time:
                self.timestamp += self.frame_dt
            timestamp = self.timestamp
        else:
            self.timestamp = float(timestamp)

        # Pose on the RAW frame (never on a subtracted image).
        detections = self.detector.detect(frame_bgr)
        subtraction = None
        rejected = 0
        filtered = detections
        if self.subtractor is not None:
            subtraction = self.subtractor.compare(frame_bgr)
            filtered, rejected = self.filter_detections(
                detections, subtraction.projected_mask
            )

        tracks = self.tracker.update(filtered)
        footsteps = self.footstep_detector.update(tracks, float(timestamp))
        self.events.extend(footsteps)
        return TrackingResult(
            detections=detections,
            filtered_detections=filtered,
            tracks=tracks,
            footsteps=footsteps,
            subtraction=subtraction,
            timestamp=float(timestamp),
            rejected_count=rejected,
        )

    def metrics(self) -> dict[str, Any]:
        return {
            "footstep_count": len(self.events),
            "active_tracks": len(self.tracker.tracks),
            "timestamp": self.timestamp,
        }
