"""CLI: run sim tracking / footstep stream to local UDP (ADR 0014)."""

from __future__ import annotations

import argparse
import time

import numpy as np

from lumur.events.udp_json import EventSender
from lumur.sim import SimRig, default_crossing_people
from lumur.sim.geometry import Plane
from lumur.track.footsteps import FootstepDetector
from lumur.track.pipeline import TrackingPipeline
from lumur.track.pose import OraclePoseDetector
from lumur.track.subtraction import PredictedFrameSubtractor, calibrate_radiometric
from lumur.track.tracker import SimpleByteTracker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Lumur tracking / footstep ripples (sim)")
    p.add_argument("--scene", default="room_with_walkers")
    p.add_argument("--people", type=int, default=2)
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--latency-frames", type=int, default=2)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-send", action="store_true")
    p.add_argument("--project-silhouette", action="store_true",
                   help="Project a fake human silhouette and inject false pose")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    rig = SimRig.from_scene_path(
        args.scene,
        latency_frames=args.latency_frames,
        n_people=args.people,
        frame_dt=1.0 / args.fps,
        retain_color=True,
    )
    if rig.people is None:
        rig.set_people(default_crossing_people(args.people))

    gt = rig.ground_truth()
    cam = rig.scene.camera
    proj = rig.scene.projector

    def predict_fn(pattern):
        return rig.render_buffers(
            pattern=pattern, include_people=False, retain_color=True
        ).image

    def capture_fn(pattern):
        rig.set_pattern(pattern)
        # No lag during calibration.
        old = rig.latency_frames
        rig.latency_frames = 0
        buf = rig.render_buffers(
            pattern=pattern, include_people=False, retain_color=True
        )
        rig.latency_frames = old
        return buf.image

    radio = calibrate_radiometric(
        predict_fn, capture_fn, projector_size=rig.projector_size
    )
    subtractor = PredictedFrameSubtractor.from_sim_ground_truth(
        gt,
        ambient=cam.ambient,
        exposure=cam.exposure,
        gamma=proj.gamma,
        radiometric=radio,
        latency_frames=args.latency_frames,
    )

    floor = next(p for p in rig.scene.room.planes if p.name == "floor")
    detector = OraclePoseDetector(joint_records_fn=rig.ground_truth_joints, seed=0)
    pipeline = TrackingPipeline(
        detector=detector,
        tracker=SimpleByteTracker(match_thresh_px=50.0),
        footstep_detector=FootstepDetector.from_sim(floor, cam),
        subtractor=subtractor,
        frame_dt=1.0 / args.fps,
    )

    sender = None if args.no_send else EventSender(host=args.host, port=args.port)
    pw, ph = rig.projector_size
    silhouette = None
    if args.project_silhouette:
        silhouette = np.zeros((ph, pw, 3), dtype=np.uint8)
        # Rough human blob on the back wall region of the projector.
        cv, cu = ph // 3, pw // 2
        silhouette[max(0, cv - 10) : cv + 14, max(0, cu - 4) : cu + 5] = (220, 220, 220)
        detector.inject_false_person(u=cam.width * 0.55, v=cam.height * 0.35, scale=12.0)

    n_steps = 0
    for i in range(args.frames):
        if silhouette is not None:
            # Pulse the silhouette so subtraction has content to match.
            pat = silhouette if (i % 2 == 0) else (silhouette // 2)
            rig.set_pattern(pat)
            pipeline.push_projector_frame(pat)
        else:
            # Calm dynamic content: soft gradient
            yy, xx = np.mgrid[0:ph, 0:pw]
            phase = i / args.fps
            gray = (80 + 40 * np.sin(xx / 8.0 + phase) * np.cos(yy / 6.0)).astype(
                np.uint8
            )
            pat = np.stack([gray, gray, gray], axis=-1)
            rig.set_pattern(pat)
            pipeline.push_projector_frame(pat)

        frame = rig.render_frame(advance=True)
        result = pipeline.step(frame)
        n_steps += len(result.footsteps)
        if sender is not None:
            for ev in result.footsteps:
                sender.send_footstep(ev)
        if i % 30 == 0:
            print(
                f"frame={i} tracks={len(result.tracks)} "
                f"footsteps_total={len(pipeline.events)} "
                f"rejected={result.rejected_count}"
            )

    if sender is not None:
        sender.close()
    print(f"done frames={args.frames} footsteps={len(pipeline.events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
