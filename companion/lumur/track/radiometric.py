"""Rough radiometric (gain/bias) calibration for predicted-frame subtraction.

Projects known gray levels, observes the camera response on lit surfaces,
and fits a per-channel affine model. Sufficient for sim and for locking out
gross projector/camera mismatches (ADR 0005).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class RadiometricModel:
    """``observed ≈ gain * predicted + bias`` in digital levels [0, 255]."""

    gain: np.ndarray  # (3,) or scalar broadcast
    bias: np.ndarray
    residual_rms: float = 0.0

    def apply(self, predicted: np.ndarray) -> np.ndarray:
        pred = predicted.astype(np.float32)
        g = self.gain.astype(np.float32)
        b = self.bias.astype(np.float32)
        if pred.ndim == 2:
            return np.clip(g.mean() * pred + b.mean(), 0, 255)
        return np.clip(g.reshape(1, 1, -1) * pred + b.reshape(1, 1, -1), 0, 255)

    def to_dict(self) -> dict:
        return {
            "gain": np.asarray(self.gain).reshape(-1).tolist(),
            "bias": np.asarray(self.bias).reshape(-1).tolist(),
            "residual_rms": float(self.residual_rms),
        }

    @classmethod
    def identity(cls) -> RadiometricModel:
        return cls(
            gain=np.ones(3, dtype=np.float64),
            bias=np.zeros(3, dtype=np.float64),
            residual_rms=0.0,
        )


def fit_affine(
    predicted: np.ndarray,
    observed: np.ndarray,
    mask: np.ndarray | None = None,
) -> RadiometricModel:
    """Least-squares gain/bias from paired predicted/observed samples."""
    pred = predicted.astype(np.float64)
    obs = observed.astype(np.float64)
    if pred.ndim == 2:
        pred = pred[..., None]
        obs = obs[..., None]
    if mask is None:
        mask = np.ones(pred.shape[:2], dtype=bool)
    else:
        mask = mask.astype(bool)

    gains = []
    biases = []
    residuals = []
    n_ch = pred.shape[2]
    for c in range(n_ch):
        x = pred[..., c][mask].ravel()
        y = obs[..., c][mask].ravel()
        if x.size < 8:
            gains.append(1.0)
            biases.append(0.0)
            residuals.append(0.0)
            continue
        # [x 1] @ [g, b] = y
        A = np.stack([x, np.ones_like(x)], axis=1)
        coef, _, _, _ = np.linalg.lstsq(A, y, rcond=None)
        g, b = float(coef[0]), float(coef[1])
        # Keep gain sane.
        if not np.isfinite(g) or abs(g) < 1e-4:
            g, b = 1.0, 0.0
        err = y - (g * x + b)
        gains.append(g)
        biases.append(b)
        residuals.append(float(np.sqrt(np.mean(err * err))))
    while len(gains) < 3:
        gains.append(gains[-1] if gains else 1.0)
        biases.append(biases[-1] if biases else 0.0)
        residuals.append(residuals[-1] if residuals else 0.0)
    return RadiometricModel(
        gain=np.asarray(gains[:3], dtype=np.float64),
        bias=np.asarray(biases[:3], dtype=np.float64),
        residual_rms=float(np.mean(residuals[:3])),
    )


def calibrate_radiometric(
    predict_fn,
    capture_fn,
    *,
    levels: tuple[int, ...] = (32, 96, 160, 224),
    projector_size: tuple[int, int],
) -> RadiometricModel:
    """Project flat gray frames and fit the affine radiometric model.

    ``predict_fn(pattern_uint8) -> predicted_camera`` should render the empty
    room (no people) as the companion would predict. ``capture_fn`` returns
    the observed camera frame for the same pattern.
    """
    pw, ph = projector_size
    preds = []
    obss = []
    masks = []
    for level in levels:
        pattern = np.full((ph, pw), int(level), dtype=np.uint8)
        pattern_bgr = np.stack([pattern, pattern, pattern], axis=-1)
        pred = predict_fn(pattern_bgr)
        obs = capture_fn(pattern_bgr)
        if pred.ndim == 2:
            pred = np.stack([pred, pred, pred], axis=-1)
        if obs.ndim == 2:
            obs = np.stack([obs, obs, obs], axis=-1)
        # Lit pixels: predicted above ambient-ish floor.
        mask = pred.mean(axis=2) > 8.0
        preds.append(pred)
        obss.append(obs)
        masks.append(mask)
    pred_all = np.concatenate(preds, axis=0)
    obs_all = np.concatenate(obss, axis=0)
    mask_all = np.concatenate(masks, axis=0)
    return fit_affine(pred_all, obs_all, mask_all)
