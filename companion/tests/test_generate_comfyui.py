"""PRD-002 slice 1: standalone ComfyUI provider against an in-process mock."""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np

from lumur.generate.comfy_provider import ComfyUISurfaceGenerator
from lumur.generate.controls import build_control_images, write_control_images
from lumur.generate.jobs import JobRunner
from lumur.generate.pipeline import build_surface_request, run_generation
from lumur.generate.presets import (
    discover_presets,
    select_preset,
    surface_role_tag,
)
from lumur.generate.provider import NullSurfaceGenerator
from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceTarget
from lumur.paint.export import export_godot_paint_assets

from tests.mock_comfyui import MockComfyUIServer
from tests.test_paint import _scan_room


def test_null_provider_skips_without_error():
    gen = NullSurfaceGenerator()
    req = SurfaceRenderRequest(
        surface=SurfaceTarget(role="floor", width=32, height=32),
        routing={"mode": "direct", "provider": "comfyui", "comfy_base_url": "http://x"},
        workflow={"inline": {"1": {}}},
    )
    result = gen.generate(req)
    assert result.status == JobStatus.SKIPPED


def test_preset_selection_fallback(tmp_path: Path):
    # Local presets with increasing specificity.
    d = tmp_path / "presets"
    d.mkdir()
    base = {
        "schema": "lumur.workflow_preset",
        "schema_version": "1.0",
        "workflow": {"1": {"class_type": "EmptyImage", "inputs": {}}},
    }
    (d / "global.json").write_text(
        json.dumps(
            {
                **base,
                "id": "global_floor",
                "metadata": {"preset": {"tags": [surface_role_tag("floor")]}},
            }
        )
    )
    (d / "room.json").write_text(
        json.dumps(
            {
                **base,
                "id": "room_floor",
                "metadata": {
                    "preset": {
                        "tags": [
                            surface_role_tag("floor"),
                            "lumur:room=studio_a",
                        ]
                    }
                },
            }
        )
    )
    (d / "scenario.json").write_text(
        json.dumps(
            {
                **base,
                "id": "scenario_floor",
                "metadata": {
                    "preset": {
                        "tags": [
                            surface_role_tag("floor"),
                            "lumur:room=studio_a",
                            "lumur:scenario=demo",
                        ]
                    }
                },
            }
        )
    )
    presets = discover_presets([d])
    assert select_preset(presets, surface_role="floor")["id"] == "global_floor"
    assert (
        select_preset(presets, surface_role="floor", room_id="studio_a")["id"]
        == "room_floor"
    )
    assert (
        select_preset(
            presets, surface_role="floor", room_id="studio_a", scenario_key="demo"
        )["id"]
        == "scenario_floor"
    )
    assert select_preset(presets, surface_role="floor", preset_id="room_floor")["id"] == "room_floor"


def test_control_images_from_sim_room(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)
    controls = build_control_images(
        room_dir,
        surface="floor",
        width=64,
        height=48,
        want_mask=True,
        want_depth=True,
        want_normal=True,
    )
    assert controls["mask"].shape == (48, 64)
    assert controls["depth"].shape == (48, 64)
    assert controls["normal"].shape == (48, 64, 3)
    assert int(controls["mask"].max()) == 255
    paths = write_control_images(controls, tmp_path / "controls")
    assert paths["mask"].is_file()


