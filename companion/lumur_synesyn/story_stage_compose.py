"""Compose Story Stage layer frames into surface textures.

Handles aspect fitting, safe-area placement, and simple cut/crossfade
transitions. Output textures are float32 HxWx3 in 0..1 for the paint path.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from lumur_synesyn.story_stage_layers import LayerFrame
from lumur_synesyn.story_stage_layout import SafeArea


def aspect_fit_size(
    src_w: int,
    src_h: int,
    box_w: int,
    box_h: int,
) -> tuple[int, int]:
    """Return (w, h) that fits ``src`` inside ``box`` preserving aspect."""
    if src_w <= 0 or src_h <= 0 or box_w <= 0 or box_h <= 0:
        return max(1, box_w), max(1, box_h)
    scale = min(box_w / float(src_w), box_h / float(src_h))
    return max(1, int(round(src_w * scale))), max(1, int(round(src_h * scale)))


def safe_box(
    width: int,
    height: int,
    area: SafeArea,
) -> tuple[int, int, int, int]:
    """Pixel box (x0, y0, x1, y1) from normalised safe-area insets."""
    x0 = int(round(float(area.left) * width))
    x1 = int(round((1.0 - float(area.right)) * width))
    y0 = int(round(float(area.top) * height))
    y1 = int(round((1.0 - float(area.bottom)) * height))
    x0 = max(0, min(width - 1, x0))
    y0 = max(0, min(height - 1, y0))
    x1 = max(x0 + 1, min(width, x1))
    y1 = max(y0 + 1, min(height, y1))
    return x0, y0, x1, y1


def _as_rgb_float(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image)
    if arr.dtype != np.float32 and arr.dtype != np.float64:
        arr = arr.astype(np.float32)
        if arr.max() > 1.5:
            arr = arr / 255.0
    else:
        arr = arr.astype(np.float32)
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    if arr.shape[-1] >= 4:
        arr = arr[..., :3]
    return np.clip(arr, 0.0, 1.0)


def _resize_rgb(image: np.ndarray, width: int, height: int) -> np.ndarray:
    """Nearest-neighbour resize (no OpenCV dependency required here)."""
    src = _as_rgb_float(image)
    sh, sw = src.shape[:2]
    if sw == width and sh == height:
        return src
    ys = (np.arange(height) + 0.5) * (sh / float(height)) - 0.5
    xs = (np.arange(width) + 0.5) * (sw / float(width)) - 0.5
    yi = np.clip(np.rint(ys).astype(np.int32), 0, sh - 1)
    xi = np.clip(np.rint(xs).astype(np.int32), 0, sw - 1)
    return src[yi[:, None], xi[None, :], :]


def frame_to_rgb(
    frame: LayerFrame,
    *,
    width: int = 64,
    height: int = 64,
) -> np.ndarray:
    """Materialise a layer frame to RGB, applying transitions when present."""
    if frame.image is not None:
        base = _resize_rgb(frame.image, width, height)
    else:
        base = np.zeros((height, width, 3), dtype=np.float32)
        base[:] = np.asarray(frame.color, dtype=np.float32).reshape(1, 1, 3)

    if frame.transition == "crossfade" and frame.transition_from is not None:
        prev = _resize_rgb(frame.transition_from, width, height)
        fade = float(frame.meta.get("fade", 0.5))
        fade = min(1.0, max(0.0, fade))
        base = prev * (1.0 - fade) + base * fade
    return np.clip(base.astype(np.float32), 0.0, 1.0)


def compose_layer_texture(
    frame: LayerFrame,
    *,
    surface_size: tuple[int, int] = (64, 64),
    safe_area: SafeArea | None = None,
    clear_color: tuple[float, float, float] = (0.0, 0.0, 0.0),
    content_size: tuple[int, int] | None = None,
) -> np.ndarray:
    """Fit layer content into a surface texture with aspect + safe area.

    ``surface_size`` is (width, height). Content is aspect-fitted into the
    safe box; letterbox / pillarbox regions keep ``clear_color``.
    """
    sw, sh = int(surface_size[0]), int(surface_size[1])
    sw = max(1, sw)
    sh = max(1, sh)
    area = safe_area or SafeArea()
    x0, y0, x1, y1 = safe_box(sw, sh, area)
    box_w, box_h = x1 - x0, y1 - y0

    if content_size is None:
        if frame.image is not None:
            ch, cw = frame.image.shape[:2]
            content_size = (cw, ch)
        else:
            content_size = (box_w, box_h)
    fit_w, fit_h = aspect_fit_size(content_size[0], content_size[1], box_w, box_h)
    content = frame_to_rgb(frame, width=fit_w, height=fit_h)

    out = np.zeros((sh, sw, 3), dtype=np.float32)
    out[:] = np.asarray(clear_color, dtype=np.float32).reshape(1, 1, 3)
    ox = x0 + (box_w - fit_w) // 2
    oy = y0 + (box_h - fit_h) // 2
    out[oy : oy + fit_h, ox : ox + fit_w] = content
    return out


def blend_layers_on_surface(
    textures: list[np.ndarray],
    *,
    opacities: list[float] | None = None,
) -> np.ndarray:
    """Alpha-over stack of same-sized RGB textures (last on top)."""
    if not textures:
        raise ValueError("no textures to blend")
    out = textures[0].astype(np.float32).copy()
    if opacities is None:
        opacities = [1.0] * len(textures)
    for tex, opac in zip(textures[1:], opacities[1:]):
        a = float(opac)
        out = out * (1.0 - a) + tex.astype(np.float32) * a
    return np.clip(out, 0.0, 1.0)


def apply_confidence_mask(
    texture: np.ndarray,
    confidence: np.ndarray,
    *,
    threshold: float = 0.05,
    fill: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Zero-out low-confidence samples (mirrors paint-mode masking intent).

    ``confidence`` may be projector-sized; when shapes differ the mask is
    resized with nearest neighbour. Used by tests / tools that want an
    explicit masked texture before paint; the live paint shader still applies
    its own confidence threshold.
    """
    tex = texture.astype(np.float32)
    conf = np.asarray(confidence, dtype=np.float32)
    if conf.ndim == 3:
        conf = conf[..., 0]
    if conf.shape != tex.shape[:2]:
        # crude nearest resize
        th, tw = tex.shape[:2]
        ch, cw = conf.shape[:2]
        ys = np.clip(
            np.rint((np.arange(th) + 0.5) * (ch / float(th)) - 0.5).astype(np.int32),
            0,
            ch - 1,
        )
        xs = np.clip(
            np.rint((np.arange(tw) + 0.5) * (cw / float(tw)) - 0.5).astype(np.int32),
            0,
            cw - 1,
        )
        conf = conf[ys[:, None], xs[None, :]]
    if conf.max() > 1.5:
        conf = conf / 255.0
    out = tex.copy()
    out[conf < float(threshold)] = np.asarray(fill, dtype=np.float32)
    return out


def compose_meta(frame: LayerFrame, surface_role: str, safe_area: SafeArea) -> dict[str, Any]:
    return {
        "layer": frame.layer,
        "surface_role": surface_role,
        "transition": frame.transition,
        "safe_area": safe_area.as_dict(),
        "time_s": frame.time_s,
    }
