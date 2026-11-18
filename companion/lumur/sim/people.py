"""Animated articulated people for the simulated room.

Stick/capsule figures with known joint positions, walking trajectories,
and ground-truth ankles for footstep tests. Pose models are not run here —
see ``lumur.track`` for detectors that consume these figures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from lumur.sim.geometry import Capsule, Sphere, project_points

# MediaPipe-compatible subset used by footstep / tracking code.
JOINT_NAMES = (
    "nose",
    "left_shoulder",
    "right_shoulder",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)

# Limb connections for capsule rendering (parent, child, radius_m).
# Radii are intentionally a bit thick so low-res sim cameras actually hit them.
LIMBS: tuple[tuple[str, str, float], ...] = (
    ("left_shoulder", "right_shoulder", 0.08),
    ("left_shoulder", "left_hip", 0.09),
    ("right_shoulder", "right_hip", 0.09),
    ("left_hip", "right_hip", 0.08),
    ("left_hip", "left_knee", 0.06),
    ("left_knee", "left_ankle", 0.05),
    ("right_hip", "right_knee", 0.06),
    ("right_knee", "right_ankle", 0.05),
    ("left_shoulder", "nose", 0.05),
    ("right_shoulder", "nose", 0.05),
)

FootName = Literal["left", "right"]


@dataclass
class JointPose:
    """One named joint in world coordinates."""

    name: str
    position: np.ndarray  # (3,) metres
    visible: bool = True


@dataclass
class PersonPose3D:
    """Ground-truth pose for one simulated person at a single time."""

    person_id: int
    joints: dict[str, JointPose]
    height: float
    albedo: float = 0.32

    def ankle(self, foot: FootName) -> np.ndarray | None:
        key = f"{foot}_ankle"
        j = self.joints.get(key)
        if j is None or not j.visible:
            return None
        return j.position

    def joint_array(self) -> np.ndarray:
        """Nx3 joint positions in JOINT_NAMES order (NaN if missing)."""
        out = np.full((len(JOINT_NAMES), 3), np.nan, dtype=np.float64)
        for i, name in enumerate(JOINT_NAMES):
            j = self.joints.get(name)
            if j is not None and j.visible:
                out[i] = j.position
        return out


@dataclass
class WalkPath:
    """Polyline or closed loop trajectory on the floor (y ignored)."""

    waypoints: np.ndarray  # Mx3 or Mx2
    closed: bool = True
    speed_m_s: float = 0.9

    def __post_init__(self) -> None:
        wp = np.asarray(self.waypoints, dtype=np.float64)
        if wp.ndim != 2 or wp.shape[0] < 2:
            raise ValueError("WalkPath needs at least two waypoints")
        if wp.shape[1] == 2:
            wp = np.column_stack([wp[:, 0], np.zeros(wp.shape[0]), wp[:, 1]])
        elif wp.shape[1] != 3:
            raise ValueError("waypoints must be Mx2 or Mx3")
        self.waypoints = wp
        segs = np.linalg.norm(np.diff(wp[:, [0, 2]], axis=0), axis=1)
        if self.closed:
            segs = np.append(
                segs,
                float(np.linalg.norm(wp[0, [0, 2]] - wp[-1, [0, 2]])),
            )
        self._seg_lengths = segs
        self._total = float(segs.sum())
        if self._total < 1e-6:
            raise ValueError("WalkPath length is zero")

    @property
    def length(self) -> float:
        return self._total

    def sample(self, distance: float) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(position_xyz, forward_xz_unit)`` at arc length ``distance``."""
        d = distance % self._total if self.closed else float(
            np.clip(distance, 0.0, self._total)
        )
        acc = 0.0
        n_seg = len(self._seg_lengths)
        for i, length in enumerate(self._seg_lengths):
            if acc + length >= d - 1e-9 or i == n_seg - 1:
                t = 0.0 if length < 1e-9 else (d - acc) / length
                a = self.waypoints[i]
                b = self.waypoints[(i + 1) % len(self.waypoints)] if self.closed or i + 1 < len(
                    self.waypoints
                ) else self.waypoints[i]
                if not self.closed and i + 1 >= len(self.waypoints):
                    b = self.waypoints[i]
                pos = a + t * (b - a)
                fwd = b - a
                fwd[1] = 0.0
                nrm = np.linalg.norm(fwd[[0, 2]])
                if nrm < 1e-8:
                    fwd = np.array([0.0, 0.0, 1.0])
                else:
                    fwd = fwd / nrm
                pos = pos.copy()
                pos[1] = 0.0
                return pos, fwd
            acc += length
        pos = self.waypoints[-1].copy()
        pos[1] = 0.0
        return pos, np.array([0.0, 0.0, 1.0])


