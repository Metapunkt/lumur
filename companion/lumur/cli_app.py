"""CLI: validate / fit / list / run app manifests (PRD-003)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur-app",
        description="App manifest helpers: check, fit, list, and headless run.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate a lumur.app manifest JSON")
    check.add_argument("manifest", type=Path)

    fit = sub.add_parser("fit", help="fit a manifest to a scanned room package")
    fit.add_argument("manifest", type=Path)
    fit.add_argument(
        "--room",
        "-r",
        type=Path,
        required=True,
        help="room package directory (after lumur-scan / export)",
    )

    list_p = sub.add_parser(
        "list",
        help="list startable apps under apps/ (and optional roots)",
    )
    list_p.add_argument(
        "--root",
        action="append",
        default=[],
        type=Path,
        help="extra app root to scan (repeatable)",
    )
    list_p.add_argument(
        "--bridge",
        action="store_true",
        help="include bridge-only apps (lumur_synesyn)",
    )
    list_p.add_argument(
        "--room",
        "-r",
        type=Path,
        default=None,
        help="optional room package — only list apps that fit",
    )

    run = sub.add_parser(
        "run",
        help="headless install+launch via AppLifecycle (no Godot window)",
    )
    run.add_argument("manifest", type=Path)
    run.add_argument("--room", "-r", type=Path, required=True)
    return p


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from lumur.cli_errors import CliError, require_path
    from lumur.schema.app import load_app_manifest, validate_app_manifest

    if args.command == "check":
        require_path(args.manifest, kind="manifest")
        doc = load_app_manifest(args.manifest)
        validate_app_manifest(doc)
        print(json.dumps({"ok": True, "id": doc.get("id"), "name": doc.get("name")}, indent=2))
        return 0

    if args.command == "fit":
        require_path(args.manifest, kind="manifest")
        require_path(args.room, kind="room")
        from lumur.app.fit import fit_app_to_room
        from lumur.app.room_services import RoomServices

        doc = load_app_manifest(args.manifest)
        room = RoomServices.load(args.room)
        result = fit_app_to_room(doc, room)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.ok else 1

    if args.command == "list":
        from lumur.app.fit import fit_app_to_room
        from lumur.app.generation import bridge_app_roots, bundled_app_roots
        from lumur.app.room_services import RoomServices

        roots = list(bundled_app_roots())
        if args.bridge:
            roots.extend(bridge_app_roots())
        roots.extend(args.root or [])
        room = None
        if args.room:
            require_path(args.room, kind="room")
            room = RoomServices.load(args.room)
        found: list[dict] = []
        for root in roots:
            root = Path(root)
            if not root.is_dir():
                continue
            for man in sorted(root.rglob("lumur.app.json")):
                try:
                    doc = load_app_manifest(man)
                    validate_app_manifest(doc)
                except Exception as exc:
                    found.append({"path": str(man), "ok": False, "error": str(exc)})
                    continue
                entry = {
                    "path": str(man),
                    "id": doc.get("id"),
                    "name": doc.get("name"),
                    "bridge": doc.get("bridge"),
                    "ok": True,
                }
                if room is not None:
                    fit = fit_app_to_room(doc, room)
                    entry["fits"] = fit.ok
                    if not fit.ok:
                        entry["unmet"] = [u.to_dict() for u in fit.unmet]
                found.append(entry)
        print(json.dumps({"apps": found}, indent=2))
        return 0

    if args.command == "run":
        require_path(args.manifest, kind="manifest")
        require_path(args.room, kind="room")
        from lumur.app.compositor import Compositor
        from lumur.app.fit import fit_app_to_room
        from lumur.app.input_bus import AppInputBus
        from lumur.app.lifecycle import AppLifecycle, AppState
        from lumur.app.room_services import RoomServices

        doc = load_app_manifest(args.manifest)
        room = RoomServices.load(args.room)
        fit = fit_app_to_room(doc, room)
        if not fit.ok:
            raise CliError(
                f"app does not fit room: {fit.unmet}",
                hint="hint: lumur-app fit <manifest> --room <dir>",
                code=1,
            )
        life = AppLifecycle()
        life.setup(room, AppInputBus(), Compositor())
        app_id = str(doc["id"])
        life.install(doc, source_path=str(args.manifest))
        life.launch(app_id)
        rec = life.get(app_id)
        state = rec.state.value if isinstance(rec.state, AppState) else str(rec.state)
        print(json.dumps({"ok": True, "id": app_id, "state": state, "fit": fit.to_dict()}, indent=2))
        return 0

    raise CliError(f"unknown command {args.command!r}")


def main(argv: list[str] | None = None) -> int:
    from lumur.cli_errors import run_cli

    return run_cli(_main, argv)


if __name__ == "__main__":
    raise SystemExit(main())
