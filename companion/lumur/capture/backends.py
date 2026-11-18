"""Device backend factory: OpenCV hardware vs simulated rig."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from lumur.capture.camera import OpenCVCamera
from lumur.capture.display import OpenCVFullscreenDisplay, PatternDisplay

BackendName = Literal["opencv", "sim"]


@dataclass
class DevicePair:
    """Camera + display pair used by ``CaptureLoop`` / the CLI."""

    camera: Any  # FrameSource with optional lock_exposure_and_wb
    display: PatternDisplay
    backend: BackendName
    projector_size: tuple[int, int] | None = None
    camera_size: tuple[int, int] | None = None
    rig: Any | None = None  # SimRig when backend == "sim"

    def lock_exposure_and_wb(self):
        if hasattr(self.camera, "lock_exposure_and_wb"):
            return self.camera.lock_exposure_and_wb()
        return None

    def close(self) -> None:
        self.display.close()
        if hasattr(self.camera, "release"):
            self.camera.release()


def open_devices(
    backend: BackendName = "opencv",
    *,
    camera: int | str = 0,
    camera_width: int | None = None,
    camera_height: int | None = None,
    monitor_index: int = 1,
    scene: str | Path | None = None,
) -> DevicePair:
    """Open a camera/display pair for the requested backend.

    ``scene`` is required when ``backend == "sim"`` (file path or preset name).
    """
    if backend == "opencv":
        cam = OpenCVCamera(camera, width=camera_width, height=camera_height)
        display = OpenCVFullscreenDisplay(monitor_index=monitor_index)
        return DevicePair(camera=cam, display=display, backend="opencv")

    if backend == "sim":
        if scene is None:
            raise ValueError("--scene is required when --backend sim")
        from lumur.sim.backend import SimRig

        rig = SimRig.from_scene_path(scene)
        return DevicePair(
            camera=rig.camera,
            display=rig.display,
            backend="sim",
            projector_size=rig.projector_size,
            camera_size=rig.camera_size,
            rig=rig,
        )

    raise ValueError(f"unknown backend {backend!r}")
