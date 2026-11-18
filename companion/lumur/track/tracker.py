"""Lightweight multi-person tracker (ByteTrack-inspired, no hard dependency).

Associates detections across frames by centroid distance with a simple
high/low confidence two-stage match so identities stay stable when paths
cross. Optional ``byteTrack`` packages are not required.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from lumur.track.pose import DetectedPerson, Keypoint


@dataclass
class PersonTrack:
    track_id: int
    keypoints: dict[str, Keypoint]
    score: float
    age: int = 0
    hits: int = 1
    time_since_update: int = 0
    centroid: tuple[float, float] = (0.0, 0.0)
    source: str = "detector"

    def ankle(self, foot: str) -> Keypoint | None:
        return self.keypoints.get(f"{foot}_ankle")


@dataclass
class SimpleByteTracker:
    """Greedy distance association with tentative / confirmed tracks."""

    high_thresh: float = 0.5
    low_thresh: float = 0.2
    match_thresh_px: float = 40.0
    max_time_lost: int = 15
    _next_id: int = 1
    _tracks: list[PersonTrack] = field(default_factory=list)

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1

    @property
    def tracks(self) -> list[PersonTrack]:
        return list(self._tracks)

    def update(self, detections: list[DetectedPerson]) -> list[PersonTrack]:
        for t in self._tracks:
            t.age += 1
            t.time_since_update += 1

        high = [d for d in detections if d.score >= self.high_thresh]
        low = [
            d
            for d in detections
            if self.low_thresh <= d.score < self.high_thresh
        ]

        matched_t: set[int] = set()
        matched_d: set[int] = set()

        def associate(dets: list[DetectedPerson], track_indices: list[int]) -> None:
            nonlocal matched_t, matched_d
            if not dets or not track_indices:
                return
            cost = np.full((len(track_indices), len(dets)), np.inf)
            for ti, tidx in enumerate(track_indices):
                tc = self._tracks[tidx].centroid
                for di, det in enumerate(dets):
                    dc = det.centroid()
                    if dc is None:
                        continue
                    dist = float(np.hypot(tc[0] - dc[0], tc[1] - dc[1]))
                    cost[ti, di] = dist
            # Greedy match
            while True:
                ti, di = np.unravel_index(np.argmin(cost), cost.shape)
                if not np.isfinite(cost[ti, di]) or cost[ti, di] > self.match_thresh_px:
                    break
                tidx = track_indices[ti]
                if tidx in matched_t or di in matched_d:
                    cost[ti, di] = np.inf
                    continue
                self._assign(self._tracks[tidx], dets[di])
                matched_t.add(tidx)
                matched_d.add(di)
                cost[ti, :] = np.inf
                cost[:, di] = np.inf

        active = list(range(len(self._tracks)))
        associate(high, active)
        unmatched_high = [i for i in range(len(high)) if i not in matched_d]
        # Second stage: remaining tracks ↔ low-score dets
        remaining_tracks = [i for i in active if i not in matched_t]
        # Remap low match indices carefully
        low_matched: set[int] = set()
        if remaining_tracks and low:
            cost = np.full((len(remaining_tracks), len(low)), np.inf)
            for ti, tidx in enumerate(remaining_tracks):
                tc = self._tracks[tidx].centroid
                for di, det in enumerate(low):
                    dc = det.centroid()
                    if dc is None:
                        continue
                    cost[ti, di] = float(np.hypot(tc[0] - dc[0], tc[1] - dc[1]))
            while True:
                ti, di = np.unravel_index(np.argmin(cost), cost.shape)
                if not np.isfinite(cost[ti, di]) or cost[ti, di] > self.match_thresh_px:
                    break
                tidx = remaining_tracks[ti]
                if tidx in matched_t or di in low_matched:
                    cost[ti, di] = np.inf
                    continue
                self._assign(self._tracks[tidx], low[di])
                matched_t.add(tidx)
                low_matched.add(di)
                cost[ti, :] = np.inf
                cost[:, di] = np.inf

        # Birth new tracks from unmatched high-score detections
        for i in unmatched_high:
            self._spawn(high[i])

        # Drop lost tracks
        self._tracks = [
            t for t in self._tracks if t.time_since_update <= self.max_time_lost
        ]
        return [t for t in self._tracks if t.time_since_update == 0]

    def _assign(self, track: PersonTrack, det: DetectedPerson) -> None:
        track.keypoints = det.keypoints
        track.score = det.score
        track.source = det.source
        track.hits += 1
        track.time_since_update = 0
        c = det.centroid()
        if c is not None:
            track.centroid = c

    def _spawn(self, det: DetectedPerson) -> None:
        c = det.centroid() or (0.0, 0.0)
        self._tracks.append(
            PersonTrack(
                track_id=self._next_id,
                keypoints=det.keypoints,
                score=det.score,
                centroid=c,
                source=det.source,
            )
        )
        self._next_id += 1
