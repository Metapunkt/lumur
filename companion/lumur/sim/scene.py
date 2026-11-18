"""Scene file loading (JSON / optional YAML) and built-in presets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from lumur.sim.devices import VirtualCamera, VirtualProjector
from lumur.sim.geometry import Box, OccupantPlaceholder
from lumur.sim.people import PeopleSim, people_from_config
from lumur.sim.room import Room, make_axis_room

PRESETS_DIR = Path(__file__).resolve().parent / "presets"


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def preset_path(name: str) -> Path:
    path = PRESETS_DIR / f"{name}.json"
    if not path.is_file():
        known = ", ".join(list_presets()) or "(none)"
        raise FileNotFoundError(f"unknown preset {name!r}; available: {known}")
    return path


def _load_raw(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load .yaml/.yml scene files; "
                "use JSON or pip install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("scene YAML root must be a mapping")
        return data
    # Try JSON first, then YAML.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise ValueError(
                f"unsupported scene format for {path}; use .json or install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError("scene root must be a mapping")
        return data


def _vec3(value: Any, default: list[float] | None = None) -> np.ndarray:
    if value is None:
        if default is None:
            raise ValueError("missing vec3")
        value = default
    arr = np.asarray(value, dtype=np.float64).reshape(3)
    return arr


class SimScene:
    """Parsed simulation scene: room + virtual devices."""

    def __init__(
        self,
        room: Room,
        camera: VirtualCamera,
        projector: VirtualProjector,
        *,
        name: str = "scene",
        meta: dict[str, Any] | None = None,
    ):
        self.room = room
        self.camera = camera
        self.projector = projector
        self.name = name
        self.meta = meta or {}


def _build_room(cfg: dict[str, Any]) -> Room:
    room_cfg = cfg.get("room", {})
    if room_cfg.get("type", "axis") == "axis":
        room = make_axis_room(
            width=float(room_cfg.get("width", 4.0)),
            depth=float(room_cfg.get("depth", 4.0)),
            height=float(room_cfg.get("height", 2.5)),
            floor_albedo=float(room_cfg.get("floor_albedo", 0.65)),
            wall_albedo=float(room_cfg.get("wall_albedo", 0.8)),
            include_ceiling=bool(room_cfg.get("include_ceiling", False)),
            include_side_walls=bool(room_cfg.get("include_side_walls", True)),
        )
    else:
        room = Room()
        for plane_cfg in room_cfg.get("planes", []):
            from lumur.sim.geometry import Plane

            room.planes.append(
                Plane.from_point_normal(
                    _vec3(plane_cfg["point"]),
                    _vec3(plane_cfg["normal"]),
                    albedo=float(plane_cfg.get("albedo", 0.75)),
                    name=str(plane_cfg.get("name", "plane")),
                )
            )

    for box_cfg in room_cfg.get("boxes", []):
        room.boxes.append(
            Box(
                center=_vec3(box_cfg["center"]),
                size=_vec3(box_cfg["size"]),
                albedo=float(box_cfg.get("albedo", 0.55)),
                name=str(box_cfg.get("name", "box")),
            )
        )
    for occ_cfg in room_cfg.get("occupants", []):
        room.occupants.append(
            OccupantPlaceholder(
                center=_vec3(occ_cfg["center"]),
                height=float(occ_cfg.get("height", 1.7)),
                radius=float(occ_cfg.get("radius", 0.25)),
                albedo=float(occ_cfg.get("albedo", 0.35)),
                name=str(occ_cfg.get("name", "occupant")),
            )
        )
    people_cfg = room_cfg.get("people")
    if people_cfg:
        room.people = people_from_config(list(people_cfg))
    return room


def _build_projector(cfg: dict[str, Any]) -> VirtualProjector:
    p = cfg["projector"]
    kwargs: dict[str, Any] = {
        "width": int(p["width"]),
        "height": int(p["height"]),
        "eye": _vec3(p["eye"]),
        "target": _vec3(p["target"]),
        "fov_y_deg": float(p.get("fov_y_deg", 40.0)),
        "gamma": float(p.get("gamma", 2.2)),
    }
    if "up" in p:
        kwargs["up"] = _vec3(p["up"])
    if "K" in p:
        kwargs["K"] = np.asarray(p["K"], dtype=np.float64)
    return VirtualProjector.from_look_at(**kwargs)


def _build_camera(cfg: dict[str, Any]) -> VirtualCamera:
    c = cfg["camera"]
    kwargs: dict[str, Any] = {
        "width": int(c["width"]),
        "height": int(c["height"]),
        "eye": _vec3(c["eye"]),
        "target": _vec3(c["target"]),
        "fov_y_deg": float(c.get("fov_y_deg", 55.0)),
        "exposure": float(c.get("exposure", 1.0)),
        "noise_std": float(c.get("noise_std", 0.0)),
        "ambient": float(c.get("ambient", 0.0)),
        "blur_sigma": float(c.get("blur_sigma", 0.0)),
        "seed": int(c.get("seed", cfg.get("seed", 0))),
    }
    if "up" in c:
        kwargs["up"] = _vec3(c["up"])
    if "K" in c:
        kwargs["K"] = np.asarray(c["K"], dtype=np.float64)
    if "distortion" in c:
        kwargs["distortion"] = np.asarray(c["distortion"], dtype=np.float64)
    return VirtualCamera.from_look_at(**kwargs)


def load_scene(path: str | Path) -> SimScene:
    """Load a scene description from JSON or YAML."""
    path = Path(path)
    if not path.is_file():
        # Allow bare preset names.
        try:
            path = preset_path(str(path))
        except FileNotFoundError:
            raise FileNotFoundError(f"scene file not found: {path}") from None
    cfg = _load_raw(path)
    return SimScene(
        room=_build_room(cfg),
        camera=_build_camera(cfg),
        projector=_build_projector(cfg),
        name=str(cfg.get("name", path.stem)),
        meta={k: v for k, v in cfg.items() if k not in ("room", "camera", "projector")},
    )


def load_preset(name: str) -> SimScene:
    return load_scene(preset_path(name))
