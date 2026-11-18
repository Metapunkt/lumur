"""Predicted-frame subtraction mask (ADR 0005).

Pose runs on the raw webcam frame. This module predicts the camera image of
the projected content (via calibration / room correspondence + radiometric
model), compares it to the raw frame, and yields a foreground mask used to
reject false detections that sit on projected content.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from lumur.track.radiometric import RadiometricModel, calibrate_radiometric, fit_affine

__all__ = [
    "RadiometricModel",
    "calibrate_radiometric",
    "fit_affine",
    "PredictedFrameSubtractor",
    "predict_projected_camera_image",
]


def predict_projected_camera_image(
    pattern: np.ndarray | None,
    *,
    albedo: np.ndarray,
    proj_u: np.ndarray,
    proj_v: np.ndarray,
    valid_proj: np.ndarray,
    ambient: float = 0.0,
    exposure: float = 1.0,
    gamma: float = 2.2,
    radiometric: RadiometricModel | None = None,
) -> np.ndarray:
    """Predict the camera's view of projected light (no people).

    Uses dense camera→projector correspondence and surface albedo — the same
    quantities a room package / sim ground truth already carries.
    """
    h, w = albedo.shape
    if pattern is None:
        pred = np.full((h, w), float(ambient) * exposure, dtype=np.float32)
        pred = np.stack([pred, pred, pred], axis=-1)
    else:
        pat = pattern.astype(np.float32)
        if pat.ndim == 2:
            pat = np.stack([pat, pat, pat], axis=-1)
        linear = np.power(np.clip(pat[:, :, :3] / 255.0, 0.0, 1.0), gamma) * 255.0
        sampled = np.zeros((h, w, 3), dtype=np.float32)
        if np.any(valid_proj):
            ui = np.rint(proj_u[valid_proj]).astype(np.int32)
            vi = np.rint(proj_v[valid_proj]).astype(np.int32)
            ph, pw = linear.shape[:2]
            inside = (ui >= 0) & (ui < pw) & (vi >= 0) & (vi < ph)
            idx = np.flatnonzero(valid_proj)
            keep = idx[inside]
            ui, vi = ui[inside], vi[inside]
            flat = sampled.reshape(-1, 3)
            flat[keep] = linear[vi, ui]
        radiance = float(ambient) + albedo[..., None] * sampled
        pred = radiance * float(exposure)

    pred = np.clip(pred, 0, 255)
    if radiometric is not None:
        pred = radiometric.apply(pred)
    return np.clip(pred, 0, 255).astype(np.float32)


@dataclass
class SubtractionResult:
    predicted: np.ndarray  # float HxWx3
    difference: np.ndarray  # float HxW absolute luma delta
    foreground_mask: np.ndarray  # bool HxW — differs from projection
    projected_mask: np.ndarray  # bool HxW — agrees with projection


class PredictedFrameSubtractor:
    """Ring-buffered predicted-frame comparison.

    Push each outgoing projector frame; when a camera frame arrives, look up
    the pattern from ``latency_frames`` ago and build the subtraction mask.
    """

    def __init__(
        self,
        *,
        albedo: np.ndarray,
        proj_u: np.ndarray,
        proj_v: np.ndarray,
        valid_proj: np.ndarray,
        ambient: float = 0.0,
        exposure: float = 1.0,
        gamma: float = 2.2,
        radiometric: RadiometricModel | None = None,
        latency_frames: int = 0,
        diff_threshold: float = 18.0,
        ring_size: int = 32,
    ):
        self.albedo = albedo.astype(np.float32)
        self.proj_u = proj_u.astype(np.float32)
        self.proj_v = proj_v.astype(np.float32)
        self.valid_proj = valid_proj.astype(bool)
        self.ambient = float(ambient)
        self.exposure = float(exposure)
        self.gamma = float(gamma)
        self.radiometric = radiometric or RadiometricModel.identity()
        self.latency_frames = max(0, int(latency_frames))
        self.diff_threshold = float(diff_threshold)
        self._patterns: deque[np.ndarray | None] = deque(maxlen=ring_size)

    def push_projector_frame(self, pattern: np.ndarray | None) -> None:
        self._patterns.append(
            None if pattern is None else np.array(pattern, copy=True)
        )

    def pattern_for_camera(self) -> np.ndarray | None:
        if not self._patterns:
            return None
        idx = len(self._patterns) - 1 - self.latency_frames
        if idx < 0:
            return self._patterns[0]
        return self._patterns[idx]

    def predict(self, pattern: np.ndarray | None = None) -> np.ndarray:
        if pattern is None:
            pattern = self.pattern_for_camera()
        return predict_projected_camera_image(
            pattern,
            albedo=self.albedo,
            proj_u=self.proj_u,
            proj_v=self.proj_v,
            valid_proj=self.valid_proj,
            ambient=self.ambient,
            exposure=self.exposure,
            gamma=self.gamma,
            radiometric=self.radiometric,
        )

    def compare(
        self,
        camera_bgr: np.ndarray,
        *,
        bright_threshold: float = 40.0,
    ) -> SubtractionResult:
        pred = self.predict()
        obs = camera_bgr.astype(np.float32)
        if obs.ndim == 2:
            obs = np.stack([obs, obs, obs], axis=-1)
        else:
            # BGR → RGB to match prediction channel order.
            obs = obs[:, :, ::-1]
        diff = np.mean(np.abs(obs - pred), axis=2)
        pred_luma = pred.mean(axis=2) if pred.ndim == 3 else pred
        # Only treat *bright* agreement as projected content. Dim residuals
        # cannot separate a person from a faintly lit floor (ADR 0005).
        bright = pred_luma >= float(bright_threshold)
        agrees = self.valid_proj & bright & (diff <= self.diff_threshold)
        foreground = (~agrees)
        return SubtractionResult(
            predicted=pred,
            difference=diff.astype(np.float32),
            foreground_mask=foreground,
            projected_mask=agrees,
        )

    def filter_keypoints(
        self,
        keypoints_uv: list[tuple[float, float]],
        mask: np.ndarray | None = None,
        *,
        require_foreground_fraction: float = 0.5,
        radius: int = 3,
    ) -> list[bool]:
        """Return True for keypoints that look like real foreground.

        A detection is rejected when most of a small neighbourhood sits on the
        projected-content agreement mask (false person painted on a wall).
        """
        if mask is None:
            raise ValueError("mask required (pass projected_mask from compare)")
        h, w = mask.shape
        keep: list[bool] = []
        for u, v in keypoints_uv:
            ui, vi = int(round(u)), int(round(v))
            if ui < 0 or vi < 0 or ui >= w or vi >= h:
                # Off-frame joints: treat as not-projected (do not alone reject).
                keep.append(True)
                continue
            y0, y1 = max(0, vi - radius), min(h, vi + radius + 1)
            x0, x1 = max(0, ui - radius), min(w, ui + radius + 1)
            patch = mask[y0:y1, x0:x1]
            frac_projected = float(patch.mean()) if patch.size else 0.0
            keep.append(frac_projected < (1.0 - require_foreground_fraction))
        return keep

    @classmethod
    def from_sim_ground_truth(
        cls,
        ground_truth,
        *,
        ambient: float,
        exposure: float,
        gamma: float,
        radiometric: RadiometricModel | None = None,
        latency_frames: int = 0,
        diff_threshold: float = 18.0,
    ) -> PredictedFrameSubtractor:
        corr = ground_truth.correspondence
        return cls(
            albedo=ground_truth.albedo,
            proj_u=corr.proj_u,
            proj_v=corr.proj_v,
            valid_proj=corr.valid,
            ambient=ambient,
            exposure=exposure,
            gamma=gamma,
            radiometric=radiometric,
            latency_frames=latency_frames,
            diff_threshold=diff_threshold,
        )
