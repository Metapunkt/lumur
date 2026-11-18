"""Ankle→floor intersection and footfall event detection (ADR 0005 / 0006)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from lumur.sim.geometry import Plane, intersect_rays_plane
from lumur.track.tracker import PersonTrack

FootName = Literal["left", "right"]


@dataclass
class FootstepEvent:
    """Room-runtime input event: a foot contacted the floor."""

    person_id: int
    foot: FootName
    position_room: tuple[float, float, float]
    position_floor: tuple[float, float]
    timestamp: float
    confidence: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "footstep",
            "person_id": int(self.person_id),
            "foot": self.foot,
            "position_room": [
                float(self.position_room[0]),
                float(self.position_room[1]),
                float(self.position_room[2]),
            ],
            "position_floor": [
                float(self.position_floor[0]),
                float(self.position_floor[1]),
            ],
            "timestamp": float(self.timestamp),
            "confidence": float(self.confidence),
        }


@dataclass
class _FootState:
    last_pos: np.ndarray | None = None
    last_t: float | None = None
    in_contact: bool = False
    last_emit_t: float = -1e9
    velocity: float = 0.0


@dataclass
class FootstepDetector:
    """Ray-cast ankles onto the floor plane; emit events on contact heuristics.

    Contact when vertical-ish speed (floor-plane tangential speed) drops below
    ``velocity_thresh`` after having been moving, with a refractory period.
    """

    floor_plane: Plane
    camera_K: np.ndarray
    camera_R: np.ndarray
    camera_t: np.ndarray
    camera_distortion: np.ndarray | None = None
    camera_center: np.ndarray | None = None
    # Floor surface coordinates: origin + axes in world (XZ by default).
    floor_origin: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float64)
    )
    floor_u_axis: np.ndarray = field(
        default_factory=lambda: np.array([1.0, 0.0, 0.0])
    )
    floor_v_axis: np.ndarray = field(
        default_factory=lambda: np.array([0.0, 0.0, 1.0])
    )
    velocity_thresh: float = 0.55  # m/s tangential
    refractory_s: float = 0.30
    max_ankle_height: float = 0.06  # metres above plane
    _state: dict[tuple[int, FootName], _FootState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.camera_center is None:
            from lumur.sim.geometry import device_center

            self.camera_center = device_center(self.camera_R, self.camera_t)
        self.floor_origin = np.asarray(self.floor_origin, dtype=np.float64)
        self.floor_u_axis = np.asarray(self.floor_u_axis, dtype=np.float64)
        self.floor_v_axis = np.asarray(self.floor_v_axis, dtype=np.float64)
        self.floor_u_axis = self.floor_u_axis / (
            np.linalg.norm(self.floor_u_axis) + 1e-12
        )
        self.floor_v_axis = self.floor_v_axis / (
            np.linalg.norm(self.floor_v_axis) + 1e-12
        )

    @classmethod
    def from_room_package(
        cls,
        room_doc: dict[str, Any],
        *,
        camera_K: np.ndarray,
        camera_R: np.ndarray,
        camera_t: np.ndarray,
        camera_distortion: np.ndarray | None = None,
        **kwargs: Any,
    ) -> FootstepDetector:
        """Build from ``lumur.room`` plane list (camera coordinate frame)."""
        floor_id = room_doc.get("floor_plane_id")
        planes = room_doc.get("planes", [])
        floor = None
        for p in planes:
            if floor_id is not None and int(p.get("plane_id", -1)) == int(floor_id):
                floor = p
                break
            if p.get("kind") == "floor" or p.get("label") == "floor":
                floor = p
                break
        if floor is None:
            # Fallback: world y=0 expressed in camera frame is unknown —
            # use an axis floor in camera coords from calibration stereo if needed.
            raise ValueError("room package has no floor plane")
        # Plane stored as camera-frame normal + d (point normal form).
        n = np.asarray(floor["normal"], dtype=np.float64)
        # Prefer point+normal if present.
        if "point" in floor:
            plane = Plane.from_point_normal(
                np.asarray(floor["point"], dtype=np.float64), n, name="floor"
            )
        else:
            d = float(floor.get("d", 0.0))
            plane = Plane(normal=n / np.linalg.norm(n), d=d, name="floor")
        return cls(
            floor_plane=plane,
            camera_K=np.asarray(camera_K, dtype=np.float64),
            camera_R=np.asarray(camera_R, dtype=np.float64),
            camera_t=np.asarray(camera_t, dtype=np.float64),
            camera_distortion=camera_distortion,
            **kwargs,
        )

    @classmethod
    def from_sim(
        cls,
        floor_plane: Plane,
        camera,
        **kwargs: Any,
    ) -> FootstepDetector:
        return cls(
            floor_plane=floor_plane,
            camera_K=camera.K,
            camera_R=camera.R,
            camera_t=camera.t,
            camera_distortion=camera.distortion,
            camera_center=camera.center,
            **kwargs,
        )

    def floor_uv(self, point: np.ndarray) -> tuple[float, float]:
        rel = np.asarray(point, dtype=np.float64) - self.floor_origin
        return float(rel @ self.floor_u_axis), float(rel @ self.floor_v_axis)

    def ankle_to_floor(
        self, u: float, v: float
    ) -> tuple[np.ndarray, float] | None:
        """Cast a ray through pixel (u,v) and intersect the floor plane."""
        # Build a single pixel ray via the same undistort path as the sim.
        # Approximate with a 1x1 grid at the fractional pixel by using
        # neighbouring integer math: project direction from K.
        import cv2

        K = self.camera_K
        dist = self.camera_distortion
        pt = np.array([[[u, v]]], dtype=np.float64)
        if dist is not None and np.any(np.asarray(dist) != 0):
            undist = cv2.undistortPoints(
                pt, K, np.asarray(dist, dtype=np.float64).reshape(-1)
            ).reshape(2)
            xn, yn = float(undist[0]), float(undist[1])
        else:
            xn = (u - K[0, 2]) / K[0, 0]
            yn = (v - K[1, 2]) / K[1, 1]
        dir_cam = np.array([xn, yn, 1.0], dtype=np.float64)
        dir_cam /= np.linalg.norm(dir_cam)
        dir_world = self.camera_R.T @ dir_cam
        origin = np.asarray(self.camera_center, dtype=np.float64).reshape(1, 3)
        direction = dir_world.reshape(1, 3)
        pts, t = intersect_rays_plane(origin, direction, self.floor_plane)
        if not np.isfinite(t[0]):
            return None
        return pts[0], float(t[0])

    def update(
        self, tracks: list[PersonTrack], timestamp: float
    ) -> list[FootstepEvent]:
        events: list[FootstepEvent] = []
        for track in tracks:
            for foot in ("left", "right"):
                kp = track.ankle(foot)
                if kp is None or not kp.visible:
                    continue
                hit = self.ankle_to_floor(kp.u, kp.v)
                if hit is None:
                    continue
                pos, _ = hit
                # Height above plane.
                height = float(
                    self.floor_plane.normal @ pos + self.floor_plane.d
                )
                if abs(height) > self.max_ankle_height and height > self.max_ankle_height:
                    # Still track velocity but don't contact.
                    pass
                key = (track.track_id, foot)  # type: ignore[arg-type]
                st = self._state.setdefault(key, _FootState())
                if st.last_pos is not None and st.last_t is not None:
                    dt = max(1e-3, timestamp - st.last_t)
                    st.velocity = float(np.linalg.norm(pos - st.last_pos) / dt)
                else:
                    st.velocity = 0.0

                near_floor = abs(height) <= self.max_ankle_height
                slow = st.velocity <= self.velocity_thresh
                contact_now = near_floor and slow
                if (
                    contact_now
                    and not st.in_contact
                    and (timestamp - st.last_emit_t) >= self.refractory_s
                ):
                    uv = self.floor_uv(pos)
                    events.append(
                        FootstepEvent(
                            person_id=track.track_id,
                            foot=foot,  # type: ignore[arg-type]
                            position_room=(
                                float(pos[0]),
                                float(pos[1]),
                                float(pos[2]),
                            ),
                            position_floor=uv,
                            timestamp=float(timestamp),
                            confidence=float(kp.confidence),
                        )
                    )
                    st.last_emit_t = timestamp
                st.in_contact = contact_now
                st.last_pos = pos
                st.last_t = timestamp
        return events


def plane_from_world_y0_in_camera(camera_R: np.ndarray, camera_t: np.ndarray) -> Plane:
    """Floor y=0 in world, expressed as a plane in world coords (sim default)."""
    return Plane.from_point_normal(
        np.array([0.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0]), name="floor"
    )
