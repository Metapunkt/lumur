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
            "a projector. Patterns are shown fullscreen via OpenCV (ADR 0010)."
        ),
    )
    p.add_argument("--camera", default="0", help="camera index or device path")
    p.add_argument("--camera-width", type=int, default=None)
    p.add_argument("--camera-height", type=int, default=None)
    p.add_argument("--projector-width", type=int, required=True)
    p.add_argument("--projector-height", type=int, required=True)
    p.add_argument(
        "--monitor",
        type=int,
        default=1,
        help="display index hint for the projector (OpenCV moveWindow)",
    )
    p.add_argument("--settle-ms", type=int, default=200)
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
    from lumur.capture.camera import OpenCVCamera, to_gray
    from lumur.capture.display import OpenCVFullscreenDisplay
    from lumur.capture.loop import CaptureLoop
    from lumur.decode.graycode import decode_graycode
    from lumur.patterns.graycode import generate_graycode_sequence
    from lumur.schema.calibration import build_calibration_document, save_calibration

    device = _parse_device(args.camera)
    camera = OpenCVCamera(device, width=args.camera_width, height=args.camera_height)
    lock = camera.lock_exposure_and_wb()
    display = OpenCVFullscreenDisplay(monitor_index=args.monitor)

    try:
        sequence = generate_graycode_sequence(
            args.projector_width, args.projector_height
        )
        loop = CaptureLoop(
            camera,
            display,
            settle_s=args.settle_ms / 1000.0,
            validate_identity=not args.skip_identity_check,
        )
        print(
            f"projecting {len(sequence.frames)} Gray-code frames "
            f"({args.projector_width}x{args.projector_height})…",
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
        projector_size = (args.projector_width, args.projector_height)

        if args.board:
            cols_s, rows_s = args.board.lower().split("x")
            board_size = (int(cols_s), int(rows_s))
            # Fresh grab of the board under ambient / last pattern — caller
            # should illuminate the board; use the last capture as a stand-in
            # only when a dedicated board image is unavailable.
            board_image = to_gray(camera.grab())
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
            result = calibrate_plane_with_measured_distance(
                corr,
                camera_size=(cam_w, cam_h),
                projector_size=projector_size,
                point_a_cam=_parse_uv(args.point_a),
                point_b_cam=_parse_uv(args.point_b),
                distance_m=args.distance_m,
            )

        doc = build_calibration_document(
            result,
            projector_size=projector_size,
            notes={
                "camera_lock": {
                    "exposure_locked": lock.exposure_locked,
                    "white_balance_locked": lock.white_balance_locked,
                    "notes": lock.notes,
                }
            },
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
        display.close()
        camera.release()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())