"""Surface generation: provider interface + standalone ComfyUI (PRD-002 slice 1).

Aligned by convention with Synesyn's ``SynesynRenderRequestV1`` / tagged
workflow presets so authors can move presets between Lumur and SynPunkt.
This package must not import Synesyn.
"""

from __future__ import annotations

from lumur.generate.comfy_provider import ComfyUISurfaceGenerator
from lumur.generate.jobs import GenerationJob, JobRunner
from lumur.generate.provider import NullSurfaceGenerator, SurfaceGenerator
from lumur.generate.types import (
    JobStatus,
    SurfaceRenderRequest,
    SurfaceRenderResult,
)

__all__ = [
    "ComfyUISurfaceGenerator",
    "GenerationJob",
    "JobRunner",
    "JobStatus",
    "NullSurfaceGenerator",
    "SurfaceGenerator",
    "SurfaceRenderRequest",
    "SurfaceRenderResult",
]
