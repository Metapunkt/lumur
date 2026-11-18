"""Python reference implementation of correspondence-based paint mapping.

Mirrors the Godot ``paint_mode.gdshader`` logic so CI can verify paint
without a Godot binary. Prefer running Godot headless when available.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np

Mode = Literal["solid", "texture", "pulse"]


@dataclass
class PaintAssignment:
    """Per-surface content for the paint pass."""

    surface_id: int
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)  # RGB in 0..1
    mode: Mode = "solid"
    # Optional HxWx3 float texture in 0..1; sampled with surface UV.
    texture: np.ndarray | None = None
    pulse_hz: float = 1.0


def paint_projector_image(
    surface_id: np.ndarray,
    confidence: np.ndarray,
    valid: np.ndarray,
    assignments: list[PaintAssignment],
    *,
    confidence_threshold: float = 0.05,
    lookup_uv: np.ndarray | None = None,
    time_s: float = 0.0,
) -> np.ndarray:
    """Render a projector RGB image (float32 HxWx3 in 0..1).

    ``surface_id`` / ``confidence`` / ``valid`` are projector-resolution maps.
    ``lookup_uv`` is optional HxWx2 normalised UV (from the distortion/lookup
    texture); when omitted, SCREEN-style UV is derived from pixel indices.
    """
    h, w = surface_id.shape
    out = np.zeros((h, w, 3), dtype=np.float32)
    by_id = {a.surface_id: a for a in assignments}

    yy, xx = np.mgrid[0:h, 0:w]
    if lookup_uv is None:
        u = (xx.astype(np.float32) + 0.5) / float(w)
        v = (yy.astype(np.float32) + 0.5) / float(h)
    else:
        u = lookup_uv[..., 0].astype(np.float32)
        v = lookup_uv[..., 1].astype(np.float32)

    mask = (
        valid.astype(bool)
        & (confidence >= confidence_threshold)
        & (surface_id > 0)
    )
    for sid, assignment in by_id.items():
        sel = mask & (surface_id == int(sid))
        if not np.any(sel):
            continue
        color = np.asarray(assignment.color, dtype=np.float32).reshape(3)
        if assignment.mode == "solid":
            out[sel] = color
        elif assignment.mode == "texture" and assignment.texture is not None:
            tex = assignment.texture
            th, tw = tex.shape[:2]
            ui = np.clip(np.rint(u[sel] * (tw - 1)).astype(np.int32), 0, tw - 1)
            vi = np.clip(np.rint(v[sel] * (th - 1)).astype(np.int32), 0, th - 1)
            sampled = tex[vi, ui, :3].astype(np.float32)
            out[sel] = sampled * color.reshape(1, 3)
        elif assignment.mode == "pulse":
            phase = np.sin(
                2.0 * np.pi * float(assignment.pulse_hz) * float(time_s)
                + (u[sel] + v[sel]) * np.pi
            )
            amp = 0.55 + 0.45 * phase
            out[sel] = color.reshape(1, 3) * amp.astype(np.float32)[:, None]
        else:
            out[sel] = color
    return np.clip(out, 0.0, 1.0)


def paint_from_godot_assets(
    godot_dir: str | Path,
    assignments: list[PaintAssignment],
    *,
    confidence_threshold: float | None = None,
    time_s: float = 0.0,
) -> np.ndarray:
    """Load exported Godot PNGs and paint with the reference mapper."""
    import json
    from pathlib import Path

    import cv2

    godot_dir = Path(godot_dir)
    manifest = json.loads(
        (godot_dir / "paint_manifest.json").read_text(encoding="utf-8")
    )
    tex = manifest["textures"]
    surface_id = cv2.imread(str(godot_dir / tex["surface_id"]), cv2.IMREAD_GRAYSCALE)
    confidence_u8 = cv2.imread(
        str(godot_dir / tex["confidence"]), cv2.IMREAD_GRAYSCALE
    )
    lookup_bgr = cv2.imread(str(godot_dir / tex["lookup"]), cv2.IMREAD_COLOR)
    if surface_id is None or confidence_u8 is None or lookup_bgr is None:
        raise FileNotFoundError(f"missing paint textures under {godot_dir}")

    lookup_rgb = cv2.cvtColor(lookup_bgr, cv2.COLOR_BGR2RGB)
    valid = lookup_rgb[..., 2] > 127
    lookup_uv = np.stack(
        [
            lookup_rgb[..., 0].astype(np.float32) / 255.0,
            lookup_rgb[..., 1].astype(np.float32) / 255.0,
        ],
        axis=-1,
    )
    thr = (
        float(confidence_threshold)
        if confidence_threshold is not None
        else float(manifest.get("confidence_threshold_default", 0.05))
    )
    return paint_projector_image(
        surface_id.astype(np.int32),
        confidence_u8.astype(np.float32) / 255.0,
        valid,
        assignments,
        confidence_threshold=thr,
        lookup_uv=lookup_uv,
        time_s=time_s,
    )
