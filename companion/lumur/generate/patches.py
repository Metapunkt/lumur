"""Apply Synesyn-style node patches to a ComfyUI API workflow graph."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def apply_patches(workflow: dict[str, Any], patches: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a deep-copied workflow with ``patches`` applied.

    Each patch is ``{"node_id": "3", "input": "seed", "value": 123}``.
    Missing nodes / inputs are created as needed when ``input`` is set.
    """
    out = deepcopy(workflow)
    for patch in patches or []:
        node_id = str(patch.get("node_id") or "").strip()
        input_name = str(patch.get("input") or "").strip()
        if not node_id or not input_name:
            continue
        node = out.setdefault(node_id, {"class_type": "Unknown", "inputs": {}})
        if not isinstance(node, dict):
            continue
        inputs = node.setdefault("inputs", {})
        if not isinstance(inputs, dict):
            inputs = {}
            node["inputs"] = inputs
        inputs[input_name] = patch.get("value")
    return out


def size_patches_for_preset(
    preset: dict[str, Any],
    *,
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    """Build width/height patches declared by a Lumur workflow preset."""
    patches: list[dict[str, Any]] = []
    for entry in list(preset.get("size_patches") or []):
        node_id = str(entry.get("node_id") or "").strip()
        if not node_id:
            continue
        w_in = str(entry.get("width_input") or "width")
        h_in = str(entry.get("height_input") or "height")
        patches.append({"node_id": node_id, "input": w_in, "value": int(width)})
        patches.append({"node_id": node_id, "input": h_in, "value": int(height)})
    return patches
