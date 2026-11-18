"""Surface ownership and paint-mode compositing (PRD-003 slice 3 / ADR 0018).

Exclusive ownership by default; overlays only when the app declares
``shares``. Confidence masking reuses paint-mode thresholds — apps cannot
invent coverage. Switch / pause hand off with a deterministic cut.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from lumur.app.fit import FitResult
from lumur.app.room_services import RoomServices
from lumur.paint.render import PaintAssignment, paint_from_godot_assets


@dataclass(frozen=True)
class SurfaceClaim:
    """One app's claim on a bound surface."""

    app_id: str
    surface_id: int
    surface_key: str
    layer: str  # "base" | "overlay"

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "surface_id": self.surface_id,
            "surface_key": self.surface_key,
            "layer": self.layer,
        }


@dataclass
class OwnershipEntry:
    """Ownership of one surface (base + ordered overlays)."""

    surface_id: int
    base_app_id: str | None = None
    base_key: str | None = None
    overlays: list[tuple[str, str]] = field(default_factory=list)  # (app_id, key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface_id": self.surface_id,
            "base_app_id": self.base_app_id,
            "base_key": self.base_key,
            "overlays": [
                {"app_id": a, "surface_key": k} for a, k in self.overlays
            ],
        }


@dataclass
class TransitionRecord:
    kind: str  # "cut" (v1 required); "crossfade" optional later
    from_app_id: str | None
    to_app_id: str | None
    surface_ids: tuple[int, ...]
    reason: str  # "switch" | "pause" | "resume" | "stop" | "launch"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "from_app_id": self.from_app_id,
            "to_app_id": self.to_app_id,
            "surface_ids": list(self.surface_ids),
            "reason": self.reason,
        }


@dataclass
class CompositeFrame:
    """One composed projector frame snapshot (ownership + masking digest)."""

    ownership: dict[int, OwnershipEntry]
    assignments: list[PaintAssignment]
    painted_pixels: int
    masked_pixels: int
    total_pixels: int
    digest: str
    transition: TransitionRecord | None = None
    image: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ownership": {str(k): v.to_dict() for k, v in self.ownership.items()},
            "painted_pixels": self.painted_pixels,
            "masked_pixels": self.masked_pixels,
            "total_pixels": self.total_pixels,
            "digest": self.digest,
            "transition": self.transition.to_dict() if self.transition else None,
            "assignment_ids": [a.surface_id for a in self.assignments],
        }


class CompositorError(ValueError):
    """Ownership / layering conflict."""

    def __init__(self, message: str, *, reason: str = "conflict"):
        super().__init__(message)
        self.reason = reason


