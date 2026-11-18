"""Friendly CLI error mapping (unknown scene, missing camera)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_unknown_scene_lists_presets_not_scan_hint():
    proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli",
            "--backend",
            "sim",
            "--scene",
            "typo_room",
            "--distance-m",
            "1.08",
            "--point-a",
            "31.2,17.2",
            "--point-b",
            "49.0,22.1",
            "-o",
            "/tmp/lumur_typo_cal.json",
        ]
    )
    assert proc.returncode != 0
    err = (proc.stderr + proc.stdout).lower()
    assert "unknown preset" in err or "typo_room" in err
    assert "available" in err or "empty_room" in err
    assert "lumur-scan" not in err
    assert "empty_room" in err
    assert "room_with_box" in err


def test_missing_camera_maps_to_friendly_hint():
    proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli",
            "--backend",
            "opencv",
            "--projector-width",
            "64",
            "--projector-height",
            "48",
            "--distance-m",
            "1.08",
            "--point-a",
            "1,1",
            "--point-b",
            "2,2",
            "-o",
            "/tmp/lumur_nocam_cal.json",
        ]
    )
    assert proc.returncode != 0
    err = proc.stderr + proc.stdout
    assert "Traceback" not in err
    assert "could not open camera" in err.lower() or "camera" in err.lower()
    assert "--backend sim" in err
    assert "empty_room" in err
