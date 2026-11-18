"""Pluggable pose detectors. Pose always runs on the raw camera frame.

Default real backends (MediaPipe / YOLO-pose) are optional dependencies.
Sim tests use ``OraclePoseDetector``, which projects ground-truth joints and
can inject false detections on projected content so the subtraction mask is
genuinely exercised (ADR 0005).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

import numpy as np

from lumur.sim.people import JOINT_NAMES

FootName = Literal["left", "right"]


@dataclass
class Keypoint:
    name: str
    u: float
    v: float
    confidence: float = 1.0
    visible: bool = True


@dataclass
class DetectedPerson:
    """One pose detection before tracking assigns a stable id."""

    keypoints: dict[str, Keypoint]
    score: float = 1.0
    # Optional hint from oracle / injector
    source: str = "detector"
    raw_id: int | None = None

    def ankle(self, foot: FootName) -> Keypoint | None:
        return self.keypoints.get(f"{foot}_ankle")

    def bbox(self) -> tuple[float, float, float, float] | None:
        us = [k.u for k in self.keypoints.values() if k.visible]
        vs = [k.v for k in self.keypoints.values() if k.visible]
        if not us:
            return None
        return min(us), min(vs), max(us), max(vs)

    def centroid(self) -> tuple[float, float] | None:
        box = self.bbox()
        if box is None:
            return None
        return 0.5 * (box[0] + box[2]), 0.5 * (box[1] + box[3])


@runtime_checkable
class PoseDetector(Protocol):
    def detect(self, frame_bgr: np.ndarray) -> list[DetectedPerson]:
        """Run on the unmodified webcam frame (never on a subtracted image)."""


@dataclass
class OraclePoseDetector:
    """Deterministic sim detector: project figure joints + optional noise.

    ``inject_false_on_projected`` places extra silhouette detections at
    given UV locations (e.g. a painted human on the wall) so subtraction
    filtering can be tested.
    """

    joint_records_fn: Any  # () -> list[dict] ground-truth from PeopleSim
    noise_std_px: float = 0.0
    seed: int = 0
    detection_dropout: float = 0.0
    false_detections: list[dict[str, Any]] = field(default_factory=list)
    _rng: np.random.Generator = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)

    def inject_false_person(
        self,
        *,
        u: float,
        v: float,
        scale: float = 20.0,
        label: str = "projected_silhouette",
    ) -> None:
        """Queue a fake person whose ankles/torso sit on projected content."""
        self.false_detections.append(
            {"u": float(u), "v": float(v), "scale": float(scale), "label": label}
        )

    def clear_false_detections(self) -> None:
        self.false_detections.clear()

    def detect(self, frame_bgr: np.ndarray) -> list[DetectedPerson]:
        del frame_bgr  # oracle ignores pixels; uses sim GT
        people: list[DetectedPerson] = []
        for rec in self.joint_records_fn():
            if self.detection_dropout > 0 and self._rng.random() < self.detection_dropout:
                continue
            kps: dict[str, Keypoint] = {}
            for name in JOINT_NAMES:
                j = rec["joints"].get(name)
                if j is None or not j.get("visible") or j.get("u") is None:
                    continue
                u = float(j["u"])
                v = float(j["v"])
                if self.noise_std_px > 0:
                    u += float(self._rng.normal(0, self.noise_std_px))
                    v += float(self._rng.normal(0, self.noise_std_px))
                kps[name] = Keypoint(name=name, u=u, v=v, confidence=0.99)
            if len(kps) < 3:
                continue
            people.append(
                DetectedPerson(
                    keypoints=kps,
                    score=0.99,
                    source="oracle",
                    raw_id=int(rec["person_id"]),
                )
            )
        for fake in self.false_detections:
            people.append(self._fake_person(fake))
        return people

    def _fake_person(self, fake: dict[str, Any]) -> DetectedPerson:
        u0, v0, s = fake["u"], fake["v"], fake["scale"]
        # Stick figure in image space — intentionally on the wall projection.
        offsets = {
            "nose": (0.0, -1.6),
            "left_shoulder": (-0.4, -1.0),
            "right_shoulder": (0.4, -1.0),
            "left_hip": (-0.3, 0.0),
            "right_hip": (0.3, 0.0),
            "left_knee": (-0.3, 0.7),
            "right_knee": (0.3, 0.7),
            "left_ankle": (-0.3, 1.4),
            "right_ankle": (0.3, 1.4),
        }
        kps = {
            name: Keypoint(name=name, u=u0 + ox * s, v=v0 + oy * s, confidence=0.85)
            for name, (ox, oy) in offsets.items()
        }
        return DetectedPerson(
            keypoints=kps, score=0.85, source=str(fake.get("label", "injected"))
        )


class MediaPipePoseDetector:
    """Optional MediaPipe Pose backend. Requires ``mediapipe`` installed."""

    def __init__(self, **kwargs: Any):
        try:
            import mediapipe as mp  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "MediaPipe is an optional dependency. Install mediapipe or use "
                "OraclePoseDetector / create_pose_detector('oracle')."
            ) from exc
        self._mp = mp
        self._pose = mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=int(kwargs.get("model_complexity", 0)),
            enable_segmentation=False,
        )
        self._name_map = {
            0: "nose",
            11: "left_shoulder",
            12: "right_shoulder",
            23: "left_hip",
            24: "right_hip",
            25: "left_knee",
            26: "right_knee",
            27: "left_ankle",
            28: "right_ankle",
        }

    def detect(self, frame_bgr: np.ndarray) -> list[DetectedPerson]:
        import cv2

        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return []
        kps: dict[str, Keypoint] = {}
        for idx, name in self._name_map.items():
            lm = result.pose_landmarks.landmark[idx]
            kps[name] = Keypoint(
                name=name,
                u=lm.x * w,
                v=lm.y * h,
                confidence=float(lm.visibility),
                visible=lm.visibility > 0.5,
            )
        return [DetectedPerson(keypoints=kps, score=0.9, source="mediapipe")]


class YoloPoseDetector:
    """Optional YOLO-pose backend. Requires ``ultralytics`` installed."""

    def __init__(self, model_name: str = "yolov8n-pose.pt", **kwargs: Any):
        try:
            from ultralytics import YOLO  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "ultralytics is an optional dependency. Install it or use "
                "OraclePoseDetector / create_pose_detector('oracle')."
            ) from exc
        self._model = YOLO(model_name)
        # COCO pose indices used by YOLOv8-pose
        self._names = {
            0: "nose",
            5: "left_shoulder",
            6: "right_shoulder",
            11: "left_hip",
            12: "right_hip",
            13: "left_knee",
            14: "right_knee",
            15: "left_ankle",
            16: "right_ankle",
        }
        self._kwargs = kwargs

    def detect(self, frame_bgr: np.ndarray) -> list[DetectedPerson]:
        results = self._model.predict(frame_bgr, verbose=False, **self._kwargs)
        people: list[DetectedPerson] = []
        if not results:
            return people
        r0 = results[0]
        if r0.keypoints is None:
            return people
        xy = r0.keypoints.xy.cpu().numpy()
        conf = r0.keypoints.conf.cpu().numpy() if r0.keypoints.conf is not None else None
        for pi in range(xy.shape[0]):
            kps: dict[str, Keypoint] = {}
            for idx, name in self._names.items():
                u, v = float(xy[pi, idx, 0]), float(xy[pi, idx, 1])
                c = float(conf[pi, idx]) if conf is not None else 1.0
                if u <= 1 and v <= 1 and (u + v) < 1e-3:
                    continue
                kps[name] = Keypoint(name=name, u=u, v=v, confidence=c, visible=c > 0.3)
            if kps:
                people.append(
                    DetectedPerson(keypoints=kps, score=0.9, source="yolo_pose")
                )
        return people


def create_pose_detector(
    backend: str = "oracle",
    **kwargs: Any,
) -> PoseDetector:
    """Factory. ``oracle`` needs ``joint_records_fn``. Real backends optional."""
    backend = backend.lower().strip()
    if backend in ("oracle", "sim"):
        if "joint_records_fn" not in kwargs:
            raise ValueError("oracle backend requires joint_records_fn=")
        return OraclePoseDetector(**kwargs)
    if backend in ("mediapipe", "mp"):
        return MediaPipePoseDetector(**kwargs)
    if backend in ("yolo", "yolo-pose", "yolov8"):
        return YoloPoseDetector(**kwargs)
    raise ValueError(
        f"unknown pose backend {backend!r}; use oracle|mediapipe|yolo"
    )
