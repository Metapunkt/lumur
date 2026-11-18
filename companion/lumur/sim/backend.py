"""Simulated display + camera that plug into ``CaptureLoop``."""

from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np

from lumur.capture.camera import CameraLockStatus
from lumur.sim.ground_truth import GroundTruth, compute_ground_truth
from lumur.sim.people import PeopleSim, default_crossing_people
from lumur.sim.render import RenderBuffers, render_camera_view
from lumur.sim.scene import SimScene, load_scene


class SimDisplay:
    """Pattern sink that feeds the shared ``SimRig`` projector framebuffer."""

    def __init__(self, rig: SimRig):
        self._rig = rig

    def show(self, image: np.ndarray) -> None:
        if image.dtype != np.uint8:
            raise TypeError("pattern image must be uint8")
        self._rig.set_pattern(image)

    def close(self) -> None:
        self._rig.set_pattern(None)


class SimCamera:
    """Frame source that re-renders the room under the current projector image."""

    def __init__(self, rig: SimRig):
        self._rig = rig
        self.lock_status = CameraLockStatus(
            exposure_locked=True,
            white_balance_locked=True,
            notes=["simulated camera; AE/AWB locked"],
        )

    def lock_exposure_and_wb(self) -> CameraLockStatus:
        # Sim exposure/WB are fixed by construction (ADR 0005 / REQ-001-009).
        self.lock_status = CameraLockStatus(
            exposure_locked=True,
            white_balance_locked=True,
            notes=["simulated camera; AE/AWB locked"],
        )
        return self.lock_status

    def grab(self) -> np.ndarray:
        return self._rig.render_frame()

    def release(self) -> None:
        return None


class SimRig:
    """Paired simulated projector display and webcam for the capture loop.

    ``latency_frames`` models USB webcam lag: the camera observes projector
    frame N−k while the display already shows a newer pattern. A ring buffer
    of recent renders supports predicted-frame subtraction (ADR 0005).
    """

    def __init__(
        self,
        scene: SimScene,
        *,
        latency_frames: int = 0,
        people: PeopleSim | None = None,
        frame_dt: float = 1.0 / 30.0,
        retain_color: bool = False,
    ):
        self.scene = scene
        self.latency_frames = max(0, int(latency_frames))
        self.frame_dt = float(frame_dt)
        self.retain_color = bool(retain_color)
        self._pattern: np.ndarray | None = None
        self._rng = np.random.default_rng(scene.camera.seed)
        self._ground_truth: GroundTruth | None = None
        self._pattern_ring: deque[np.ndarray | None] = deque(maxlen=64)
        self._render_ring: deque[RenderBuffers] = deque(maxlen=64)
        self.frame_index = 0
        self.time_s = 0.0
        if people is not None:
            self.scene.room.people = people
        self.display = SimDisplay(self)
        self.camera = SimCamera(self)

    @classmethod
    def from_scene_path(
        cls,
        path: str | Path,
        *,
        latency_frames: int = 0,
        n_people: int | None = None,
        **kwargs,
    ) -> SimRig:
        scene = load_scene(path)
        people = None
        if n_people is not None:
            people = default_crossing_people(n_people)
        return cls(
            scene,
            latency_frames=latency_frames,
            people=people,
            **kwargs,
        )

    @property
    def projector_size(self) -> tuple[int, int]:
        p = self.scene.projector
        return p.width, p.height

    @property
    def camera_size(self) -> tuple[int, int]:
        c = self.scene.camera
        return c.width, c.height

    @property
    def people(self) -> PeopleSim | None:
        return self.scene.room.people

    def set_people(self, people: PeopleSim | None) -> None:
        self.scene.room.people = people

    def set_pattern(self, image: np.ndarray | None) -> None:
        if image is None:
            self._pattern = None
        else:
            # Accept gray or BGR; store a copy so callers can mutate freely.
            self._pattern = np.array(image, copy=True)
        self._pattern_ring.append(
            None if self._pattern is None else np.array(self._pattern, copy=True)
        )

    def pattern_at_lag(self, lag: int | None = None) -> np.ndarray | None:
        """Projector pattern the camera would have seen ``lag`` frames ago."""
        lag = self.latency_frames if lag is None else max(0, int(lag))
        if not self._pattern_ring:
            return self._pattern
        idx = len(self._pattern_ring) - 1 - lag
        if idx < 0:
            return self._pattern_ring[0]
        return self._pattern_ring[idx]

    def advance(self, dt: float | None = None) -> None:
        """Advance simulation clock (people animation)."""
        step = self.frame_dt if dt is None else float(dt)
        self.time_s += step
        if self.people is not None:
            self.people.set_time(self.time_s)

    def render_frame(
        self,
        *,
        advance: bool = True,
        pattern: np.ndarray | None | object = ...,
        include_people: bool = True,
    ) -> np.ndarray:
        """Render a BGR webcam frame under the lag-matched projector image."""
        if advance:
            self.advance()
            self.frame_index += 1

        people = self.scene.room.people
        if not include_people:
            self.scene.room.people = None

        if pattern is ...:
            use_pattern = self.pattern_at_lag(self.latency_frames)
        else:
            use_pattern = pattern  # type: ignore[assignment]

        buffers = render_camera_view(
            self.scene.room,
            self.scene.camera,
            self.scene.projector,
            use_pattern,
            rng=self._rng,
            retain_color=self.retain_color,
        )
        self._render_ring.append(buffers)
        self.scene.room.people = people

        img = buffers.image
        if img.ndim == 2:
            return np.stack([img, img, img], axis=-1)
        # retain_color path is RGB; OpenCV cameras are BGR.
        return img[:, :, ::-1].copy()

    def render_buffers(
        self,
        *,
        pattern: np.ndarray | None | object = ...,
        include_people: bool = True,
        retain_color: bool | None = None,
    ) -> RenderBuffers:
        people = self.scene.room.people
        if not include_people:
            self.scene.room.people = None
        if pattern is ...:
            use_pattern = self.pattern_at_lag(self.latency_frames)
        else:
            use_pattern = pattern  # type: ignore[assignment]
        rc = self.retain_color if retain_color is None else retain_color
        buffers = render_camera_view(
            self.scene.room,
            self.scene.camera,
            self.scene.projector,
            use_pattern,
            rng=self._rng,
            retain_color=rc,
        )
        self.scene.room.people = people
        return buffers

    def recent_patterns(self) -> list[np.ndarray | None]:
        return list(self._pattern_ring)

    def ground_truth_joints(self) -> list[dict]:
        if self.people is None:
            return []
        cam = self.scene.camera
        return self.people.ground_truth_joints_2d(
            cam.K,
            cam.R,
            cam.t,
            distortion=cam.distortion,
            width=cam.width,
            height=cam.height,
        )

    def ground_truth(self, *, refresh: bool = False) -> GroundTruth:
        # Geometry GT without people (static room).
        people = self.scene.room.people
        self.scene.room.people = None
        if self._ground_truth is None or refresh:
            self._ground_truth = compute_ground_truth(
                self.scene.room, self.scene.camera, self.scene.projector
            )
        self.scene.room.people = people
        return self._ground_truth
