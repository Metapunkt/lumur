"""Parity: Python fit/compositor vs GDScript mirrors (when Godot is available)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from lumur.app.compositor import Compositor
from lumur.app.fit import fit_app_to_room
from lumur.app.room_services import RoomServices
from lumur.paint.export import export_godot_paint_assets
from lumur.scan.pipeline import scan_from_correspondence, write_scan_package
from lumur.schema.app import load_app_manifest
from lumur.sim import SimRig

from tests.test_room_scan import _calibration_from_gt, _capture_decode

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_MANIFEST = Path(__file__).resolve().parent / "fixtures" / "parity" / "floor_app.json"
IMPORT_SCRIPT = REPO_ROOT / "tools" / "godot_import.sh"


def _find_godot() -> Path | None:
    candidates = [
        Path(os.environ["GODOT_BIN"]) if os.environ.get("GODOT_BIN") else None,
        REPO_ROOT / "tools" / "godot",
        Path(shutil.which("godot") or ""),
        Path(shutil.which("godot4") or ""),
    ]
    for p in candidates:
        if p is not None and p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def _ensure_godot_import(godot: Path) -> None:
    """Documented first-run import so class_name resolves."""
    if (REPO_ROOT / ".godot").is_dir():
        return
    env = os.environ.copy()
    env["GODOT_BIN"] = str(godot)
    proc = subprocess.run(
        ["bash", str(IMPORT_SCRIPT)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"godot import failed:\n{proc.stdout}\n{proc.stderr}"


@pytest.fixture
def room_with_godot(tmp_path: Path) -> Path:
    rig = SimRig.from_scene_path("room_with_box")
    decoded = _capture_decode(rig)
    calib = _calibration_from_gt(rig)
    result = scan_from_correspondence(decoded, calib, max_reprojection_error_px=4.0)
    room = write_scan_package(result, tmp_path / "room", calibration=calib)
    export_godot_paint_assets(room)
    return room


def _run_godot_script(godot: Path, script: str, *user_args: str) -> dict:
    out = Path(os.environ.get("TMPDIR", "/tmp")) / f"lumur_parity_{os.getpid()}.json"
    if out.exists():
        out.unlink()
    cmd = [
        str(godot),
        "--headless",
        "--path",
        str(REPO_ROOT),
        "--script",
        script,
        "--",
        *user_args,
        f"--out={out}",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"Godot parity script failed\ncmd={cmd}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )
    assert out.is_file(), f"missing out file; stdout={proc.stdout}\nstderr={proc.stderr}"
    return json.loads(out.read_text(encoding="utf-8"))


def test_fit_parity_python_vs_godot(room_with_godot: Path):
    godot = _find_godot()
    if godot is None:
        pytest.skip("Godot binary not found (set GODOT_BIN)")

    _ensure_godot_import(godot)
    room = RoomServices.load(room_with_godot)
    manifest = load_app_manifest(FIXTURE_MANIFEST)
    py = fit_app_to_room(manifest, room).to_dict()

    gd = _run_godot_script(
        godot,
        "res://demo/scripts/headless_parity_fit.gd",
        f"--assets={room_with_godot / 'godot'}",
        f"--manifest={FIXTURE_MANIFEST}",
    )
    assert py["ok"] is True
    assert gd["ok"] is True
    assert py["app_id"] == gd["app_id"]
    py_ids = {
        k: v.get("surface_id")
        for k, v in py["bindings"].items()
        if v.get("surface_id") is not None
    }
    gd_ids = {
        k: v.get("surface_id")
        for k, v in gd["bindings"].items()
        if v.get("surface_id") is not None
    }
    assert py_ids == gd_ids


def test_compositor_parity_python_vs_godot(room_with_godot: Path):
    godot = _find_godot()
    if godot is None:
        pytest.skip("Godot binary not found (set GODOT_BIN)")

    _ensure_godot_import(godot)
    room = RoomServices.load(room_with_godot)
    manifest = load_app_manifest(FIXTURE_MANIFEST)
    fit = fit_app_to_room(manifest, room)
    assert fit.ok
    comp = Compositor(room=room)
    claims = comp.claim_from_fit(str(manifest["id"]), fit, shares=manifest.get("shares") or [])
    py_owned = sorted(comp.exclusive_owned_ids())
    py_claim_sids = sorted(c.surface_id for c in claims)

    gd = _run_godot_script(
        godot,
        "res://demo/scripts/headless_parity_compositor.gd",
        f"--assets={room_with_godot / 'godot'}",
        f"--manifest={FIXTURE_MANIFEST}",
    )
    gd_owned = sorted(int(x) for x in gd.get("exclusive_owned_ids") or [])
    gd_claim_sids = sorted(int(c["surface_id"]) for c in gd.get("claimed") or [])
    assert py_owned == gd_owned
    assert py_claim_sids == gd_claim_sids
