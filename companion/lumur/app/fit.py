"""Bind ``lumur.app`` surface requests to a room package (ADR 0018 allocation).

Slice 1 covers single-app fit: matching, constraints, required fail / optional
null, deterministic preference. Multi-app ownership lives in later slices.

Parity note: Godot mirrors this logic in ``addons/lumur/app_fit.gd``
(``LumurAppFit``). Keep matching rules (role / kind / min_width_m /
min_confidence / required) aligned when changing either side; there is no
automated cross-language parity suite yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from lumur.app.room_services import RoomServices, SurfaceRecord
from lumur.schema.app import validate_app_manifest


@dataclass(frozen=True)
class SurfaceBinding:
    """Concrete binding for one manifest surface request key."""

    key: str
    role_requested: str
    surface_id: int | None
    roles: tuple[str, ...] = ()
    width_m: float | None = None
    mean_confidence: float | None = None
    optional_unmet: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "role_requested": self.role_requested,
            "surface_id": self.surface_id,
            "roles": list(self.roles),
            "width_m": self.width_m,
            "mean_confidence": self.mean_confidence,
            "optional_unmet": self.optional_unmet,
        }


@dataclass(frozen=True)
class UnmetSurface:
    key: str
    role: str
    reason: str
    constraints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "role": self.role,
            "reason": self.reason,
            "constraints": dict(self.constraints),
        }


@dataclass
class FitResult:
    ok: bool
    bindings: dict[str, SurfaceBinding]
    unmet: list[UnmetSurface] = field(default_factory=list)
    app_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "app_id": self.app_id,
            "bindings": {k: v.to_dict() for k, v in self.bindings.items()},
            "unmet": [u.to_dict() for u in self.unmet],
        }


class FitError(ValueError):
    """Hard-fail when a required surface request cannot be met."""

    def __init__(self, message: str, *, result: FitResult):
        super().__init__(message)
        self.result = result


def fit_app_to_room(
    manifest: dict[str, Any],
    room: RoomServices,
    *,
    exclusive_owned: set[int] | None = None,
    share_keys: set[str] | frozenset[str] | None = None,
    raise_on_unmet: bool = True,
) -> FitResult:
    """Allocate distinct room surfaces for each manifest request (manifest order).

    Matching (ADR 0018):
    - ``floor`` exact role / kind
    - ``wall`` matches any ``wall_*`` role or ``kind=wall``
    - a specific label matches that role / label
    - filter by ``min_confidence`` and ``min_width_m`` when present
    - prefer larger ``width_m``, then lower ``surface_id``
    - ``required: true`` (default) with no candidate → hard fail
    - ``required: false`` → bind ``surface_id=None``
    - keys listed in ``share_keys`` (manifest ``shares``) may bind surfaces
      already exclusively owned — compositor claims them as overlays
    """
    validate_app_manifest(manifest)
    owned = set(exclusive_owned or ())
    shares = frozenset(str(k) for k in (share_keys or ()))
    used: set[int] = set()
    bindings: dict[str, SurfaceBinding] = {}
    unmet: list[UnmetSurface] = []

    for req in manifest["surfaces"]:
        key = str(req["key"])
        role = str(req["role"])
        required = bool(req.get("required", True))
        count = int(req.get("count", 1))
        min_width = (
            float(req["min_width_m"]) if req.get("min_width_m") is not None else None
        )
        min_conf = (
            float(req["min_confidence"])
            if req.get("min_confidence") is not None
            else None
        )
        constraints = {
            "min_width_m": min_width,
            "min_confidence": min_conf,
            "count": count,
            "required": required,
        }
        # Overlay-declared keys may reuse a base-owned surface (ADR 0018 shares).
        skip_owned = key not in shares

        assigned: list[SurfaceRecord] = []
        for _ in range(count):
            candidates = [
                s
                for s in room.surfaces
                if s.surface_id not in used
                and (not skip_owned or s.surface_id not in owned)
                and _role_matches(s, role)
                and _passes_constraints(s, min_width=min_width, min_conf=min_conf)
            ]
            candidates.sort(key=lambda s: (-s.width_m, s.surface_id))
            if not candidates:
                break
            pick = candidates[0]
            assigned.append(pick)
            used.add(pick.surface_id)

        if len(assigned) < count:
            reason = "unmet_surface"
            unmet.append(
                UnmetSurface(
                    key=key, role=role, reason=reason, constraints=constraints
                )
            )
            if required:
                result = FitResult(
                    ok=False,
                    bindings=bindings,
                    unmet=unmet,
                    app_id=str(manifest.get("id", "")),
                )
                if raise_on_unmet:
                    raise FitError(
                        f"unmet_surface key={key!r} role={role!r} "
                        f"constraints={constraints}",
                        result=result,
                    )
                return result
            # Optional: bind null for this key (count>1 still one null slot).
            bindings[key] = SurfaceBinding(
                key=key,
                role_requested=role,
                surface_id=None,
                optional_unmet=True,
            )
            continue

        # count == 1 is the common case; count > 1 binds the first under ``key``
        # and additional under ``key#2`` … so callers always get distinct handles.
        for i, surf in enumerate(assigned):
            bind_key = key if i == 0 else f"{key}#{i + 1}"
            bindings[bind_key] = SurfaceBinding(
                key=bind_key,
                role_requested=role,
                surface_id=surf.surface_id,
                roles=surf.roles,
                width_m=surf.width_m,
                mean_confidence=surf.mean_confidence,
            )

    return FitResult(
        ok=True,
        bindings=bindings,
        unmet=unmet,
        app_id=str(manifest.get("id", "")),
    )


def _role_matches(surface: SurfaceRecord, role: str) -> bool:
    role_l = role.strip()
    if not role_l:
        return False
    roles = set(surface.roles)
    if role_l in roles or surface.label == role_l:
        return True
    if role_l == "floor":
        return surface.kind == "floor" or "floor" in roles
    if role_l == "wall":
        if surface.kind == "wall":
            return True
        return any(r == "wall" or r.startswith("wall_") for r in roles)
    return False


def _passes_constraints(
    surface: SurfaceRecord,
    *,
    min_width: float | None,
    min_conf: float | None,
) -> bool:
    if min_width is not None and surface.width_m + 1e-9 < min_width:
        return False
    if min_conf is not None and surface.mean_confidence + 1e-9 < min_conf:
        return False
    return True
