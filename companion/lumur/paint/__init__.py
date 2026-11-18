"""Correspondence-based paint-the-room helpers (export + reference render)."""

from lumur.paint.export import export_godot_paint_assets
from lumur.paint.render import PaintAssignment, paint_projector_image

__all__ = [
    "PaintAssignment",
    "export_godot_paint_assets",
    "paint_projector_image",
]