@dataclass
class AnimatedPerson:
    """One walking articulated figure driven by a floor path and gait phase."""

    person_id: int
    path: WalkPath
    height: float = 1.7
    albedo: float = 0.32
    shoulder_width: float = 0.36
    hip_width: float = 0.28
    phase_offset: float = 0.0  # radians of gait phase
    start_distance: float = 0.0
    limb_radius_scale: float = 1.0

    def pose_at(self, time_s: float) -> PersonPose3D:
        dist = self.start_distance + self.path.speed_m_s * time_s
        root, forward = self.path.sample(dist)
        right = np.array([forward[2], 0.0, -forward[0]])
        # Gait: two steps per stride length ~0.7 * height
        stride = 0.55 * self.height
        phase = self.phase_offset + 2.0 * np.pi * (dist / max(stride, 1e-3))
        return _build_pose(
            person_id=self.person_id,
            root=root,
            forward=forward,
            right=right,
            height=self.height,
            shoulder_width=self.shoulder_width,
            hip_width=self.hip_width,
            phase=phase,
            albedo=self.albedo,
        )

    def capsules_at(self, time_s: float) -> list[Capsule]:
        pose = self.pose_at(time_s)
        out: list[Capsule] = []
        for a, b, radius in LIMBS:
            ja, jb = pose.joints.get(a), pose.joints.get(b)
            if ja is None or jb is None:
                continue
            if not (ja.visible and jb.visible):
                continue
            out.append(
                Capsule(
                    a=ja.position,
                    b=jb.position,
                    radius=radius * self.limb_radius_scale,
                    albedo=self.albedo,
                    name=f"p{self.person_id}_{a}_{b}",
                )
            )
        # Head sphere as a short capsule.
        nose = pose.joints.get("nose")
        if nose is not None and nose.visible:
            top = nose.position + np.array([0.0, 0.08, 0.0])
            out.append(
                Capsule(
                    a=nose.position,
                    b=top,
                    radius=0.09 * self.limb_radius_scale,
                    albedo=self.albedo,
                    name=f"p{self.person_id}_head",
                )
            )
        return out

    def spheres_at(self, time_s: float) -> list[Sphere]:
        pose = self.pose_at(time_s)
        spheres: list[Sphere] = []
        for name, j in pose.joints.items():
            if not j.visible:
                continue
            r = 0.05 if "ankle" in name else 0.04
            spheres.append(
                Sphere(
                    center=j.position,
                    radius=r * self.limb_radius_scale,
                    albedo=self.albedo,
                    name=f"p{self.person_id}_{name}",
                )
            )
        return spheres


