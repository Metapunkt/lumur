"""Umbrella ``lumur`` console command; old script names remain as aliases."""

from __future__ import annotations

import argparse
import sys


_COMMANDS = {
    "calibrate": ("lumur.cli", "main"),
    "scan": ("lumur.cli_scan", "main"),
    "export-godot": ("lumur.cli_export_godot", "main"),
    "track": ("lumur.cli_track", "main"),
    "generate": ("lumur.cli_generate", "main"),
    "app": ("lumur.cli_app", "main"),
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur",
        description=(
            "Lumur companion umbrella. Subcommands mirror the dedicated "
            "console scripts (lumur-calibrate, lumur-scan, …)."
        ),
    )
    p.add_argument(
        "command",
        choices=sorted(_COMMANDS),
        help="subcommand to run",
    )
    p.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="arguments passed to the subcommand (use -- to disambiguate)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        build_parser().print_help()
        return 0
    command = argv[0]
    rest = argv[1:]
    if rest and rest[0] == "--":
        rest = rest[1:]
    if command not in _COMMANDS:
        print(
            f"unknown command {command!r}; choose from: {', '.join(sorted(_COMMANDS))}",
            file=sys.stderr,
        )
        return 2
    module_name, attr = _COMMANDS[command]
    import importlib

    module = importlib.import_module(module_name)
    return int(getattr(module, attr)(rest))


if __name__ == "__main__":
    raise SystemExit(main())
