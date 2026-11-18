"""Ground-truth buffers and stereo extrinsics for the simulated rig."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.decode.graycode import CorrespondenceMap
from lumur.sim.devices import VirtualCamera, VirtualProjector, stereo_camera_to_projector
from lumur.sim.render import RenderBuffers, render_camera_view
from lumur.sim.room import Room


@dataclass
class GroundTruth:
    """True device parameters plus dense depth / correspondence."""

    camera: VirtualCamera
    projector: VirtualProjector
    depth: np.ndarray
    correspondence: CorrespondenceMap
    stereo_R: np.ndarray
    stereo_T: np.ndarray
    albedo: np.ndarray

    def to_dict(self) -> dict:
        return {
            "camera": self.camera.to_dict(),
            "projector": self.projector.to_dict(),
            "stereo_R": self.stereo_R.tolist(),
            "stereo_T": self.stereo_T.tolist(),
            "valid_fraction": self.correspondence.valid_fraction,
        }


def buffers_to_correspondence(buffers: RenderBuffers) -> CorrespondenceMap:
    return CorrespondenceMap(
        proj_u=buffers.proj_u.astype(np.float32),
        proj_v=buffers.proj_v.astype(np.float32),
        confidence=buffers.valid_proj.astype(np.float32),
        valid=buffers.valid_proj.copy(),
    )


def compute_ground_truth(
    room: Room,
    camera: VirtualCamera,
    projector: VirtualProjector,
) -> GroundTruth:
    """Ray-cast the room with the projector off to obtain geometry GT."""
    buffers = render_camera_view(room, camera, projector, pattern=None)
    R, T = stereo_camera_to_projector(camera, projector)
    return GroundTruth(
        camera=camera,
        projector=projector,
        depth=buffers.depth,
        correspondence=buffers_to_correspondence(buffers),
        stereo_R=R,
        stereo_T=T,
        albedo=buffers.albedo,
    )


def measure_floor_span_pixels(
    ground_truth: GroundTruth,
    world_a: np.ndarray,
    world_b: np.ndarray,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    """Project two world points into the camera for measured-distance tests.

    Returns ``(point_a_uv, point_b_uv, distance_m)``.
    """
    from lumur.sim.geometry import project_points

    cam = ground_truth.camera
    pts = np.stack([world_a, world_b], axis=0)
    u, v, depth = project_points(
        pts, cam.K, cam.R, cam.t, distortion=cam.distortion
    )
    if not (np.isfinite(u).all() and depth.min() > 0):
        raise ValueError("world points do not project into the camera")
    dist = float(np.linalg.norm(np.asarray(world_a) - np.asarray(world_b)))
    return (float(u[0]), float(v[0])), (float(u[1]), float(v[1])), dist
