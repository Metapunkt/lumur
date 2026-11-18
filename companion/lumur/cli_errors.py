"""Shared friendly CLI error handling for Lumur console scripts."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any


class CliError(Exception):
    """User-facing CLI failure with an optional hint line."""

    def __init__(self, message: str, *, hint: str | None = None, code: int = 2):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code


def preset_names() -> list[str]:
    try:
        from lumur.sim import list_presets

        return list(list_presets())
    except Exception:
        return ["empty_room", "room_with_box", "noisy_room", "room_with_walkers"]


def format_presets() -> str:
    return ", ".join(preset_names())


def run_cli(main: Callable[[list[str] | None], int], argv: list[str] | None = None) -> int:
    """Wrap a CLI ``main`` so known failures print hints instead of tracebacks."""
    try:
        return int(main(argv))
    except CliError as exc:
        print(exc.message, file=sys.stderr)
        if exc.hint:
            print(exc.hint, file=sys.stderr)
        return int(exc.code)
    except FileNotFoundError as exc:
        msg = str(exc)
        low = msg.lower()
        # Mistyped --scene / missing preset: never suggest lumur-scan.
        if "unknown preset" in low or (
            "available:" in low and ("preset" in low or "scene" in low)
        ):
            print(msg, file=sys.stderr)
            print(
                f"unknown scene — available presets: {format_presets()}",
                file=sys.stderr,
            )
            return 2
        path = getattr(exc, "filename", None) or msg
        print(f"not found: {path}", file=sys.stderr)
        lower = str(path).lower()
        if "calibrat" in lower or str(path).endswith(".json"):
            print(
                "hint: run lumur-calibrate first, then pass --calibration <file>",
                file=sys.stderr,
            )
        elif "godot" in lower or (
            "room" in lower and "typo" not in lower and "preset" not in lower
        ):
            print(
                "hint: run lumur-scan -o <dir>, then lumur-export-godot <dir>",
                file=sys.stderr,
            )
        return 2
    except ConnectionError as exc:
        print(f"unreachable: {exc}", file=sys.stderr)
        print(
            "hint: check --comfy-url / --hub-url, or use --backend sim for hardware-free capture",
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        # Camera open failures, etc.
        err = str(exc).lower()
        print(f"device error: {exc}", file=sys.stderr)
        if "camera" in err or "video" in err or "device" in err:
            print(
                "hint: no camera? try --backend sim --scene empty_room",
                file=sys.stderr,
            )
        return 2
    except RuntimeError as exc:
        err = str(exc).lower()
        print(f"error: {exc}", file=sys.stderr)
        if "camera" in err or "could not open" in err or "video" in err:
            print(
                "hint: no camera? try --backend sim --scene empty_room",
                file=sys.stderr,
            )
            return 2
        return 1
    except ValueError as exc:
        msg = str(exc)
        print(msg, file=sys.stderr)
        low = msg.lower()
        if "scene" in low or "preset" in low:
            print(
                f"unknown scene — available presets: {format_presets()}",
                file=sys.stderr,
            )
        elif "camera" in low:
            print(
                "hint: no camera? try --backend sim --scene empty_room",
                file=sys.stderr,
            )
        return 2


def require_path(path: Any, *, kind: str) -> None:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        if kind == "calibration":
            raise CliError(
                f"calibration not found: {p}",
                hint="hint: run lumur-calibrate … -o cal.json, then pass --calibration cal.json",
            )
        if kind == "room":
            raise CliError(
                f"room package not found: {p}",
                hint="hint: run lumur-scan -o <dir> (then lumur-export-godot <dir> for Godot assets)",
            )
        raise CliError(f"not found: {p}")


def warn_scene_mismatch(calibration: dict, scan_scene: str | None) -> None:
    """Warn when calibration notes.scene differs from the scan --scene."""
    if not scan_scene:
        return
    notes = calibration.get("notes") if isinstance(calibration, dict) else None
    if not isinstance(notes, dict):
        return
    cal_scene = notes.get("scene")
    if cal_scene is None:
        return
    if str(cal_scene) != str(scan_scene):
        print(
            f"warning: calibration scene {cal_scene!r} differs from scan scene "
            f"{scan_scene!r}; metric fit may degrade",
            file=sys.stderr,
        )