@dataclass
class Compositor:
    """Room display server: who owns which surface, and paint-mode masking."""

    room: RoomServices
    confidence_threshold: float | None = None
    ownership: dict[int, OwnershipEntry] = field(default_factory=dict)
    # app_id → surface_id → claim
    claims_by_app: dict[str, dict[int, SurfaceClaim]] = field(default_factory=dict)
    # app_id → content keyed by surface_id
    content: dict[str, dict[int, PaintAssignment]] = field(default_factory=dict)
    transitions: list[TransitionRecord] = field(default_factory=list)
    last_frame: CompositeFrame | None = None
    # Apps that declared share keys (overlay-capable surface keys).
    share_keys: dict[str, frozenset[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence_threshold is None:
            thr = 0.05
            if self.room.paint_manifest:
                thr = float(
                    self.room.paint_manifest.get("confidence_threshold", thr)
                )
            self.confidence_threshold = thr

    def exclusive_owned_ids(self) -> set[int]:
        """Surface ids with a live exclusive base owner (candidates for fit)."""
        return {
            sid
            for sid, entry in self.ownership.items()
            if entry.base_app_id is not None
        }

    def app_controls_surface(self, app_id: str, surface_id: int) -> bool:
        """True when ``app_id`` owns base or overlays ``surface_id``."""
        claims = self.claims_by_app.get(app_id) or {}
        return int(surface_id) in claims

    def controlled_surface_ids(self, app_id: str) -> set[int]:
        return set((self.claims_by_app.get(app_id) or {}).keys())

    def ownership_table(self) -> dict[int, dict[str, Any]]:
        return {sid: e.to_dict() for sid, e in sorted(self.ownership.items())}

    def set_share_keys(self, app_id: str, keys: Sequence[str] | None) -> None:
        self.share_keys[app_id] = frozenset(str(k) for k in (keys or ()))

    def claim_from_fit(
        self,
        app_id: str,
        fit: FitResult,
        *,
        shares: Sequence[str] | None = None,
        as_overlay: bool = False,
    ) -> list[SurfaceClaim]:
        """Register ownership from a successful fit.

        Exclusive base claims fail when another running app already owns the
        surface. Overlay claims require the surface key in ``shares`` and do
        not steal base ownership (ADR 0018).
        """
        self.set_share_keys(app_id, shares)
        share_set = self.share_keys.get(app_id, frozenset())
        claimed: list[SurfaceClaim] = []
        for key, binding in fit.bindings.items():
            if binding.surface_id is None:
                continue  # optional unmet — no geometry invention
            sid = int(binding.surface_id)
            entry = self.ownership.get(sid)
            other_base = (
                entry is not None
                and entry.base_app_id is not None
                and entry.base_app_id != app_id
            )
            # ``shares`` means willing to overlay; alone, still take base.
            want_overlay = as_overlay or (key in share_set and other_base)
            if want_overlay:
                claim = self._claim_overlay(app_id, sid, key)
            else:
                claim = self._claim_base(app_id, sid, key)
            claimed.append(claim)
        return claimed

    def _claim_base(self, app_id: str, surface_id: int, key: str) -> SurfaceClaim:
        entry = self.ownership.setdefault(
            surface_id, OwnershipEntry(surface_id=surface_id)
        )
        if entry.base_app_id is not None and entry.base_app_id != app_id:
            raise CompositorError(
                f"surface {surface_id} exclusively owned by {entry.base_app_id!r}; "
                f"{app_id!r} cannot take base layer",
                reason="exclusive_conflict",
            )
        entry.base_app_id = app_id
        entry.base_key = key
        claim = SurfaceClaim(
            app_id=app_id, surface_id=surface_id, surface_key=key, layer="base"
        )
        self.claims_by_app.setdefault(app_id, {})[surface_id] = claim
        return claim

    def _claim_overlay(self, app_id: str, surface_id: int, key: str) -> SurfaceClaim:
        share_set = self.share_keys.get(app_id, frozenset())
        if key not in share_set:
            raise CompositorError(
                f"app {app_id!r} cannot overlay {key!r} without shares declaration",
                reason="overlay_not_declared",
            )
        entry = self.ownership.setdefault(
            surface_id, OwnershipEntry(surface_id=surface_id)
        )
        # Overlays never steal base; they stack.
        if (app_id, key) not in entry.overlays:
            entry.overlays.append((app_id, key))
        claim = SurfaceClaim(
            app_id=app_id, surface_id=surface_id, surface_key=key, layer="overlay"
        )
        self.claims_by_app.setdefault(app_id, {})[surface_id] = claim
        return claim

    def release(self, app_id: str, *, reason: str = "stop") -> TransitionRecord:
        """Drop all claims for ``app_id`` (cut handoff)."""
        claims = self.claims_by_app.pop(app_id, {})
        surface_ids = tuple(sorted(claims.keys()))
        for sid in surface_ids:
            entry = self.ownership.get(sid)
            if entry is None:
                continue
            if entry.base_app_id == app_id:
                entry.base_app_id = None
                entry.base_key = None
            entry.overlays = [(a, k) for a, k in entry.overlays if a != app_id]
            if entry.base_app_id is None and not entry.overlays:
                self.ownership.pop(sid, None)
        self.content.pop(app_id, None)
        self.share_keys.pop(app_id, None)
        rec = TransitionRecord(
            kind="cut",
            from_app_id=app_id,
            to_app_id=None,
            surface_ids=surface_ids,
            reason=reason,
        )
        self.transitions.append(rec)
        return rec

    def pause_handoff(self, app_id: str) -> TransitionRecord:
        """Pause: release exclusive base ownership; clear that app's content."""
        return self.release(app_id, reason="pause")

    def set_content(
        self,
        app_id: str,
        assignments: Mapping[int, PaintAssignment] | Sequence[PaintAssignment],
    ) -> None:
        """Set per-surface paint content for an owning / overlaying app."""
        by_id: dict[int, PaintAssignment] = {}
        if isinstance(assignments, Mapping):
            for sid, a in assignments.items():
                by_id[int(sid)] = a
        else:
            for a in assignments:
                by_id[int(a.surface_id)] = a
        # Only keep content for surfaces this app actually claims (or claimed).
        claimed = self.claims_by_app.get(app_id, {})
        if claimed:
            by_id = {sid: a for sid, a in by_id.items() if sid in claimed}
        self.content[app_id] = by_id

    def compose(
        self,
        *,
        time_s: float = 0.0,
        transition: TransitionRecord | None = None,
        render_image: bool = True,
    ) -> CompositeFrame:
        """Build projector assignments from ownership + content; apply masking.

        Low-confidence / invalid pixels stay unpainted (paint-mode authority).
        Apps cannot override ``confidence_threshold`` here to invent coverage.
        """
        # Base layer first, then overlays in claim order (later wins in alpha
        # sense for digest — v1 solid overlay replaces base colour on that id
        # for the reference painter; ripples use a separate overlay path in Godot).
        ordered: list[PaintAssignment] = []
        seen: set[int] = set()
        # Prefer base owners' content.
        for sid, entry in sorted(self.ownership.items()):
            if entry.base_app_id is not None:
                app_content = self.content.get(entry.base_app_id, {})
                if sid in app_content:
                    ordered.append(app_content[sid])
                    seen.add(sid)
            for overlay_app, _key in entry.overlays:
                app_content = self.content.get(overlay_app, {})
                if sid in app_content:
                    # Overlay assignment recorded for digest; base still painted
                    # unless overlay provides content (v1: last write for solid).
                    ordered.append(app_content[sid])
                    seen.add(sid)

        thr = float(self.confidence_threshold or 0.05)
        image = None
        painted = 0
        masked = 0
        total = 0
        digest = ""

        godot_dir = self.room.godot_dir
        if render_image and godot_dir is not None and Path(godot_dir).is_dir():
            # Deduplicate by surface_id keeping last (overlay wins for solid).
            by_sid: dict[int, PaintAssignment] = {}
            for a in ordered:
                by_sid[int(a.surface_id)] = a
            assignments = list(by_sid.values())
            image = paint_from_godot_assets(
                godot_dir,
                assignments,
                confidence_threshold=thr,
                time_s=time_s,
            )
            surface_id, confidence, valid = _load_mask_maps(godot_dir)
            total = int(surface_id.size)
            conf_ok = (confidence >= thr) & valid & (surface_id > 0)
            owned_ids = set(self.ownership.keys())
            owned_mask = np.isin(surface_id, list(owned_ids)) if owned_ids else np.zeros_like(valid)
            paintable = conf_ok & owned_mask
            painted = int(np.count_nonzero(paintable))
            # Masked = would-be owned surface pixels rejected by confidence/valid.
            owned_pixels = (
                np.isin(surface_id, list(owned_ids)) & (surface_id > 0)
                if owned_ids
                else np.zeros_like(valid, dtype=bool)
            )
            masked = int(np.count_nonzero(owned_pixels & ~conf_ok))
            digest = _masking_digest(
                surface_id=surface_id,
                confidence=confidence,
                valid=valid,
                threshold=thr,
                ownership=self.ownership,
                assignments=assignments,
                painted=painted,
                masked=masked,
            )
        else:
            # No godot assets: digest from ownership + assignment ids only.
            digest = _ownership_digest(self.ownership, ordered, thr)
            assignments = ordered

        frame = CompositeFrame(
            ownership={k: v for k, v in self.ownership.items()},
            assignments=list(assignments) if render_image else ordered,
            painted_pixels=painted,
            masked_pixels=masked,
            total_pixels=total,
            digest=digest,
            transition=transition,
            image=image,
        )
        self.last_frame = frame
        return frame

    def switch_handoff(
        self,
        from_app_id: str | None,
        to_app_id: str | None,
        *,
        reason: str = "switch",
    ) -> TransitionRecord:
        """Record a cut transition between apps (ownership already updated)."""
        surfaces: set[int] = set()
        if from_app_id and from_app_id in self.claims_by_app:
            surfaces.update(self.claims_by_app[from_app_id].keys())
        if to_app_id and to_app_id in self.claims_by_app:
            surfaces.update(self.claims_by_app[to_app_id].keys())
        rec = TransitionRecord(
            kind="cut",
            from_app_id=from_app_id,
            to_app_id=to_app_id,
            surface_ids=tuple(sorted(surfaces)),
            reason=reason,
        )
        self.transitions.append(rec)
        return rec


def _load_mask_maps(
    godot_dir: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    import cv2

    godot_dir = Path(godot_dir)
    sid = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    conf = cv2.imread(str(godot_dir / "confidence.png"), cv2.IMREAD_GRAYSCALE)
    lookup_bgr = cv2.imread(str(godot_dir / "lookup.png"), cv2.IMREAD_COLOR)
    if sid is None or conf is None or lookup_bgr is None:
        raise FileNotFoundError(f"missing paint maps in {godot_dir}")
    lookup_rgb = cv2.cvtColor(lookup_bgr, cv2.COLOR_BGR2RGB)
    surface_id = sid.astype(np.int32)
    confidence = conf.astype(np.float32) / 255.0
    # Export RGB: R/G = cam UV, B = valid (same as paint_from_godot_assets).
    valid = lookup_rgb[..., 2] > 127
    return surface_id, confidence, valid.astype(bool)


def _masking_digest(
    *,
    surface_id: np.ndarray,
    confidence: np.ndarray,
    valid: np.ndarray,
    threshold: float,
    ownership: Mapping[int, OwnershipEntry],
    assignments: Sequence[PaintAssignment],
    painted: int,
    masked: int,
) -> str:
    """Stable digest of masking + ownership (REQ-003-009 verification)."""
    conf_ok = (confidence >= threshold) & valid & (surface_id > 0)
    # Sample a coarse grid of mask bits for stability without huge hashes.
    h, w = surface_id.shape
    ys = np.linspace(0, h - 1, num=min(32, h), dtype=np.int32)
    xs = np.linspace(0, w - 1, num=min(32, w), dtype=np.int32)
    grid = conf_ok[np.ix_(ys, xs)].astype(np.uint8).tobytes()
    own = [
        {
            "sid": sid,
            "base": entry.base_app_id,
            "overlays": [a for a, _ in entry.overlays],
        }
        for sid, entry in sorted(ownership.items())
    ]
    assigns = sorted(int(a.surface_id) for a in assignments)
    payload = {
        "threshold": round(float(threshold), 6),
        "painted": painted,
        "masked": masked,
        "ownership": own,
        "assignments": assigns,
        "grid_sha": hashlib.sha256(grid).hexdigest()[:16],
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _ownership_digest(
    ownership: Mapping[int, OwnershipEntry],
    assignments: Sequence[PaintAssignment],
    threshold: float,
) -> str:
    own = [
        {
            "sid": sid,
            "base": entry.base_app_id,
            "overlays": [a for a, _ in entry.overlays],
        }
        for sid, entry in sorted(ownership.items())
    ]
    payload = {
        "threshold": round(float(threshold), 6),
        "ownership": own,
        "assignments": sorted(int(a.surface_id) for a in assignments),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def binding_surface_ids(fit: FitResult) -> set[int]:
    return {
        int(b.surface_id)
        for b in fit.bindings.values()
        if b.surface_id is not None
    }
