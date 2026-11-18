"""Story Stage layer content model + stub source (PRD-002 slice 3).

A real Synesyn ``story_stage`` instance is observed non-invasively by the
Godot bridge. Headless verification uses :class:`StubStoryStageSource`, which
emits known solid-colour (or image) layers without importing Synesyn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

import numpy as np

from lumur_synesyn.story_stage_layout import (
    CANONICAL_LAYERS,
    LAYER_AMBIENCE,
    LAYER_BACKDROP,
    LAYER_CAPTION,
    LAYER_CHARACTER,
    LAYER_CLIP,
    canonical_layer,
)

# Distinct RGB colours for stub verification (0..1). Chosen so sim chromaticity
# checks can tell layers apart after projector→camera.
STUB_LAYER_COLORS: dict[str, tuple[float, float, float]] = {
    LAYER_BACKDROP: (0.08, 0.12, 0.92),  # blue — main wall
    LAYER_CHARACTER: (0.12, 0.88, 0.18),  # green — side wall
    LAYER_CLIP: (0.95, 0.55, 0.08),  # amber — overlays character surface
    LAYER_CAPTION: (0.95, 0.92, 0.15),  # yellow — caption region
    LAYER_AMBIENCE: (0.92, 0.10, 0.12),  # red — floor
}


@dataclass
class LayerFrame:
    """One visual frame for a Story Stage layer."""

    layer: str
    # HxWx3 or HxWx4 float32 in 0..1. None → use ``color`` as solid fill.
    image: np.ndarray | None = None
    color: tuple[float, float, float] = (0.5, 0.5, 0.5)
    # Optional clip / transition metadata.
    time_s: float = 0.0
    duration_s: float = 0.0
    transition: str = "cut"  # cut | crossfade
    transition_from: np.ndarray | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.layer = canonical_layer(self.layer)


@dataclass
class StoryStageSnapshot:
    """All layers at one instant (what the bridge projects onto the room)."""

    frames: dict[str, LayerFrame] = field(default_factory=dict)
    scenario: dict[str, Any] = field(default_factory=dict)
    time_s: float = 0.0

    def get(self, layer: str) -> LayerFrame | None:
        return self.frames.get(canonical_layer(layer))

    def layers(self) -> list[str]:
        return list(self.frames.keys())


class StoryStageSource(Protocol):
    """Produces layer snapshots. Stub or live observer both satisfy this."""

    def snapshot(self, time_s: float = 0.0) -> StoryStageSnapshot:
        ...


@dataclass
class StubStoryStageSource:
    """Deterministic mock Story Stage for headless sim tests.

    Produces known solid colours (or optional custom images) for each layer.
    Supports a simple clip timeline: at ``clip_start_s`` the character surface
    content crossfades toward the clip colour over ``clip_fade_s``.
    """

    colors: dict[str, tuple[float, float, float]] = field(
        default_factory=lambda: dict(STUB_LAYER_COLORS)
    )
    images: dict[str, np.ndarray] = field(default_factory=dict)
    scenario: dict[str, Any] = field(default_factory=dict)
    clip_start_s: float = 0.5
    clip_fade_s: float = 0.25
    include_clip: bool = True

    def snapshot(self, time_s: float = 0.0) -> StoryStageSnapshot:
        frames: dict[str, LayerFrame] = {}
        for layer in CANONICAL_LAYERS:
            if layer == LAYER_CLIP and not self.include_clip:
                continue
            color = self.colors.get(layer, (0.5, 0.5, 0.5))
            image = self.images.get(layer)
            transition = "cut"
            transition_from = None
            if layer == LAYER_CLIP and self.include_clip:
                # Clip becomes active after clip_start_s; fade from character.
                if time_s < self.clip_start_s:
                    continue
                fade_t = 0.0
                if self.clip_fade_s > 0:
                    fade_t = min(
                        1.0, max(0.0, (time_s - self.clip_start_s) / self.clip_fade_s)
                    )
                if fade_t < 1.0:
                    transition = "crossfade"
                    char = self.images.get(LAYER_CHARACTER)
                    if char is None:
                        c = self.colors.get(LAYER_CHARACTER, (0.5, 0.5, 0.5))
                        transition_from = _solid(8, 8, c)
                    else:
                        transition_from = char
                    # Encode fade amount for the composer.
                    frames[layer] = LayerFrame(
                        layer=layer,
                        image=image,
                        color=color,
                        time_s=time_s,
                        transition=transition,
                        transition_from=transition_from,
                        meta={"fade": fade_t},
                    )
                    continue
            frames[layer] = LayerFrame(
                layer=layer,
                image=image,
                color=color,
                time_s=time_s,
                transition=transition,
                transition_from=transition_from,
            )
        return StoryStageSnapshot(frames=frames, scenario=dict(self.scenario), time_s=time_s)

    def timeline(self, times: list[float]) -> Iterator[StoryStageSnapshot]:
        for t in times:
            yield self.snapshot(t)


def _solid(h: int, w: int, color: tuple[float, float, float]) -> np.ndarray:
    out = np.zeros((h, w, 3), dtype=np.float32)
    out[:] = np.asarray(color, dtype=np.float32).reshape(1, 1, 3)
    return out
