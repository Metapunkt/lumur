"""Command-line entry for structured-light room scan."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lumur-scan",
        description=(
            "Run a Gray-code room scan: triangulate a dense point map with "
            "per-pixel confidence, fit floor/wall planes, and write a versioned "
            "room package (ADR 0012)."
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
            "(empty_room, room_with_box, noisy_room, room_with_walkers); "
            "required for --backend sim when capturing live"
        ),
    )
    p.add_argument("--camera", default="0", help="camera index or device path")
    p.add_argument("--camera-width", type=int, default=None)
    p.add_argument("--camera-height", type=int, default=None)
    p.add_argument("--projector-width", type=int, default=None)
    p.add_argument("--projector-height", type=int, default=None)
    p.add_argument("--monitor", type=int, default=1)
    p.add_argument("--settle-ms", type=int, default=None)
    p.add_argument("--contrast-threshold", type=float, default=15.0)
    p.add_argument(
        "--calibration",
        "-c",
        type=Path,
        required=True,
        help="path to lumur.calibration JSON from lumur-calibrate",
    )
    p.add_argument(
        "--correspondence",
        type=Path,
        default=None,
        help=(
            "optional precomputed correspondence .npz "
            "(proj_u, proj_v, confidence, valid); skips live capture when set"
        ),
    )
    p.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("room_package"),
        help="output directory for the versioned room package",
    )
    p.add_argument(
        "--min-confidence",
        type=float,
        default=0.05,
        help="minimum decode/combined confidence for a valid point",
    )
    p.add_argument(
        "--max-reproj-px",
        type=float,
        default=3.0,
        help="maximum triangulation reprojection error in pixels",
    )
    p.add_argument(
        "--plane-threshold-m",
        type=float,
        default=0.04,
        help="RANSAC plane inlier distance in metres",
    )
    p.add_argument(
        "--skip-identity-check",
        action="store_true",
        help="do not require consecutive patterns to change the camera image",
    )
    p.add_argument(
        "--use-sim-gt-pose",
        action="store_true",
        help=(
            "when --backend sim, replace stereo R/T (and optionally intrinsics) "
            "with ground-truth pose from the rig; useful when planar calibration "
            "translation is weakly constrained"
        ),
    )
    return p


def _parse_device(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def _load_correspondence(path: Path):
    import numpy as np

    from lumur.decode.graycode import CorrespondenceMap

    data = np.load(path)
    return CorrespondenceMap(
        proj_u=data["proj_u"],
        proj_v=data["proj_v"],
        confidence=data["confidence"],
        valid=data["valid"].astype(bool),
    )


def _apply_sim_gt_pose(calibration: dict, rig) -> dict:
    """Override stereo (and device intrinsics) with sim ground truth."""
    import copy

    gt = rig.ground_truth()
    doc = copy.deepcopy(calibration)
    doc["camera"]["matrix"] = gt.camera.K.tolist()
    doc["camera"]["distortion"] = gt.camera.distortion.reshape(-1).tolist()
    doc["camera"]["image_size"] = [int(gt.camera.width), int(gt.camera.height)]
    doc["projector"]["matrix"] = gt.projector.K.tolist()
    doc["projector"]["distortion"] = [0.0, 0.0, 0.0, 0.0, 0.0]
    doc["projector"]["image_size"] = [int(gt.projector.width), int(gt.projector.height)]
    doc["stereo"]["R"] = gt.stereo_R.tolist()
    doc["stereo"]["T"] = gt.stereo_T.reshape(-1).tolist()
    doc["notes"] = dict(doc.get("notes") or {})
    doc["notes"]["pose_source"] = "sim_ground_truth"
    return doc


def _main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    from lumur.cli_errors import require_path, warn_scene_mismatch
    from lumur.schema.calibration import load_calibration
    from lumur.scan.pipeline import scan_from_correspondence, write_scan_package

    require_path(args.calibration, kind="calibration")
    calibration = load_calibration(args.calibration)
    warn_scene_mismatch(calibration, args.scene)
    devices = None
    corr = None

    try:
        if args.correspondence is not None:
            corr = _load_correspondence(args.correspondence)
            print(
                f"loaded correspondence from {args.correspondence} "
                f"(valid_fraction={corr.valid_fraction:.3f})",
                file=sys.stderr,
            )
            if args.use_sim_gt_pose:
                if args.backend != "sim" or not args.scene:
                    print(
                        "--use-sim-gt-pose with --correspondence still needs "
                        "--backend sim --scene <preset>",
                        file=sys.stderr,
                    )
                    return 2
                from lumur.capture.backends import open_devices

                devices = open_devices("sim", scene=args.scene)
                calibration = _apply_sim_gt_pose(calibration, devices.rig)
        else:
            from lumur.capture.backends import open_devices
            from lumur.capture.loop import CaptureLoop
            from lumur.decode.graycode import decode_graycode
            from lumur.patterns.graycode import generate_graycode_sequence

            devices = open_devices(
                args.backend,
                camera=_parse_device(args.camera),
                camera_width=args.camera_width,
                camera_height=args.camera_height,
                monitor_index=args.monitor,
                scene=args.scene,
            )
            devices.lock_exposure_and_wb()

            if args.projector_width is None or args.projector_height is None:
                if devices.projector_size is not None:
                    proj_w, proj_h = devices.projector_size
                else:
                    proj_w, proj_h = (
                        int(calibration["projector_resolution"][0]),
                        int(calibration["projector_resolution"][1]),
                    )
            else:
                proj_w, proj_h = args.projector_width, args.projector_height

            settle_ms = args.settle_ms
            if settle_ms is None:
                settle_ms = 0 if args.backend == "sim" else 200

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
            if args.use_sim_gt_pose:
                if devices.rig is None:
                    print("--use-sim-gt-pose requires --backend sim", file=sys.stderr)
                    return 2
                calibration = _apply_sim_gt_pose(calibration, devices.rig)

        result = scan_from_correspondence(
            corr,
            calibration,
            min_decode_confidence=args.min_confidence,
            max_reprojection_error_px=args.max_reproj_px,
            plane_distance_threshold_m=args.plane_threshold_m,
        )
        notes = {
            "backend": args.backend,
            "calibration_path": str(args.calibration),
        }
        if args.scene:
            notes["scene"] = str(args.scene)
        if args.use_sim_gt_pose:
            notes["pose_source"] = "sim_ground_truth"

        out = write_scan_package(
            result,
            args.output,
            calibration=calibration,
            calibration_ref=str(args.calibration),
            notes=notes,
        )
        print(f"wrote room package to {out}", file=sys.stderr)
        print(json.dumps(result.report.to_dict(), indent=2))
    finally:
        if devices is not None:
            devices.close()

    return 0


def main(argv: list[str] | None = None) -> int:
    from lumur.cli_errors import run_cli

    return run_cli(_main, argv)


if __name__ == "__main__":
    raise SystemExit(main())
