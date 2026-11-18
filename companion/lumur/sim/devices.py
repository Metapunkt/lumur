"""Virtual projector and webcam specifications."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from lumur.sim.geometry import device_center, make_look_at, pinhole_K


@dataclass
class VirtualProjector:
    """Idealised projector treated as an inverse camera with gamma."""

    width: int
    height: int
    K: np.ndarray
    R: np.ndarray  # world → projector
    t: np.ndarray
    gamma: float = 2.2

    @property
    def center(self) -> np.ndarray:
        return device_center(self.R, self.t)

    @classmethod
    def from_look_at(
        cls,
        width: int,
        height: int,
        eye: np.ndarray,
        target: np.ndarray,
        *,
        fov_y_deg: float = 40.0,
        up: np.ndarray | None = None,
        gamma: float = 2.2,
        K: np.ndarray | None = None,
    ) -> VirtualProjector:
        R, t = make_look_at(eye, target, up=up)
        matrix = pinhole_K(width, height, fov_y_deg) if K is None else np.asarray(K)
        return cls(width=width, height=height, K=matrix, R=R, t=t, gamma=gamma)

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "K": self.K.tolist(),
            "R": self.R.tolist(),
            "t": self.t.tolist(),
            "gamma": self.gamma,
            "center": self.center.tolist(),
        }


@dataclass
class VirtualCamera:
    """Webcam with optional Brown–Conrady distortion and sensor effects."""

    width: int
    height: int
    K: np.ndarray
    R: np.ndarray  # world → camera
    t: np.ndarray
    distortion: np.ndarray = field(
        default_factory=lambda: np.zeros(5, dtype=np.float64)
    )
    exposure: float = 1.0
    noise_std: float = 0.0
    ambient: float = 0.0  # additive gray level before exposure
    blur_sigma: float = 0.0
    seed: int = 0

    @property
    def center(self) -> np.ndarray:
        return device_center(self.R, self.t)

    @classmethod
    def from_look_at(
        cls,
        width: int,
        height: int,
        eye: np.ndarray,
        target: np.ndarray,
        *,
        fov_y_deg: float = 55.0,
        up: np.ndarray | None = None,
        distortion: np.ndarray | None = None,
        exposure: float = 1.0,
        noise_std: float = 0.0,
        ambient: float = 0.0,
        blur_sigma: float = 0.0,
        seed: int = 0,
        K: np.ndarray | None = None,
    ) -> VirtualCamera:
        R, t = make_look_at(eye, target, up=up)
        matrix = pinhole_K(width, height, fov_y_deg) if K is None else np.asarray(K)
        dist = (
            np.zeros(5, dtype=np.float64)
            if distortion is None
            else np.asarray(distortion, dtype=np.float64).reshape(-1)
        )
        return cls(
            width=width,
            height=height,
            K=matrix,
            R=R,
            t=t,
            distortion=dist,
            exposure=exposure,
            noise_std=noise_std,
            ambient=ambient,
            blur_sigma=blur_sigma,
            seed=seed,
        )

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "K": self.K.tolist(),
            "R": self.R.tolist(),
            "t": self.t.tolist(),
            "distortion": self.distortion.reshape(-1).tolist(),
            "exposure": self.exposure,
            "noise_std": self.noise_std,
            "ambient": self.ambient,
            "blur_sigma": self.blur_sigma,
            "seed": self.seed,
            "center": self.center.tolist(),
        }


def stereo_camera_to_projector(
    camera: VirtualCamera, projector: VirtualProjector
) -> tuple[np.ndarray, np.ndarray]:
    """Return (R, T) transforming a point from camera coords to projector coords."""
    R = projector.R @ camera.R.T
    T = projector.t - R @ camera.t
    return R, T
