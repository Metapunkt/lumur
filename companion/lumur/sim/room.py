"""Virtual room: floor, walls, boxes, occupants, and animated people."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from lumur.sim.geometry import (
    Box,
    Capsule,
    OccupantPlaceholder,
    Plane,
    Sphere,
    intersect_rays_box,
    intersect_rays_capsule,
    intersect_rays_plane,
    intersect_rays_sphere,
)

if TYPE_CHECKING:
    from lumur.sim.people import PeopleSim


@dataclass
class Room:
    """Collection of diffuse surfaces that can receive projected light."""

    planes: list[Plane] = field(default_factory=list)
    boxes: list[Box] = field(default_factory=list)
    occupants: list[OccupantPlaceholder] = field(default_factory=list)
    capsules: list[Capsule] = field(default_factory=list)
    spheres: list[Sphere] = field(default_factory=list)
    people: PeopleSim | None = None

    def all_boxes(self) -> list[Box]:
        boxes = list(self.boxes)
        boxes.extend(o.as_box() for o in self.occupants)
        return boxes

    def all_capsules(self) -> list[Capsule]:
        caps = list(self.capsules)
        if self.people is not None:
            caps.extend(self.people.capsules())
        return caps

    def all_spheres(self) -> list[Sphere]:
        return list(self.spheres)

    def intersect(
        self, origins: np.ndarray, directions: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Nearest hit for each ray.

        Returns ``(points Nx3, albedo N, t N)``. Misses have NaN points,
        albedo 0, and ``t = inf``.
        """
        n = origins.shape[0]
        best_t = np.full(n, np.inf, dtype=np.float64)
        best_points = np.full((n, 3), np.nan, dtype=np.float64)
        best_albedo = np.zeros(n, dtype=np.float64)

        for plane in self.planes:
            pts, t = intersect_rays_plane(origins, directions, plane)
            closer = t < best_t
            best_t = np.where(closer, t, best_t)
            best_points = np.where(closer[:, None], pts, best_points)
            best_albedo = np.where(closer, plane.albedo, best_albedo)

        for box in self.all_boxes():
            pts, t = intersect_rays_box(origins, directions, box)
            closer = t < best_t
            best_t = np.where(closer, t, best_t)
            best_points = np.where(closer[:, None], pts, best_points)
            best_albedo = np.where(closer, box.albedo, best_albedo)

        for capsule in self.all_capsules():
            pts, t = intersect_rays_capsule(origins, directions, capsule)
            closer = t < best_t
            best_t = np.where(closer, t, best_t)
            best_points = np.where(closer[:, None], pts, best_points)
            best_albedo = np.where(closer, capsule.albedo, best_albedo)

        for sphere in self.all_spheres():
            pts, t = intersect_rays_sphere(origins, directions, sphere)
            closer = t < best_t
            best_t = np.where(closer, t, best_t)
            best_points = np.where(closer[:, None], pts, best_points)
            best_albedo = np.where(closer, sphere.albedo, best_albedo)

        return best_points, best_albedo, best_t


def make_axis_room(
    *,
    width: float = 4.0,
    depth: float = 4.0,
    height: float = 2.5,
    floor_albedo: float = 0.65,
    wall_albedo: float = 0.8,
    include_ceiling: bool = False,
    include_side_walls: bool = True,
) -> Room:
    """Axis-aligned room with floor at y=0 and back wall at z=+depth/2.

    Origin is at floor centre. Camera/projector typically sit near
    ``z = -depth/2`` looking toward +Z.
    """
    half_w = width * 0.5
    half_d = depth * 0.5
    planes = [
        Plane.from_point_normal(
            np.array([0.0, 0.0, 0.0]),
            np.array([0.0, 1.0, 0.0]),
            albedo=floor_albedo,
            name="floor",
        ),
        Plane.from_point_normal(
            np.array([0.0, 0.0, half_d]),
            np.array([0.0, 0.0, -1.0]),
            albedo=wall_albedo,
            name="back_wall",
        ),
    ]
    if include_side_walls:
        planes.append(
            Plane.from_point_normal(
                np.array([-half_w, 0.0, 0.0]),
                np.array([1.0, 0.0, 0.0]),
                albedo=wall_albedo,
                name="left_wall",
            )
        )
        planes.append(
            Plane.from_point_normal(
                np.array([half_w, 0.0, 0.0]),
                np.array([-1.0, 0.0, 0.0]),
                albedo=wall_albedo,
                name="right_wall",
            )
        )
    if include_ceiling:
        planes.append(
            Plane.from_point_normal(
                np.array([0.0, height, 0.0]),
                np.array([0.0, -1.0, 0.0]),
                albedo=wall_albedo * 0.9,
                name="ceiling",
            )
        )
    return Room(planes=planes)