def _build_pose(
    *,
    person_id: int,
    root: np.ndarray,
    forward: np.ndarray,
    right: np.ndarray,
    height: float,
    shoulder_width: float,
    hip_width: float,
    phase: float,
    albedo: float,
) -> PersonPose3D:
    """Kinematic walk cycle. Ankles touch the floor near phase extrema."""
    h = height
    hip_y = 0.52 * h
    shoulder_y = 0.82 * h
    head_y = 0.95 * h

    # Swing / stance: left phase, right opposite.
    # Stance (cos(ph) > 0): foot planted, tracks a world point under the hip.
    # Swing (cos(ph) <= 0): foot lifts and advances.
    def leg(side_sign: float, ph: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        hip = root + right * side_sign * (hip_width * 0.5) + np.array([0.0, hip_y, 0.0])
        # Plant offset relative to root during stance; swing advances then lands.
        step = 0.16 * h * np.sin(ph)
        lift = 0.11 * h * max(0.0, -np.sin(ph))  # lift only on swing half
        ankle = (
            root
            + right * side_sign * (hip_width * 0.35)
            + forward * step
            + np.array([0.0, 0.015 + lift, 0.0])
        )
        knee = 0.5 * (hip + ankle) + np.array(
            [0.0, 0.05 * h * (lift / (0.11 * h + 1e-6)), 0.0]
        )
        ankle = ankle.copy()
        ankle[1] = max(0.01, float(ankle[1]))
        return hip, knee, ankle

    l_hip, l_knee, l_ankle = leg(+1.0, phase)
    r_hip, r_knee, r_ankle = leg(-1.0, phase + np.pi)

    l_sh = root + right * (shoulder_width * 0.5) + np.array([0.0, shoulder_y, 0.0])
    r_sh = root - right * (shoulder_width * 0.5) + np.array([0.0, shoulder_y, 0.0])
    nose = root + forward * (0.04 * h) + np.array([0.0, head_y, 0.0])

    joints = {
        "nose": JointPose("nose", nose),
        "left_shoulder": JointPose("left_shoulder", l_sh),
        "right_shoulder": JointPose("right_shoulder", r_sh),
        "left_hip": JointPose("left_hip", l_hip),
        "right_hip": JointPose("right_hip", r_hip),
        "left_knee": JointPose("left_knee", l_knee),
        "right_knee": JointPose("right_knee", r_knee),
        "left_ankle": JointPose("left_ankle", l_ankle),
        "right_ankle": JointPose("right_ankle", r_ankle),
    }
    return PersonPose3D(
        person_id=person_id, joints=joints, height=h, albedo=albedo
    )


@dataclass
class PeopleSim:
    """Collection of animated people with a shared clock."""

    people: list[AnimatedPerson] = field(default_factory=list)
    time_s: float = 0.0

    def advance(self, dt: float) -> None:
        self.time_s += float(dt)

    def set_time(self, time_s: float) -> None:
        self.time_s = float(time_s)

    def poses(self) -> list[PersonPose3D]:
        return [p.pose_at(self.time_s) for p in self.people]

    def capsules(self) -> list[Capsule]:
        out: list[Capsule] = []
        for p in self.people:
            out.extend(p.capsules_at(self.time_s))
        return out

    def ground_truth_joints_2d(
        self,
        K: np.ndarray,
        R: np.ndarray,
        t: np.ndarray,
        *,
        distortion: np.ndarray | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> list[dict[str, Any]]:
        """Project current 3D joints into the camera (pixel coords)."""
        records: list[dict[str, Any]] = []
        for pose in self.poses():
            names = []
            pts = []
            for name in JOINT_NAMES:
                j = pose.joints.get(name)
                if j is None:
                    continue
                names.append(name)
                pts.append(j.position)
            if not pts:
                continue
            arr = np.stack(pts, axis=0)
            u, v, depth = project_points(arr, K, R, t, distortion=distortion)
            joints_2d = {}
            for i, name in enumerate(names):
                visible = bool(
                    np.isfinite(u[i])
                    and depth[i] > 1e-6
                    and (width is None or (0 <= u[i] < width))
                    and (height is None or (0 <= v[i] < height))
                )
                joints_2d[name] = {
                    "u": float(u[i]) if np.isfinite(u[i]) else None,
                    "v": float(v[i]) if np.isfinite(v[i]) else None,
                    "depth": float(depth[i]),
                    "visible": visible,
                    "xyz": pose.joints[name].position.tolist(),
                }
            records.append(
                {
                    "person_id": pose.person_id,
                    "joints": joints_2d,
                    "time_s": self.time_s,
                }
            )
        return records


def people_from_config(cfg_list: list[dict[str, Any]]) -> PeopleSim:
    """Build a ``PeopleSim`` from scene JSON ``room.people`` entries."""
    people: list[AnimatedPerson] = []
    for i, cfg in enumerate(cfg_list):
        wp = np.asarray(cfg.get("waypoints", [[-1.0, 0.0, 0.5], [1.0, 0.0, 0.5]]))
        path = WalkPath(
            waypoints=wp,
            closed=bool(cfg.get("closed", True)),
            speed_m_s=float(cfg.get("speed_m_s", 0.9)),
        )
        people.append(
            AnimatedPerson(
                person_id=int(cfg.get("id", i + 1)),
                path=path,
                height=float(cfg.get("height", 1.7)),
                albedo=float(cfg.get("albedo", 0.32)),
                shoulder_width=float(cfg.get("shoulder_width", 0.36)),
                hip_width=float(cfg.get("hip_width", 0.28)),
                phase_offset=float(cfg.get("phase_offset", 0.0)),
                start_distance=float(cfg.get("start_distance", 0.0)),
                limb_radius_scale=float(cfg.get("limb_radius_scale", 1.0)),
            )
        )
    return PeopleSim(people=people)


def default_crossing_people(n: int = 2) -> PeopleSim:
    """1–4 walkers on crossing paths for tracker / footstep tests."""
    n = int(np.clip(n, 1, 4))
    configs: list[dict[str, Any]] = [
        {
            "id": 1,
            "waypoints": [[-1.2, 0.0, 0.4], [1.2, 0.0, 0.6]],
            "closed": True,
            "speed_m_s": 0.85,
            "phase_offset": 0.0,
            "height": 1.7,
        },
        {
            "id": 2,
            "waypoints": [[-0.9, 0.0, 1.3], [0.9, 0.0, 0.2]],
            "closed": True,
            "speed_m_s": 0.75,
            "phase_offset": 1.2,
            "height": 1.6,
            "start_distance": 0.4,
        },
        {
            "id": 3,
            "waypoints": [[1.0, 0.0, 1.2], [-1.0, 0.0, 1.0]],
            "closed": True,
            "speed_m_s": 0.7,
            "phase_offset": 2.0,
            "height": 1.65,
        },
        {
            "id": 4,
            "waypoints": [[-0.5, 0.0, 0.1], [0.5, 0.0, 1.4]],
            "closed": True,
            "speed_m_s": 0.8,
            "phase_offset": 0.5,
            "height": 1.55,
        },
    ]
    return people_from_config(configs[:n])
