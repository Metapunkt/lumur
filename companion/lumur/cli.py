"""Command-line entry for live Gray-code calibration."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur-calibrate",
        description=(
            "Run Gray-code structured-light calibration between a webcam and "
            "a projector. Patterns are shown fullscreen via OpenCV (ADR 0010) "
            "or through the simulated rig (ADR 0011)."
        ),
    )
    p.add_argument(
        "--backend",
        choices=("opencv", "sim"),
        default="opencv",
        help="device backend: real OpenCV camera/display, or simulated rig",
    )
    p.add_argument(
        "--scene",
        default=None,
        help=(
            "sim scene JSON/YAML path or preset name "
            "(empty_room, room_with_box, noisy_room); required for --backend sim"
        ),
    )
    p.add_argument("--camera", default="0", help="camera index or device path")
    p.add_argument("--camera-width", type=int, default=None)
    p.add_argument("--camera-height", type=int, default=None)
    p.add_argument(
        "--projector-width",
        type=int,
        default=None,
        help="projector width (required for opencv; defaults from scene for sim)",
    )
    p.add_argument(
        "--projector-height",
        type=int,
        default=None,
        help="projector height (required for opencv; defaults from scene for sim)",
    )
    p.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="display index hint for the projector (OpenCV moveWindow)",
    )
    p.add_argument("--settle-ms", type=int, default=None, help="default 200 (opencv) or 0 (sim)")
    p.add_argument("--contrast-threshold", type=float, default=15.0)
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("calibration.json"),
        help="versioned calibration JSON path",
    )
    p.add_argument(
        "--correspondence-out",
        type=Path,
        default=None,
        help="optional .npz path for the dense correspondence map",
    )
    p.add_argument(
        "--board",
        default=None,
        help="optional checkerboard interior corners as COLSxROWS, e.g. 9x6",
    )
    p.add_argument(
        "--square-m",
        type=float,
        default=0.025,
        help="checkerboard square size in metres",
    )
    p.add_argument(
        "--distance-m",
        type=float,
        default=None,
        help="measured distance between --point-a and --point-b (no-board scale)",
    )
    p.add_argument(
        "--point-a",
        default=None,
        help="camera pixel u,v for measured-distance endpoint A",
    )
    p.add_argument(
        "--point-b",
        default=None,
        help="camera pixel u,v for measured-distance endpoint B",
    )
    p.add_argument(
        "--skip-identity-check",
        action="store_true",
        help="do not require consecutive patterns to change the camera image",
    )
    return p


def _parse_device(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def _parse_uv(value: str) -> tuple[float, float]:
    u, v = value.split(",")
    return float(u), float(v)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from lumur.calibrate.geometry import (
        calibrate_plane_with_measured_distance,
        calibrate_with_checkerboard,
    )
    from lumur.capture.backends import open_devices
    from lumur.capture.camera import to_gray
    from lumur.capture.loop import CaptureLoop
    from lumur.decode.graycode import decode_graycode
    from lumur.patterns.graycode import generate_graycode_sequence
    from lumur.schema.calibration import build_calibration_document, save_calibration

    devices = open_devices(
        args.backend,
        camera=_parse_device(args.camera),
        camera_width=args.camera_width,
        camera_height=args.camera_height,
        monitor_index=args.monitor,
        scene=args.scene,
    )
    lock = devices.lock_exposure_and_wb()

    if args.projector_width is None or args.projector_height is None:
        if devices.projector_size is None:
            print(
                "--projector-width and --projector-height are required "
                "unless --backend sim provides them via --scene",
                file=sys.stderr,
            )
            devices.close()
            return 2
        proj_w, proj_h = devices.projector_size
    else:
        proj_w, proj_h = args.projector_width, args.projector_height
        if devices.projector_size is not None and devices.projector_size != (
            proj_w,
            proj_h,
        ):
            print(
                f"warning: --projector size {proj_w}x{proj_h} differs from scene "
                f"{devices.projector_size[0]}x{devices.projector_size[1]}; "
                f"using CLI values for pattern generation",
                file=sys.stderr,
            )

    settle_ms = args.settle_ms
    if settle_ms is None:
        settle_ms = 0 if args.backend == "sim" else 200

    try:
        sequence = generate_graycode_sequence(proj_w, proj_h)
        loop = CaptureLoop(
            devices.camera,
            devices.display,
            settle_s=settle_ms / 1000.0,
            validate_identity=not args.skip_identity_check,
            discard_warmup_grabs=0 if args.backend == "sim" else 1,
        )
        print(
            f"projecting {len(sequence.frames)} Gray-code frames "
            f"({proj_w}x{proj_h}) via backend={args.backend}…",
            file=sys.stderr,
        )
        captures = loop.capture_sequence(sequence)
        corr = decode_graycode(
            captures, sequence, contrast_threshold=args.contrast_threshold
        )
        print(
            f"decoded correspondence: valid_fraction={corr.valid_fraction:.3f}",
            file=sys.stderr,
        )

        cam_w = captures[0].image.shape[1]
        cam_h = captures[0].image.shape[0]
        projector_size = (proj_w, proj_h)

        if args.board:
            cols_s, rows_s = args.board.lower().split("x")
            board_size = (int(cols_s), int(rows_s))
            board_image = to_gray(devices.camera.grab())
            result = calibrate_with_checkerboard(
                corr,
                board_image,
                board_size=board_size,
                square_size_m=args.square_m,
                projector_size=projector_size,
            )
        else:
            if args.distance_m is None or not args.point_a or not args.point_b:
                print(
                    "no-board path requires --distance-m, --point-a and --point-b "
                    "(or pass --board COLSxROWS)",
                    file=sys.stderr,
                )
                return 2
            calib_kwargs = {}
            if devices.rig is not None:
                # Prefer true camera intrinsics when running against the sim.
                calib_kwargs["camera_matrix"] = devices.rig.scene.camera.K
                calib_kwargs["camera_distortion"] = devices.rig.scene.camera.distortion
            result = calibrate_plane_with_measured_distance(
                corr,
                camera_size=(cam_w, cam_h),
                projector_size=projector_size,
                point_a_cam=_parse_uv(args.point_a),
                point_b_cam=_parse_uv(args.point_b),
                distance_m=args.distance_m,
                **calib_kwargs,
            )

        notes = {
            "backend": args.backend,
            "camera_lock": {
                "exposure_locked": bool(getattr(lock, "exposure_locked", False)),
                "white_balance_locked": bool(
                    getattr(lock, "white_balance_locked", False)
                ),
                "notes": list(getattr(lock, "notes", []) or []),
            },
        }
        if args.scene:
            notes["scene"] = str(args.scene)

        doc = build_calibration_document(
            result,
            projector_size=projector_size,
            notes=notes,
        )
        save_calibration(doc, args.output)
        print(f"wrote {args.output}", file=sys.stderr)
        print(
            json.dumps(
                {
                    "residuals": doc["residuals"],
                    "method": doc["method"],
                    "valid_fraction": doc["correspondence_valid_fraction"],
                },
                indent=2,
            )
        )

        if args.correspondence_out:
            import numpy as np

            args.correspondence_out.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                args.correspondence_out,
                proj_u=corr.proj_u,
                proj_v=corr.proj_v,
                confidence=corr.confidence,
                valid=corr.valid,
            )
            print(f"wrote {args.correspondence_out}", file=sys.stderr)
    finally:
        devices.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
