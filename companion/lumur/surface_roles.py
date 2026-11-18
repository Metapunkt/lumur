"""Shared surface-role helpers (leaf module — no paint/app imports).

``assign_surface_roles`` and ``build_role_index`` are used by both the Godot
paint export and ``RoomServices``. Keeping them here breaks the cycle
``paint.export → app.metrics → app.__init__ → room_services → paint.export``.
"""

from __future__ import annotations

import re
from typing import Any

_WALL_LABEL_RE = re.compile(r"^wall_\d+$")


def build_role_index(roles: dict[int, list[str]]) -> dict[str, int]:
    """First writer wins so sequential ``wall_n`` / ``floor`` stay stable."""
    index: dict[str, int] = {}
    for pid, role_list in sorted(roles.items(), key=lambda kv: kv[0]):
        for role in role_list:
            index.setdefault(role, pid)
    return index


def assign_surface_roles(planes: list[dict[str, Any]]) -> dict[int, list[str]]:
    """Map plane_id → role names (``floor``, ``wall_1`` …, plus safe labels).

    Scan wall labels look like ``wall_{plane_id}``, which collides with the
    sequential ``wall_n`` roles apps are meant to use. Prefer sequential
    roles; only attach the raw label when it does not steal a ``wall_n`` name.
    """
    roles: dict[int, list[str]] = {}
    walls = sorted(
        [p for p in planes if p.get("kind") == "wall"],
        key=lambda p: int(p["plane_id"]),
    )
    wall_index = {int(p["plane_id"]): i + 1 for i, p in enumerate(walls)}

    for p in planes:
        pid = int(p["plane_id"])
        names: list[str] = []
        kind = p.get("kind")
        label = str(p.get("label") or f"surface_{pid}")
        if kind == "floor":
            names.append("floor")
        elif kind == "wall":
            names.append(f"wall_{wall_index[pid]}")
        if label not in names:
            # Scan labels use wall_{plane_id}; prefix those so they never steal
            # sequential wall_n roles apps are supposed to call.
            if _WALL_LABEL_RE.match(label):
                names.append(f"label:{label}")
            else:
                names.append(label)
        # De-duplicate while preserving order.
        seen: set[str] = set()
        uniq: list[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                uniq.append(n)
        roles[pid] = uniq
    return roles
