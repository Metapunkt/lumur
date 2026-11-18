"""CLI: generate a surface texture via standalone ComfyUI (PRD-002 slice 1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur-generate",
        description=(
            "Generate a surface texture with the standalone ComfyUI provider "
            "(ADR 0016 / PRD-002 slice 1). Writes into <room>/generated/ and "
            "updates godot/paint_manifest.json when present. Never blocks the "
            "projector render path — this CLI runs beside the runtime."
        ),
    )
    p.add_argument(
        "room_package",
        type=Path,
        help="path to an existing lumur.room package directory",
    )
    p.add_argument(
        "--surface",
        required=True,
        help="surface role or id (e.g. floor, wall_1, 3)",
    )
    p.add_argument(
        "--preset",
        default=None,
        help="workflow preset id (default: best tag match for the surface role)",
    )
    p.add_argument(
        "--preset-dir",
        action="append",
        default=[],
        type=Path,
        help="extra directory of lumur.workflow_preset JSON files (repeatable)",
    )
    p.add_argument(
        "--comfy-url",
        default="http://127.0.0.1:8188",
        help="ComfyUI base URL (direct provider)",
    )
    p.add_argument("--width", type=int, default=None, help="override generation width")
    p.add_argument("--height", type=int, default=None, help="override generation height")
    p.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="ComfyUI poll timeout in seconds",
    )
    p.add_argument(
        "--room-id",
        default=None,
        help="optional lumur:room= scoping tag for preset selection",
    )
    p.add_argument(
        "--scenario",
        default=None,
        help="optional lumur:scenario= scoping tag for preset selection",
    )
    p.add_argument(
        "--controls",
        choices=("auto", "all", "none"),
        default="auto",
        help="control images: auto=preset flags, all=force mask+depth+normal, none=off",
    )
    p.add_argument(
        "--ping",
        action="store_true",
        help="only check ComfyUI reachability, then exit",
    )
    p.add_argument(
        "--async",
        dest="async_submit",
        action="store_true",
        help="submit and print job id without waiting (still uses a worker thread)",
    )
    return p


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from lumur.cli_errors import CliError, require_path

    if args.ping:
        from lumur.generate.comfy_provider import ComfyUISurfaceGenerator

        ping = ComfyUISurfaceGenerator(base_url=args.comfy_url).ping()
        print(json.dumps(ping, indent=2))
        if ping.get("ok"):
            return 0
        raise CliError(
            f"ComfyUI unreachable at {args.comfy_url}",
            hint="hint: start ComfyUI locally, or pass --comfy-url to a reachable host",
        )

    require_path(args.room_package, kind="room")
    from lumur.generate.pipeline import run_generation
    from lumur.generate.presets import default_presets_dir

    include_controls: bool | None
    if args.controls == "auto":
        include_controls = None
    elif args.controls == "all":
        include_controls = True
    else:
        include_controls = False

    preset_dirs = [default_presets_dir(), *list(args.preset_dir or [])]
    try:
        job = run_generation(
            args.room_package,
            surface=args.surface,
            comfy_base_url=args.comfy_url,
            preset_id=args.preset,
            preset_dirs=preset_dirs,
            width=args.width,
            height=args.height,
            timeout_sec=args.timeout,
            wait=not args.async_submit,
            include_controls=include_controls,
            room_id=args.room_id,
            scenario_key=args.scenario,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        msg = str(exc)
        hint = None
        if "comfy" in msg.lower() or "connection" in msg.lower() or "url" in msg.lower():
            hint = f"hint: is ComfyUI running at {args.comfy_url}?"
        raise CliError(f"lumur-generate: {exc}", hint=hint, code=1) from exc

    summary = job.to_dict()
    # Drop nested request bytes-ish noise.
    if summary.get("result") and "meta" in summary["result"]:
        meta = dict(summary["result"]["meta"] or {})
        meta.pop("image_bytes", None)
        summary["result"]["meta"] = meta
    print(json.dumps(summary, indent=2))
    if job.status.value in ("succeeded", "skipped"):
        print(
            f"job {job.job_id} {job.status.value}"
            + (f" → {job.result.image_path}" if job.result and job.result.image_path else ""),
            file=sys.stderr,
        )
        return 0
    err = str(job.error or "")
    if "connect" in err.lower() or "urlopen" in err.lower() or "refused" in err.lower():
        raise CliError(
            f"job {job.job_id} failed: ComfyUI unreachable at {args.comfy_url}",
            hint="hint: start ComfyUI, then retry",
            code=3,
        )
    print(f"job {job.job_id} {job.status.value}: {job.error}", file=sys.stderr)
    return 3


def main(argv: list[str] | None = None) -> int:
    from lumur.cli_errors import run_cli

    return run_cli(_main, argv)


if __name__ == "__main__":
    raise SystemExit(main())
