"""CLI: generate a surface texture via the optional Synesyn Hub provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur-generate-synesyn",
        description=(
            "Generate a surface texture through the Synesyn Hub provider "
            "(ADR 0015 / PRD-002 slice 2). Optional bridge — Lumur core works "
            "without this command. Never blocks the projector render path."
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
        "--hub-url",
        default=None,
        help="Synesyn Hub base URL (or LUMUR_SYNESYN_HUB_URL)",
    )
    p.add_argument(
        "--hub-token",
        default=None,
        help="optional Bearer token (or LUMUR_SYNESYN_HUB_TOKEN); never commit",
    )
    p.add_argument(
        "--hub-auth",
        action="store_true",
        help="send Authorization: Bearer even if token comes from env/config",
    )
    p.add_argument(
        "--comfy-url",
        default=None,
        help="ComfyUI URL the Hub worker should call (routing.comfy_base_url)",
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="optional JSON config (hub.base_url / hub.auth); do not commit tokens",
    )
    p.add_argument("--preset", default=None, help="force json.workflow artifact id")
    p.add_argument("--width", type=int, default=None)
    p.add_argument("--height", type=int, default=None)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--room-id", default=None)
    p.add_argument("--scenario", default=None)
    p.add_argument(
        "--controls",
        choices=("auto", "all", "none"),
        default="auto",
    )
    p.add_argument(
        "--register-room",
        action="store_true",
        help="register room.json as a Hub json.lumur_room artifact before generate",
    )
    p.add_argument(
        "--no-local-fallback",
        action="store_true",
        help="do not fall back to on-disk Lumur presets when Hub has no match",
    )
    p.add_argument("--ping", action="store_true", help="only check Hub /health")
    p.add_argument(
        "--async",
        dest="async_submit",
        action="store_true",
        help="submit and print job id without waiting",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from lumur_synesyn.config import load_hub_config

    try:
        config = load_hub_config(
            hub_url=args.hub_url,
            auth_token=args.hub_token,
            auth_enabled=True if args.hub_auth or args.hub_token else None,
            comfy_url=args.comfy_url,
            config_path=args.config,
            timeout_sec=args.timeout,
        )
    except ValueError as exc:
        print(f"lumur-generate-synesyn: {exc}", file=sys.stderr)
        return 1

    if args.ping:
        from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator

        ping = SynesynHubSurfaceGenerator(config).ping()
        print(json.dumps(ping, indent=2))
        return 0 if ping.get("ok") else 2

    from lumur_synesyn.pipeline import run_hub_generation

    include_controls: bool | None
    if args.controls == "auto":
        include_controls = None
    elif args.controls == "all":
        include_controls = True
    else:
        include_controls = False

    try:
        job = run_hub_generation(
            args.room_package,
            surface=args.surface,
            config=config,
            preset_id=args.preset,
            width=args.width,
            height=args.height,
            wait=not args.async_submit,
            include_controls=include_controls,
            room_id=args.room_id,
            scenario_key=args.scenario,
            register_room=args.register_room,
            fallback_local_presets=not args.no_local_fallback,
        )
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(f"lumur-generate-synesyn: {exc}", file=sys.stderr)
        return 1

    summary = job.to_dict()
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
    print(f"job {job.job_id} {job.status.value}: {job.error}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