def test_comfyui_e2e_submit_progress_result(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockComfyUIServer() as server:
        server.state.delay_sec = 0.08
        job = run_generation(
            room_dir,
            surface="wall_1",
            comfy_base_url=server.base_url,
            preset_id="surface_solid_dev",
            width=80,
            height=60,
            timeout_sec=10.0,
            wait=True,
            include_controls=False,
        )
        assert job.status == JobStatus.SUCCEEDED
        assert job.result is not None
        assert job.result.image_path and Path(job.result.image_path).is_file()
        img = cv2.imread(job.result.image_path)
        assert img is not None
        assert img.shape[1] == 80 and img.shape[0] == 60

        # Provenance + manifests.
        prov = Path(job.result.provenance_path)
        assert prov.is_file()
        prov_doc = json.loads(prov.read_text())
        assert prov_doc["schema"] == "lumur.generation_provenance"
        assert prov_doc["status"] == "succeeded"

        gen_manifest = json.loads(
            (room_dir / "generated" / "manifest.json").read_text()
        )
        assert gen_manifest["schema"] == "lumur.generated"
        assert "wall_1" in gen_manifest["surfaces"]

        paint = json.loads((room_dir / "godot" / "paint_manifest.json").read_text())
        assert "generated_textures" in paint
        assert "wall_1" in paint["generated_textures"]
        tex_rel = paint["generated_textures"]["wall_1"]["path"]
        assert (room_dir / "godot" / tex_rel).resolve().is_file()

        # Mock saw a prompt and optionally WS progress traffic.
        assert len(server.state.prompts) >= 1


def test_comfyui_failure_leaves_no_texture(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)
    paint_before = json.loads((room_dir / "godot" / "paint_manifest.json").read_text())

    with MockComfyUIServer() as server:
        server.state.fail_next = True
        job = run_generation(
            room_dir,
            surface="wall_1",
            comfy_base_url=server.base_url,
            preset_id="surface_solid_dev",
            width=32,
            height=32,
            timeout_sec=5.0,
            wait=True,
        )
        assert job.status == JobStatus.FAILED
        paint_after = json.loads((room_dir / "godot" / "paint_manifest.json").read_text())
        assert paint_after.get("generated_textures") == paint_before.get(
            "generated_textures"
        )


def test_comfyui_timeout(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockComfyUIServer() as server:
        server.state.timeout_next = True
        job = run_generation(
            room_dir,
            surface="wall_1",
            comfy_base_url=server.base_url,
            preset_id="surface_solid_dev",
            width=32,
            height=32,
            timeout_sec=0.4,
            wait=True,
        )
        assert job.status == JobStatus.TIMEOUT


def test_job_runner_is_non_blocking(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockComfyUIServer() as server:
        server.state.delay_sec = 0.3
        request, _ = build_surface_request(
            room_dir,
            surface="wall_1",
            comfy_base_url=server.base_url,
            preset_id="surface_solid_dev",
            width=32,
            height=32,
            include_controls=False,
        )
        provider = ComfyUISurfaceGenerator(
            base_url=server.base_url,
            timeout_sec=10.0,
            room_package_dir=room_dir,
        )
        runner = JobRunner(provider)
        t0 = time.time()
        job_id = runner.submit(request)
        submit_elapsed = time.time() - t0
        assert submit_elapsed < 0.2  # must return before the mock delay finishes
        job = runner.wait(job_id, timeout_sec=10.0)
        runner.shutdown()
        assert job.status == JobStatus.SUCCEEDED


def test_floor_preset_with_controls_uploads(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockComfyUIServer() as server:
        job = run_generation(
            room_dir,
            surface="floor",
            comfy_base_url=server.base_url,
            # Let tag selection pick surface_floor_controls
            width=64,
            height=48,
            timeout_sec=10.0,
            wait=True,
        )
        assert job.status == JobStatus.SUCCEEDED
        assert len(server.state.uploads) >= 1
        assert (room_dir / "generated").is_dir()


def test_reference_paint_uses_generated_texture(tmp_path: Path):
    """Godot-facing path: generated PNG can be applied via reference painter."""
    from lumur.paint.render import PaintAssignment, paint_from_godot_assets

    room_dir, _rig, _result = _scan_room(tmp_path)
    godot_dir = export_godot_paint_assets(room_dir)

    with MockComfyUIServer() as server:
        job = run_generation(
            room_dir,
            surface="floor",
            comfy_base_url=server.base_url,
            preset_id="surface_floor_controls",
            width=64,
            height=48,
            timeout_sec=10.0,
            wait=True,
        )
    assert job.status == JobStatus.SUCCEEDED
    tex = cv2.imread(job.result.image_path, cv2.IMREAD_COLOR)
    tex_rgb = cv2.cvtColor(tex, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    paint_manifest = json.loads((godot_dir / "paint_manifest.json").read_text())
    floor_id = int(paint_manifest["role_index"]["floor"])
    img = paint_from_godot_assets(
        godot_dir,
        [PaintAssignment(floor_id, mode="texture", texture=tex_rgb)],
    )
    sid = cv2.imread(str(godot_dir / "surface_id.png"), cv2.IMREAD_GRAYSCALE)
    floor_px = img[sid == floor_id]
    assert floor_px.size > 0
    # Mock solid colour is BGR (40, 90, 200) → RGB (200, 90, 40)
    assert float(floor_px[:, 0].mean()) > 0.5
