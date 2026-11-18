"""Story Stage layer roles → Lumur surface roles (PRD-002 slice 3).

Mapping is by role name, not projector UV (REQ-002-009). Scenario overrides
are optional; unknown scenario sections are ignored (REQ-002-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

# Canonical layer roles the bridge understands.
LAYER_BACKDROP = "backdrop"
LAYER_CHARACTER = "character"
LAYER_CLIP = "clip"
LAYER_CAPTION = "caption"
LAYER_AMBIENCE = "ambience"

CANONICAL_LAYERS: tuple[str, ...] = (
    LAYER_BACKDROP,
    LAYER_CHARACTER,
    LAYER_CLIP,
    LAYER_CAPTION,
    LAYER_AMBIENCE,
)

# Synonyms authors / Story Stage scenes may use.
LAYER_ALIASES: dict[str, str] = {
    "background": LAYER_BACKDROP,
    "vis_story": LAYER_BACKDROP,
    "backdrop": LAYER_BACKDROP,
    "portrait": LAYER_CHARACTER,
    "portraits": LAYER_CHARACTER,
    "characters": LAYER_CHARACTER,
    "character": LAYER_CHARACTER,
    "sprites": LAYER_CHARACTER,
    "sprite": LAYER_CHARACTER,
    "flashhead": LAYER_CLIP,
    "video": LAYER_CLIP,
    "clip": LAYER_CLIP,
    "talking_clip": LAYER_CLIP,
    "ogv": LAYER_CLIP,
    "text": LAYER_CAPTION,
    "captions": LAYER_CAPTION,
    "caption": LAYER_CAPTION,
    "dialogue": LAYER_CAPTION,
    "dialog": LAYER_CAPTION,
    "ambient": LAYER_AMBIENCE,
    "ambience": LAYER_AMBIENCE,
    "ripples": LAYER_AMBIENCE,
}

# Preference chains when a room lacks the preferred surface.
DEFAULT_PREFERENCES: dict[str, tuple[str, ...]] = {
    LAYER_BACKDROP: ("wall_1", "wall_2", "floor"),
    LAYER_CHARACTER: ("wall_2", "wall_1", "floor"),
    LAYER_CLIP: ("wall_2", "wall_1", "floor"),
    LAYER_CAPTION: ("wall_1", "wall_2", "floor"),
    LAYER_AMBIENCE: ("floor", "wall_2", "wall_1"),
}

# Scenario keys that may carry a Lumur layout override. Anything else is ignored.
LAYOUT_SECTION_KEYS: frozenset[str] = frozenset(
    {
        "lumur_layout",
        "lumur_story_stage",
        "lumur_surfaces",
    }
)


@dataclass(frozen=True)
class SafeArea:
    """Normalised inset (0..1) for content placement on a surface texture."""

    left: float = 0.0
    right: float = 0.0
    top: float = 0.0
    bottom: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "left": float(self.left),
            "right": float(self.right),
            "top": float(self.top),
            "bottom": float(self.bottom),
        }


DEFAULT_SAFE_AREAS: dict[str, SafeArea] = {
    LAYER_BACKDROP: SafeArea(left=0.0, right=0.0, top=0.0, bottom=0.0),
    LAYER_CHARACTER: SafeArea(left=0.1, right=0.1, top=0.05, bottom=0.15),
    LAYER_CLIP: SafeArea(left=0.1, right=0.1, top=0.05, bottom=0.15),
    # Captions occupy a lower wall region (PRD: captions → wall region).
    LAYER_CAPTION: SafeArea(left=0.05, right=0.05, top=0.72, bottom=0.04),
    LAYER_AMBIENCE: SafeArea(left=0.0, right=0.0, top=0.0, bottom=0.0),
}


@dataclass
class StoryStageLayout:
    """Resolved layer → preferred surface-role chains + safe areas."""

    preferences: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {k: tuple(v) for k, v in DEFAULT_PREFERENCES.items()}
    )
    safe_areas: dict[str, SafeArea] = field(
        default_factory=lambda: dict(DEFAULT_SAFE_AREAS)
    )
    # Explicit single-role overrides from a scenario (before fallback).
    overrides: dict[str, str] = field(default_factory=dict)

    def preference_for(self, layer: str) -> tuple[str, ...]:
        canonical = canonical_layer(layer)
        if canonical in self.overrides:
            preferred = self.overrides[canonical]
            rest = [r for r in self.preferences.get(canonical, ()) if r != preferred]
            return (preferred, *rest)
        return self.preferences.get(canonical, DEFAULT_PREFERENCES.get(canonical, ("floor",)))

    def safe_area_for(self, layer: str) -> SafeArea:
        return self.safe_areas.get(canonical_layer(layer), SafeArea())

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferences": {k: list(v) for k, v in self.preferences.items()},
            "overrides": dict(self.overrides),
            "safe_areas": {k: v.as_dict() for k, v in self.safe_areas.items()},
        }


def canonical_layer(name: str) -> str:
    key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
    return LAYER_ALIASES.get(key, key)


def parse_safe_area(raw: Any) -> SafeArea | None:
    if raw is None:
        return None
    if isinstance(raw, SafeArea):
        return raw
    if not isinstance(raw, Mapping):
        return None
    return SafeArea(
        left=float(raw.get("left", 0.0)),
        right=float(raw.get("right", 0.0)),
        top=float(raw.get("top", 0.0)),
        bottom=float(raw.get("bottom", 0.0)),
    )


def layout_from_scenario(scenario: Mapping[str, Any] | None) -> StoryStageLayout:
    """Build a layout from a Synesyn-style scenario dict.

    Only known ``lumur_*`` layout sections are read. All other sections
    (``vis_story``, ``lull_protocol``, ``lumur_audience``, …) are ignored
    without error (REQ-002-010).
    """
    layout = StoryStageLayout()
    if not scenario:
        return layout

    section: Mapping[str, Any] | None = None
    for key, value in scenario.items():
        if str(key).strip().lower() in LAYOUT_SECTION_KEYS and isinstance(value, Mapping):
            section = value
            break
    if section is None:
        return layout

    # enabled: false → still return defaults (bridge stays safe); no hard fail.
    enabled = str(section.get("enabled", "true")).lower()
    if enabled in ("0", "false", "no", "off"):
        return layout

    mapping = section.get("layout", section.get("surfaces", section))
    if isinstance(mapping, Mapping):
        for raw_layer, raw_role in mapping.items():
            layer = canonical_layer(str(raw_layer))
            if layer not in CANONICAL_LAYERS:
                continue
            if isinstance(raw_role, (list, tuple)):
                roles = tuple(str(r) for r in raw_role if str(r).strip())
                if roles:
                    layout.preferences[layer] = roles
                    layout.overrides[layer] = roles[0]
            elif isinstance(raw_role, (str, int)):
                role = str(raw_role).strip()
                if role and role.lower() not in (
                    "enabled",
                    "safe_areas",
                    "layout",
                    "surfaces",
                ):
                    layout.overrides[layer] = role
            # Nested dicts / other types (e.g. mistyped sections) are ignored.

    safe_raw = section.get("safe_areas")
    if isinstance(safe_raw, Mapping):
        for raw_layer, raw_area in safe_raw.items():
            layer = canonical_layer(str(raw_layer))
            if layer not in CANONICAL_LAYERS:
                continue
            area = parse_safe_area(raw_area)
            if area is not None:
                layout.safe_areas[layer] = area

    return layout


def resolve_surface_role(
    layer: str,
    available_roles: Mapping[str, int] | set[str] | list[str],
    layout: StoryStageLayout | None = None,
) -> str | None:
    """Pick the first preferred surface role present in the room.

    Returns ``None`` when the room has no candidate surface (caller should
    skip painting that layer — projection continues for the rest).
    """
    layout = layout or StoryStageLayout()
    if isinstance(available_roles, Mapping):
        present = {str(k) for k in available_roles.keys()}
    else:
        present = {str(k) for k in available_roles}

    for role in layout.preference_for(layer):
        if role in present:
            return role
    return None


def resolve_all_layers(
    available_roles: Mapping[str, int] | set[str] | list[str],
    layout: StoryStageLayout | None = None,
    layers: tuple[str, ...] = CANONICAL_LAYERS,
) -> dict[str, str | None]:
    """Map each canonical layer to a surface role or ``None`` (missing)."""
    return {
        layer: resolve_surface_role(layer, available_roles, layout) for layer in layers
    }
