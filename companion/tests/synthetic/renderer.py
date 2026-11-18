"""Headless virtual camera / projector for synthetic calibration tests."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.capture.loop import CapturedFrame
from lumur.decode.graycode import CorrespondenceMap
from lumur.patterns.graycode import GrayCodeSequence


@dataclass(frozen=True)
class PinholeDevice:
    """A virtual pinhole camera or projector in a shared world frame."""

    width: int
    height: int
    K: np.ndarray  # 3x3
    R: np.ndarray  # 3x3 world→device
    t: np.ndarray  # (3,) world→device


@dataclass(frozen=True)
class Plane:
    """Plane ``normal·X + d = 0`` in world coordinates (normal unit length)."""

    normal: np.ndarray
    d: float


def make_look_at(
    eye: np.ndarray,
    target: np.ndarray,
    up: np.ndarray = np.array([0.0, 1.0, 0.0]),
) -> tuple[np.ndarray, np.ndarray]:
    """Return (R, t) for world→device with optical axis toward ``target``."""
    forward = target - eye
    forward = forward / np.linalg.norm(forward)
    # Device looks along +Z in OpenCV convention after R.
    z = forward
    x = np.cross(z, up)
    if np.linalg.norm(x) < 1e-8:
        x = np.cross(z, np.array([1.0, 0.0, 0.0]))
    x = x / np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.stack([x, y, z], axis=0)
    t = -R @ eye
    return R, t


def pinhole_K(width: int, height: int, fov_y_deg: float = 50.0) -> np.ndarray:
    f = 0.5 * height / np.tan(np.deg2rad(fov_y_deg) / 2.0)
    return np.array(
        [[f, 0, width / 2.0], [0, f, height / 2.0], [0, 0, 1.0]], dtype=np.float64
    )


def intersect_ray_plane(
    origin: np.ndarray, direction: np.ndarray, plane: Plane
) -> np.ndarray | None:
    denom = float(plane.normal @ direction)
    if abs(denom) < 1e-10:
        return None
    t = -float(plane.normal @ origin + plane.d) / denom
    if t <= 0:
        return None
    return origin + t * direction


def device_center(device: PinholeDevice) -> np.ndarray:
    return -device.R.T @ device.t


def project_point(device: PinholeDevice, X: np.ndarray) -> tuple[float, float, float] | None:
    Xd = device.R @ X + device.t
    if Xd[2] <= 1e-8:
        return None
    uvw = device.K @ Xd
    return float(uvw[0] / uvw[2]), float(uvw[1] / uvw[2]), float(Xd[2])


def ground_truth_correspondence(
    camera: PinholeDevice,
    projector: PinholeDevice,
    plane: Plane,
) -> CorrespondenceMap:
    """Exact camera→projector map by ray-plane intersection."""
    h, w = camera.height, camera.width
    proj_u = np.full((h, w), -1.0, dtype=np.float32)
    proj_v = np.full((h, w), -1.0, dtype=np.float32)
    valid = np.zeros((h, w), dtype=bool)
    C = device_center(camera)
    Kinv = np.linalg.inv(camera.K)

    for v in range(h):
        for u in range(w):
            ray_cam = Kinv @ np.array([u + 0.5, v + 0.5, 1.0])
            direction = camera.R.T @ ray_cam
            direction = direction / np.linalg.norm(direction)
            X = intersect_ray_plane(C, direction, plane)
            if X is None:
                continue
            projected = project_point(projector, X)
            if projected is None:
                continue
            pu, pv, _ = projected
            if 0 <= pu < projector.width and 0 <= pv < projector.height:
                proj_u[v, u] = pu
                proj_v[v, u] = pv
                valid[v, u] = True

    confidence = valid.astype(np.float32)
    return CorrespondenceMap(
        proj_u=proj_u, proj_v=proj_v, confidence=confidence, valid=valid
    )


def render_pattern_from_correspondence(
    pattern: np.ndarray,
    corr: CorrespondenceMap,
    *,
    noise_std: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Sample a projector pattern into the camera image via ``corr``."""
    h, w = corr.shape
    out = np.zeros((h, w), dtype=np.float32)
    ys, xs = np.where(corr.valid)
    pu = np.clip(np.rint(corr.proj_u[ys, xs]).astype(int), 0, pattern.shape[1] - 1)
    pv = np.clip(np.rint(corr.proj_v[ys, xs]).astype(int), 0, pattern.shape[0] - 1)
    out[ys, xs] = pattern[pv, pu].astype(np.float32)
    if noise_std > 0:
        rng = rng or np.random.default_rng(0)
        out += rng.normal(0.0, noise_std, size=out.shape).astype(np.float32)
    return np.clip(out, 0, 255).astype(np.uint8)


def synthetic_captures(
    sequence: GrayCodeSequence,
    corr: CorrespondenceMap,
    *,
    noise_std: float = 0.0,
    seed: int = 0,
) -> list[CapturedFrame]:
    rng = np.random.default_rng(seed)
    captures: list[CapturedFrame] = []
    for frame in sequence.frames:
        image = render_pattern_from_correspondence(
            frame.image, corr, noise_std=noise_std, rng=rng
        )
        pattern_id = f"{frame.axis}{frame.bit}{'i' if frame.inverted else ''}"
        captures.append(CapturedFrame(pattern=frame, image=image, pattern_id=pattern_id))
    return captures


def default_scene(
    camera_size: tuple[int, int] = (160, 120),
    projector_size: tuple[int, int] = (128, 96),
) -> tuple[PinholeDevice, PinholeDevice, Plane]:
    """A small, deterministic camera–projector–plane setup for tests."""
    cam_w, cam_h = camera_size
    proj_w, proj_h = projector_size

    plane = Plane(normal=np.array([0.0, 0.0, 1.0]), d=-2.0)  # z = 2

    cam_R, cam_t = make_look_at(
        eye=np.array([0.0, 0.0, 0.0]),
        target=np.array([0.0, 0.0, 2.0]),
        up=np.array([0.0, -1.0, 0.0]),
    )
    camera = PinholeDevice(
        width=cam_w,
        height=cam_h,
        K=pinhole_K(cam_w, cam_h, fov_y_deg=45.0),
        R=cam_R,
        t=cam_t,
    )

    proj_R, proj_t = make_look_at(
        eye=np.array([0.35, 0.05, 0.1]),
        target=np.array([0.0, 0.0, 2.0]),
        up=np.array([0.0, -1.0, 0.0]),
    )
    projector = PinholeDevice(
        width=proj_w,
        height=proj_h,
        K=pinhole_K(proj_w, proj_h, fov_y_deg=40.0),
        R=proj_R,
        t=proj_t,
    )
    return camera, projector, plane