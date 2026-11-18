"""Projective light transport: projector image → room → webcam frame."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lumur.sim.devices import VirtualCamera, VirtualProjector
from lumur.sim.geometry import pixel_rays, project_points
from lumur.sim.room import Room


@dataclass
class RenderBuffers:
    """Per-pixel ground-truth buffers produced alongside a camera frame."""

    image: np.ndarray  # uint8 HxW gray
    depth: np.ndarray  # float32 HxW, metres along ray; 0 = miss
    proj_u: np.ndarray  # float32 HxW
    proj_v: np.ndarray  # float32 HxW
    valid_proj: np.ndarray  # bool HxW — hit + inside projector frustum
    albedo: np.ndarray  # float32 HxW


def _sample_pattern(
    pattern: np.ndarray,
    pu: np.ndarray,
    pv: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Nearest-neighbour sample of a projector pattern at subpixel coords."""
    h, w = pattern.shape[:2]
    out = np.zeros(pu.shape, dtype=np.float32)
    if not np.any(valid):
        return out
    ui = np.rint(pu[valid]).astype(np.int32)
    vi = np.rint(pv[valid]).astype(np.int32)
    inside = (ui >= 0) & (ui < w) & (vi >= 0) & (vi < h)
    # Fold inside back into the flat valid mask.
    idx = np.flatnonzero(valid)
    keep = idx[inside]
    ui = ui[inside]
    vi = vi[inside]
    flat = out.ravel()
    flat[keep] = pattern[vi, ui].astype(np.float32)
    return flat.reshape(out.shape)


def render_camera_view(
    room: Room,
    camera: VirtualCamera,
    projector: VirtualProjector,
    pattern: np.ndarray | None,
    *,
    rng: np.random.Generator | None = None,
) -> RenderBuffers:
    """Render what ``camera`` sees when ``projector`` shows ``pattern``.

    ``pattern`` is uint8 HxW (or HxWx3, converted to gray). ``None`` means
    the projector is off (ambient only).
    """
    h, w = camera.height, camera.width
    dirs = pixel_rays(
        w, h, camera.K, camera.R, distortion=camera.distortion
    ).reshape(-1, 3)
    origin = np.broadcast_to(camera.center, dirs.shape).copy()
    points, albedo, t_hit = room.intersect(origin, dirs)

    depth = np.where(np.isfinite(t_hit), t_hit, 0.0).astype(np.float32).reshape(h, w)
    albedo_img = albedo.astype(np.float32).reshape(h, w)

    proj_u = np.full(h * w, -1.0, dtype=np.float32)
    proj_v = np.full(h * w, -1.0, dtype=np.float32)
    valid_proj = np.zeros(h * w, dtype=bool)

    hit = np.isfinite(t_hit)
    if np.any(hit):
        pu, pv, pdepth = project_points(
            points[hit], projector.K, projector.R, projector.t
        )
        in_frustum = (
            (pdepth > 1e-8)
            & (pu >= 0)
            & (pu < projector.width)
            & (pv >= 0)
            & (pv < projector.height)
        )
        hit_idx = np.flatnonzero(hit)
        ok = hit_idx[in_frustum]
        proj_u[ok] = pu[in_frustum].astype(np.float32)
        proj_v[ok] = pv[in_frustum].astype(np.float32)
        valid_proj[ok] = True

    proj_u = proj_u.reshape(h, w)
    proj_v = proj_v.reshape(h, w)
    valid_proj = valid_proj.reshape(h, w)

    radiance = np.full((h, w), float(camera.ambient), dtype=np.float32)
    if pattern is not None:
        if pattern.ndim == 3:
            # BGR or RGB → luma-ish gray
            pat = pattern.astype(np.float32)
            if pat.shape[2] == 3:
                gray = 0.114 * pat[:, :, 0] + 0.587 * pat[:, :, 1] + 0.299 * pat[:, :, 2]
            else:
                gray = pat[:, :, 0]
        else:
            gray = pattern.astype(np.float32)
        # Projector digital → approximate linear light via gamma.
        linear = np.power(np.clip(gray / 255.0, 0.0, 1.0), projector.gamma) * 255.0
        sampled = _sample_pattern(linear, proj_u, proj_v, valid_proj)
        radiance = radiance + albedo_img * sampled

    exposed = radiance * float(camera.exposure)
    if camera.noise_std > 0:
        rng = rng or np.random.default_rng(camera.seed)
        exposed = exposed + rng.normal(0.0, camera.noise_std, size=exposed.shape)

    image = np.clip(exposed, 0, 255).astype(np.float32)
    if camera.blur_sigma and camera.blur_sigma > 0:
        import cv2

        image = cv2.GaussianBlur(
            image, ksize=(0, 0), sigmaX=float(camera.blur_sigma)
        )

    return RenderBuffers(
        image=np.clip(image, 0, 255).astype(np.uint8),
        depth=depth,
        proj_u=proj_u,
        proj_v=proj_v,
        valid_proj=valid_proj,
        albedo=albedo_img,
    )
