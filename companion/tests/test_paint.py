"""Paint-the-room: Godot asset export, reference mapper, sim colour check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from lumur.paint.export import assign_surface_roles, export_godot_paint_assets
from lumur.paint.render import PaintAssignment, paint_from_godot_assets, paint_projector_image
from lumur.scan.pipeline import scan_from_correspondence, write_scan_package
from lumur.schema.room import load_room_package
from lumur.sim import SimRig
from lumur.sim.render import render_camera_view

from tests.test_room_scan import _calibration_from_gt, _capture_decode


REPO_ROOT = Path(__file__).resolve().parents[2]
GODOT_CANDIDATES = [
    Path(os.environ["GODOT_BIN"]) if os.environ.get("GODOT_BIN") else None,
    REPO_ROOT / "tools" / "godot",
    Path(shutil.which("godot") or ""),
    Path(shutil.which("godot4") or ""),
]


def _find_godot() -> Path | None:
    for p in GODOT_CANDIDATES:
        if p is not None and p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def _scan_room(tmp_path: Path, scene: str = "room_with_box") -> tuple[Path, object, dict]:
    rig = SimRig.from_scene_path(scene)
    decoded = _capture_decode(rig)
    calib = _calibration_from_gt(rig)
    result = scan_from_correspondence(decoded, calib, max_reprojection_error_px=4.0)
    out = write_scan_package(result, tmp_path / "room", calibration=calib)
    return out, rig, result


def test_assign_surface_roles_floor_and_walls():
    planes = [
        {"plane_id": 1, "kind": "floor", "label": "floor"},
        {"plane_id": 3, "kind": "wall", "label": "wall_3"},
        {"plane_id": 2, "kind": "wall", "label": "wall_2"},
        {"plane_id": 4, "kind": "non_planar", "label": "non_planar"},
    ]
    roles = assign_surface_roles(planes)
    assert "floor" in roles[1]
    assert roles[2][0] == "wall_1"  # sorted by plane_id
    assert roles[3][0] == "wall_2"
    # Raw scan label wall_2 would collide with sequential wall_2 → prefixed.
    assert "label:wall_2" in roles[2]
    assert "non_planar" in roles[4]


def test_export_godot_paint_assets(tmp_path: Path):
    room_dir, _rig, result = _scan_room(tmp_path)
    godot_dir = export_godot_paint_assets(room_dir)
    assert (godot_dir / "paint_manifest.json").is_file()
    assert (godot_dir / "surface_id.png").is_file()
    assert (godot_dir / "confidence.png").is_file()
    assert (godot_dir / "lookup.png").is_file()

    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    assert manifest["schema"] == "lumur.paint_godot"
    assert "floor" in manifest["role_index"]
    assert manifest["floor_plane_id"] == result.segmentation.floor_plane_id

    sid = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    conf = cv2.imread(str(godot_dir / "confidence.png"), cv2.IMREAD_GRAYSCALE)
    assert sid.shape == tuple(reversed(manifest["projector_resolution"]))  # H,W
    assert conf.shape == sid.shape
    assert int(sid.max()) >= 1

    doc, _, _ = load_room_package(room_dir)
    assert "godot" in doc["arrays"]


def test_reference_paint_solid_colours(tmp_path: Path):
    room_dir, _rig, result = _scan_room(tmp_path)
    godot_dir = export_godot_paint_assets(room_dir)
    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    floor_id = int(manifest["role_index"]["floor"])
    wall_roles = sorted(
        [k for k in manifest["role_index"] if k.startswith("wall_")],
        key=lambda s: int(s.split("_")[1]),
    )
    assert wall_roles, "expected at least one wall role"
    wall_id = int(manifest["role_index"][wall_roles[0]])

    assignments = [
        PaintAssignment(floor_id, color=(1.0, 0.0, 0.0), mode="solid"),
        PaintAssignment(wall_id, color=(0.0, 0.0, 1.0), mode="solid"),
    ]
    img = paint_from_godot_assets(godot_dir, assignments)
    sid = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    floor_px = img[sid == floor_id]
    wall_px = img[sid == wall_id]
    assert floor_px.size > 0 and wall_px.size > 0
    assert float(floor_px[:, 0].mean()) > 0.9
    assert float(floor_px[:, 2].mean()) < 0.1
    assert float(wall_px[:, 2].mean()) > 0.9
    assert float(wall_px[:, 0].mean()) < 0.1

    # Pulse mode should modulate with time.
    pulse = paint_projector_image(
        sid.astype(np.int32),
        np.ones_like(sid, dtype=np.float32),
        sid > 0,
        [PaintAssignment(floor_id, color=(1, 1, 1), mode="pulse", pulse_hz=1.0)],
        time_s=0.25,
    )
    assert pulse[sid == floor_id].mean() != pytest.approx(1.0, abs=0.01)


def test_paint_through_sim_lands_on_correct_surfaces(tmp_path: Path):
    """Paint in projector space → sim camera; per-surface chromaticity check."""
    room_dir, rig, result = _scan_room(tmp_path)
    # Zero sensor noise for a clean colour check.
    rig.scene.camera.noise_std = 0.0
    rig.scene.camera.blur_sigma = 0.0
    rig.scene.camera.ambient = 2.0

    godot_dir = export_godot_paint_assets(room_dir)
    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    floor_id = int(manifest["role_index"]["floor"])
    wall_roles = sorted(
        [
            k
            for k in manifest["role_index"]
            if k.startswith("wall_") and k.split("_", 1)[1].isdigit()
        ],
        key=lambda s: int(s.split("_")[1]),
    )
    assert wall_roles, "expected sequential wall_n roles"
    wall_ids = [int(manifest["role_index"][r]) for r in wall_roles]

    assignments = [PaintAssignment(floor_id, color=(1.0, 0.05, 0.05), mode="solid")]
    assignments.extend(
        PaintAssignment(wid, color=(0.05, 0.05, 1.0), mode="solid") for wid in wall_ids
    )
    painted = paint_from_godot_assets(godot_dir, assignments)
    pattern = np.clip(painted * 255.0, 0, 255).astype(np.uint8)

    buffers = render_camera_view(
        rig.scene.room,
        rig.scene.camera,
        rig.scene.projector,
        pattern,
        retain_color=True,
        rng=np.random.default_rng(0),
    )
    cam = buffers.image.astype(np.float32)
    assert cam.ndim == 3 and cam.shape[2] == 3

    # Restrict to pixels where scan surface_id agrees with the projector map
    # (Gray-code quantisation can leave edge disagreements).
    sid_cam = result.segmentation.surface_id
    sid_proj = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    assert sid_proj is not None
    pu = np.rint(buffers.proj_u).astype(np.int32)
    pv = np.rint(buffers.proj_v).astype(np.int32)
    ph, pw = sid_proj.shape
    lit = buffers.valid_proj & (buffers.depth > 0)
    inside = lit & (pu >= 0) & (pu < pw) & (pv >= 0) & (pv < ph)
    proj_sid = np.zeros(sid_cam.shape, dtype=np.int32)
    proj_sid[inside] = sid_proj[pv[inside], pu[inside]]
    agree = inside & (proj_sid == sid_cam)

    floor_sel = agree & (sid_cam == floor_id)
    wall_sel = agree & np.isin(sid_cam, np.asarray(wall_ids, dtype=np.int32))
    assert int(floor_sel.sum()) > 10
    assert int(wall_sel.sum()) > 10

    floor_rgb = cam[floor_sel]
    wall_rgb = cam[wall_sel]
    floor_r = float(floor_rgb[:, 0].mean())
    floor_b = float(floor_rgb[:, 2].mean())
    wall_r = float(wall_rgb[:, 0].mean())
    wall_b = float(wall_rgb[:, 2].mean())
    assert floor_r > floor_b * 1.3
    assert wall_b > wall_r * 1.3

    floor_ok = (floor_rgb[:, 0] > floor_rgb[:, 2] * 1.1).mean()
    wall_ok = (wall_rgb[:, 2] > wall_rgb[:, 0] * 1.1).mean()
    assert float(floor_ok) > 0.85
    assert float(wall_ok) > 0.85


def _ensure_godot_import(godot: Path) -> None:
    """First-run import so class_name resolves (ADR 0021 / tools/godot_import.sh)."""
    if (REPO_ROOT / ".godot").is_dir():
        return
    env = os.environ.copy()
    env["GODOT_BIN"] = str(godot)
    proc = subprocess.run(
        ["bash", str(REPO_ROOT / "tools" / "godot_import.sh")],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"godot import failed:\n{proc.stdout}\n{proc.stderr}"


def test_godot_headless_paint_render(tmp_path: Path):
    """When Godot is available, render paint PNG and cross-check vs reference."""
    godot = _find_godot()
    if godot is None:
        pytest.skip(
            "Godot binary not found (set GODOT_BIN to a Godot 4 binary). "
            "Python reference paint tests still cover mapping; see docs/godot/paint-mode.md."
        )
    _ensure_godot_import(godot)

    room_dir, _rig, _result = _scan_room(tmp_path)
    godot_dir = export_godot_paint_assets(room_dir)
    out_png = tmp_path / "godot_paint.png"

    # ``--headless`` uses the dummy renderer (no real shader draw). Drive a
    # virtual X display so gl_compatibility actually paints the SubViewport.
    cmd = [
        "xvfb-run",
        "-a",
        str(godot),
        "--path",
        str(REPO_ROOT),
        "--display-driver",
        "x11",
        "--rendering-driver",
        "opengl3",
        "--script",
        "res://demo/scripts/headless_paint_render.gd",
        "--",
        f"--assets={godot_dir}",
        f"--out={out_png}",
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(REPO_ROOT),
    )
    if proc.returncode != 0:
        pytest.fail(
            "Godot headless paint failed\n"
            f"cmd={cmd}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    assert out_png.is_file()
    godot_img = cv2.imread(str(out_png), cv2.IMREAD_COLOR)
    assert godot_img is not None
    godot_rgb = cv2.cvtColor(godot_img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

    manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    floor_id = int(manifest["role_index"]["floor"])
    assignments = [
        PaintAssignment(floor_id, color=(0.85, 0.15, 0.12), mode="solid"),
    ]
    # Match headless script: floor red, walls blue, other green — approximate
    # by checking floor pixels are red-dominant in the Godot PNG.
    sid = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    floor_px = godot_rgb[sid == floor_id]
    assert floor_px.size > 0
    assert float(floor_px[:, 0].mean()) > float(floor_px[:, 2].mean())
