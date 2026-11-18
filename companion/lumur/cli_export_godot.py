"""CLI: export Godot paint assets from a room package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur-export-godot",
        description=(
            "Export Godot-friendly paint textures + manifest into a lumur.room "
            "package (PNG lookups under godot/; ADR 0013)."
        ),
    )
    p.add_argument(
        "room_package",
        type=Path,
        help="path to an existing room package directory",
    )
    p.add_argument(
        "--confidence-threshold",
        type=float,
        default=0.05,
        help="default confidence threshold recorded in the paint manifest",
    )
    return p


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from lumur.cli_errors import require_path
    from lumur.paint.export import export_godot_paint_assets

    require_path(args.room_package, kind="room")
    out = export_godot_paint_assets(
        args.room_package,
        confidence_threshold=args.confidence_threshold,
    )
    manifest = json.loads((out / "paint_manifest.json").read_text(encoding="utf-8"))
    print(f"wrote Godot paint assets to {out}", file=sys.stderr)
    print(
        json.dumps(
            {
                "godot_dir": str(out),
                "surfaces": len(manifest.get("surfaces") or []),
                "role_index": manifest.get("role_index"),
                "projector_resolution": manifest.get("projector_resolution"),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    from lumur.cli_errors import run_cli

    return run_cli(_main, argv)


if __name__ == "__main__":
    raise SystemExit(main())
