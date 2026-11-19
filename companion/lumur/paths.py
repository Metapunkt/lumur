"""Filesystem helpers for locating the Lumur repository root."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: str | Path | None = None) -> Path:
    """Walk parents looking for ``project.godot`` + ``apps/``.

    Tries ``start`` (if given), this package's install path, then cwd.
    Raises ``FileNotFoundError`` when nothing matches.
    """
    candidates: list[Path] = []
    if start is not None:
        candidates.append(Path(start).resolve())
    # companion/lumur/paths.py → repo root is parents[2] for an editable checkout.
    candidates.append(Path(__file__).resolve())
    candidates.append(Path.cwd().resolve())

    seen: set[Path] = set()
    for origin in candidates:
        for path in (origin, *origin.parents):
            if path in seen:
                continue
            seen.add(path)
            if (path / "project.godot").is_file() and (path / "apps").is_dir():
                return path
    raise FileNotFoundError(
        "could not locate Lumur repo root (expected project.godot and apps/)"
    )
