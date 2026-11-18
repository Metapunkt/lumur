"""E2E: real console scripts calibrate → scan → export → fit on sim presets.

Uses subprocesses so import-order and console-script entry points are covered.
Does **not** inject ground-truth extrinsics — this is the documented CLI path.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from lumur.app.fit import fit_app_to_room
from lumur.app.room_services import RoomServices
from lumur.schema.app import load_app_manifest
from lumur.sim import SimRig

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS = REPO_ROOT / "apps"
PRESETS = ("empty_room", "room_with_box", "noisy_room")

# Documented sim tape-measure endpoints for the 64×48 / 80×60 presets.
POINT_A = "31.2,17.2"
POINT_B = "49.0,22.1"
DISTANCE_M = 1.08


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Prefer the editable install under test.
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("scene", PRESETS)
def test_cli_calibrate_scan_export_fit(tmp_path: Path, scene: str):
    cal = tmp_path / "cal.json"
    room = tmp_path / "room"

    cal_proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli",
            "--backend",
            "sim",
            "--scene",
            scene,
            "--distance-m",
            str(DISTANCE_M),
            "--point-a",
            POINT_A,
            "--point-b",
            POINT_B,
            "-o",
            str(cal),
        ],
        cwd=tmp_path,
    )
    assert cal_proc.returncode == 0, cal_proc.stderr
    assert cal.is_file()

    doc = json.loads(cal.read_text(encoding="utf-8"))
    T = np.asarray(doc["stereo"]["T"], dtype=np.float64)
    gt = SimRig.from_scene_path(scene).ground_truth()
    baseline = float(np.linalg.norm(gt.stereo_T))
    ratio = float(np.linalg.norm(T) / baseline)
    assert 0.90 <= ratio <= 1.10, f"{scene}: baseline scale ratio {ratio:.3f}"

    scan_proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli_scan",
            "--backend",
            "sim",
            "--scene",
            scene,
            "--calibration",
            str(cal),
            "-o",
            str(room),
        ],
        cwd=tmp_path,
    )
    assert scan_proc.returncode == 0, scan_proc.stderr
    assert (room / "room.json").is_file()

    export_proc = _run(
        [sys.executable, "-m", "lumur.cli_export_godot", str(room)],
        cwd=tmp_path,
    )
    assert export_proc.returncode == 0, export_proc.stderr
    assert (room / "godot" / "paint_manifest.json").is_file()

    services = RoomServices.load(room)
    floor = services.surface_by_role("floor")
    assert floor is not None, f"{scene}: missing floor role"

    for app_name in ("paint", "ripples"):
        manifest = load_app_manifest(APPS / app_name / "lumur.app.json")
        min_conf = min(
            float(s.get("min_confidence") or 0.0)
            for s in manifest["surfaces"]
            if s.get("role") == "floor"
        )
        assert floor.mean_confidence >= min_conf, (
            f"{scene}: floor confidence {floor.mean_confidence:.3f} "
            f"< {app_name} min_confidence {min_conf}"
        )
        fit = fit_app_to_room(manifest, services)
        assert fit.ok, f"{scene}: {app_name} fit failed: {fit.unmet}"
