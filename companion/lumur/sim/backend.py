"""Simulated display + camera that plug into ``CaptureLoop``."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lumur.capture.camera import CameraLockStatus
from lumur.sim.ground_truth import GroundTruth, compute_ground_truth
from lumur.sim.render import render_camera_view
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
            notes=["simulated camera"],
        )

    def lock_exposure_and_wb(self) -> CameraLockStatus:
        return self.lock_status

    def grab(self) -> np.ndarray:
        return self._rig.render_frame()

    def release(self) -> None:
        return None


class SimRig:
    """Paired simulated projector display and webcam for the capture loop."""

    def __init__(self, scene: SimScene):
        self.scene = scene
        self._pattern: np.ndarray | None = None
        self._rng = np.random.default_rng(scene.camera.seed)
        self._ground_truth: GroundTruth | None = None
        self.display = SimDisplay(self)
        self.camera = SimCamera(self)

    @classmethod
    def from_scene_path(cls, path: str | Path) -> SimRig:
        return cls(load_scene(path))

    @property
    def projector_size(self) -> tuple[int, int]:
        p = self.scene.projector
        return p.width, p.height

    @property
    def camera_size(self) -> tuple[int, int]:
        c = self.scene.camera
        return c.width, c.height

    def set_pattern(self, image: np.ndarray | None) -> None:
        if image is None:
            self._pattern = None
            return
        # Accept gray or BGR; store a copy so callers can mutate freely.
        self._pattern = np.array(image, copy=True)

    def render_frame(self) -> np.ndarray:
        buffers = render_camera_view(
            self.scene.room,
            self.scene.camera,
            self.scene.projector,
            self._pattern,
            rng=self._rng,
        )
        # OpenCV cameras return BGR; keep a 3-channel frame for drop-in use.
        gray = buffers.image
        return np.stack([gray, gray, gray], axis=-1)

    def ground_truth(self, *, refresh: bool = False) -> GroundTruth:
        if self._ground_truth is None or refresh:
            self._ground_truth = compute_ground_truth(
                self.scene.room, self.scene.camera, self.scene.projector
            )
        return self._ground_truth
