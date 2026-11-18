"""Subprocess coverage for lumur-app and umbrella ``lumur app`` commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from lumur.paint.export import export_godot_paint_assets
from lumur.scan.pipeline import write_scan_package
from lumur.sim import SimRig

from tests.test_room_scan import _calibration_from_gt, _capture_decode

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS = REPO_ROOT / "apps"
PAINT = APPS / "paint" / "lumur.app.json"


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="module")
def sample_room(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("cli_app_room")
    rig = SimRig.from_scene_path("empty_room")
    decoded = _capture_decode(rig)
    calib = _calibration_from_gt(rig)
    from lumur.scan.pipeline import scan_from_correspondence

    result = scan_from_correspondence(decoded, calib, max_reprojection_error_px=4.0)
    room = write_scan_package(result, root / "room", calibration=calib)
    export_godot_paint_assets(room)
    return room


def test_lumur_app_check():
    proc = _run([sys.executable, "-m", "lumur.cli_app", "check", str(PAINT)])
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["id"]


def test_lumur_app_fit(sample_room: Path):
    proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli_app",
            "fit",
            str(PAINT),
            "--room",
            str(sample_room),
        ]
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True


def test_lumur_app_list():
    proc = _run([sys.executable, "-m", "lumur.cli_app", "list"])
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    ids = {a.get("id") for a in data["apps"] if a.get("ok")}
    assert "lumur.paint" in ids
    assert "lumur.ripples" in ids
    # Core list excludes bridge-only Story Stage.
    bridges = [a for a in data["apps"] if a.get("bridge")]
    assert bridges == []


def test_lumur_app_list_bridge():
    proc = _run([sys.executable, "-m", "lumur.cli_app", "list", "--bridge"])
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    bridges = [a for a in data["apps"] if a.get("bridge")]
    assert bridges, "expected Story Stage under --bridge"


def test_lumur_app_run(sample_room: Path):
    proc = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli_app",
            "run",
            str(PAINT),
            "--room",
            str(sample_room),
        ]
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["ok"] is True
    assert data["state"] == "running"


@pytest.mark.parametrize(
    "args",
    [
        ["check", str(PAINT)],
        ["list"],
        ["list", "--bridge"],
    ],
)
def test_umbrella_lumur_app_subcommands(args: list[str]):
    proc = _run([sys.executable, "-m", "lumur.cli_main", "app", *args])
    assert proc.returncode == 0, proc.stderr


def test_umbrella_lumur_app_fit_and_run(sample_room: Path):
    fit = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli_main",
            "app",
            "fit",
            str(PAINT),
            "--room",
            str(sample_room),
        ]
    )
    assert fit.returncode == 0, fit.stderr
    run = _run(
        [
            sys.executable,
            "-m",
            "lumur.cli_main",
            "app",
            "run",
            str(PAINT),
            "--room",
            str(sample_room),
        ]
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["state"] == "running"
