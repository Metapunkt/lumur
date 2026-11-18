"""PRD-002 slice 2: Synesyn Hub provider against an in-process Hub mock."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import pytest

from lumur.generate.jobs import JobRunner
from lumur.generate.presets import surface_role_tag
from lumur.generate.types import JobStatus, SurfaceRenderRequest, SurfaceTarget
from lumur.paint.export import export_godot_paint_assets
from lumur_synesyn.config import HubConfig, load_hub_config
from lumur_synesyn.hub_client import HubAuthError, SynesynHubClient
from lumur_synesyn.hub_provider import SynesynHubSurfaceGenerator, to_synesyn_render_request
from lumur_synesyn.pipeline import build_hub_surface_request, run_hub_generation
from lumur_synesyn.presets import discover_hub_workflow_presets, select_hub_preset
from lumur_synesyn.room_artifact import ROOM_ARTIFACT_TYPE, register_room_package

from tests.mock_synesyn_hub import MockSynesynHubServer
from tests.test_paint import _scan_room


def _seed_floor_and_wall(server: MockSynesynHubServer) -> tuple[str, str]:
    floor_id = server.seed_workflow_preset(
        tags=[surface_role_tag("floor")],
        name="hub floor",
        size_patches=[{"node_id": "1", "width_input": "width", "height_input": "height"}],
        controls={"mask": True},
        control_nodes={"mask": {"node_id": "10", "input": "image"}},
        workflow={
            "10": {"class_type": "LoadImage", "inputs": {"image": "mask.png"}},
            "1": {
                "class_type": "EmptyImage",
                "inputs": {"width": 64, "height": 48, "batch_size": 1, "color": 0},
            },
            "2": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "floor", "images": ["1", 0]},
            },
        },
    )
    wall_id = server.seed_workflow_preset(
        tags=[surface_role_tag("wall_1")],
        name="hub wall",
        size_patches=[{"node_id": "1", "width_input": "width", "height_input": "height"}],
        workflow={
            "1": {
                "class_type": "EmptyImage",
                "inputs": {"width": 80, "height": 60, "batch_size": 1, "color": 0},
            },
            "2": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "wall", "images": ["1", 0]},
            },
        },
    )
    return floor_id, wall_id


def test_hub_config_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("LUMUR_SYNESYN_HUB_URL", "http://127.0.0.1:9999")
    monkeypatch.setenv("LUMUR_SYNESYN_HUB_TOKEN", "secret-token")
    monkeypatch.setenv("LUMUR_SYNESYN_HUB_AUTH", "1")
    cfg = load_hub_config()
    assert cfg.hub_base_url.endswith(":9999")
    assert cfg.auth_token == "secret-token"
    assert cfg.auth_enabled is True
    assert "Authorization" in cfg.bearer_headers()

    cfg_path = tmp_path / "hub.json"
    cfg_path.write_text(
        json.dumps({"hub": {"base_url": "http://from-file", "auth": {"enabled": False}}})
    )
    monkeypatch.delenv("LUMUR_SYNESYN_HUB_URL")
    monkeypatch.delenv("LUMUR_SYNESYN_HUB_TOKEN")
    monkeypatch.delenv("LUMUR_SYNESYN_HUB_AUTH")
    cfg2 = load_hub_config(config_path=cfg_path)
    assert cfg2.hub_base_url == "http://from-file"
    assert cfg2.auth_enabled is False


def test_hub_client_treats_ok_false_as_failure():
    """HTTP 200 with JSON ``ok: false`` must raise HubError."""
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import threading

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = b'{"ok": false, "error": "hub says no"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        client = SynesynHubClient(HubConfig(hub_base_url=f"http://{host}:{port}"))
        from lumur_synesyn.hub_client import HubError

        with pytest.raises(HubError, match="hub says no"):
            client._request("GET", "/health")
    finally:
        server.shutdown()


def test_synesyn_render_request_shape():

    req = SurfaceRenderRequest(
        surface=SurfaceTarget(role="floor", surface_id=1, width=64, height=48),
        routing={"mode": "hub", "provider": "comfyui", "hub_base_url": "http://h"},
        workflow={"artifact_id": "art_wf_1"},
        patches=[{"node_id": "1", "input": "width", "value": 64}],
        client={"app_id": "lumur", "client_id": "c1", "request_id": "r1"},
    )
    syn = to_synesyn_render_request(
        req,
        hub_base_url="http://h",
        comfy_base_url="http://comfy",
        input_uploads=[
            {"node_id": "10", "input": "image", "artifact_id": "art_c", "filename": "mask.png"}
        ],
    )
    assert syn["kind"] == "synesyn.render_request"
    assert syn["schema_version"] == 1
    assert syn["routing"]["mode"] == "hub"
    assert syn["routing"]["provider"] == "comfyui"
    assert syn["routing"]["comfy_base_url"] == "http://comfy"
    assert syn["output_routing"]["mode"] == "substrate"
    assert syn["output_routing"]["images"]["artifact_type"] == "image.generated"
    assert syn["input_uploads"][0]["artifact_id"] == "art_c"
    assert syn["refs"]["lumur_surface"]["role"] == "floor"


def test_hub_preset_selection_fallback():
    with MockSynesynHubServer() as server:
        server.seed_workflow_preset(tags=[surface_role_tag("floor")], name="global")
        server.seed_workflow_preset(
            tags=[surface_role_tag("floor"), "lumur:room=studio_a"],
            name="room",
            preset_id="art_room",
        )
        server.seed_workflow_preset(
            tags=[
                surface_role_tag("floor"),
                "lumur:room=studio_a",
                "lumur:scenario=demo",
            ],
            name="scenario",
            preset_id="art_scenario",
        )
        cfg = HubConfig(hub_base_url=server.base_url)
        client = SynesynHubClient(cfg)
        presets = discover_hub_workflow_presets(client)
        assert select_hub_preset(presets, surface_role="floor")["metadata"]["preset"]["name"] == "global"
        assert (
            select_hub_preset(presets, surface_role="floor", room_id="studio_a")["id"]
            == "art_room"
        )
        assert (
            select_hub_preset(
                presets, surface_role="floor", room_id="studio_a", scenario_key="demo"
            )["id"]
            == "art_scenario"
        )


def test_hub_e2e_submit_progress_success(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockSynesynHubServer() as server:
        server.state.delay_sec = 0.08
        _floor, wall_id = _seed_floor_and_wall(server)
        cfg = HubConfig(
            hub_base_url=server.base_url,
            comfy_base_url="http://127.0.0.1:8188",
            timeout_sec=10.0,
            poll_interval_sec=0.05,
        )
        job = run_hub_generation(
            room_dir,
            surface="wall_1",
            config=cfg,
            preset_id=wall_id,
            width=80,
            height=60,
            wait=True,
            include_controls=False,
            fallback_local_presets=False,
        )
        assert job.status == JobStatus.SUCCEEDED
        assert job.result is not None
        assert job.result.image_path and Path(job.result.image_path).is_file()
        img = cv2.imread(job.result.image_path)
        assert img is not None
        assert img.shape[1] == 80 and img.shape[0] == 60

        prov = json.loads(Path(job.result.provenance_path).read_text())
        assert prov["provider"] == "synesyn_hub"
        assert prov["extra"]["synesyn_job_id"]
        assert prov["extra"]["synesyn_image_artifact_ids"]
        assert prov["extra"]["synesyn_render_request_artifact_id"]

        paint = json.loads((room_dir / "godot" / "paint_manifest.json").read_text())
        assert "wall_1" in paint["generated_textures"]

        # Submit shape mirrors SynesynRenderRequestV1 hub mode.
        assert len(server.state.submits) >= 1
        submitted = server.state.submits[-1]
        assert submitted["kind"] == "synesyn.render_request"
        assert submitted["routing"]["mode"] == "hub"
        assert submitted["output_routing"]["images"]["artifact_type"] == "image.generated"


def test_hub_failure_leaves_no_texture(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)
    paint_before = json.loads((room_dir / "godot" / "paint_manifest.json").read_text())

    with MockSynesynHubServer() as server:
        server.state.fail_next = True
        _floor, wall_id = _seed_floor_and_wall(server)
        cfg = HubConfig(hub_base_url=server.base_url, timeout_sec=5.0, poll_interval_sec=0.05)
        job = run_hub_generation(
            room_dir,
            surface="wall_1",
            config=cfg,
            preset_id=wall_id,
            width=32,
            height=32,
            wait=True,
            fallback_local_presets=False,
        )
        assert job.status == JobStatus.FAILED
        paint_after = json.loads((room_dir / "godot" / "paint_manifest.json").read_text())
        assert paint_after.get("generated_textures") == paint_before.get("generated_textures")


def test_hub_timeout(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockSynesynHubServer() as server:
        server.state.timeout_next = True
        _floor, wall_id = _seed_floor_and_wall(server)
        cfg = HubConfig(
            hub_base_url=server.base_url,
            timeout_sec=0.4,
            poll_interval_sec=0.05,
        )
        job = run_hub_generation(
            room_dir,
            surface="wall_1",
            config=cfg,
            preset_id=wall_id,
            width=32,
            height=32,
            wait=True,
            fallback_local_presets=False,
        )
        assert job.status == JobStatus.TIMEOUT


def test_hub_auth_required(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockSynesynHubServer() as server:
        server.state.auth_token = "correct-token"
        _floor, wall_id = _seed_floor_and_wall(server)

        # Health remains open.
        open_cfg = HubConfig(hub_base_url=server.base_url, auth_enabled=False)
        assert SynesynHubClient(open_cfg).ping()["ok"] is True

        # Missing bearer → fail generate.
        bad = HubConfig(hub_base_url=server.base_url, auth_enabled=True, auth_token="")
        job = run_hub_generation(
            room_dir,
            surface="wall_1",
            config=bad,
            preset_id=wall_id,
            width=32,
            height=32,
            wait=True,
            fallback_local_presets=False,
        )
        assert job.status == JobStatus.FAILED
        assert "auth" in (job.error or "").lower() or "bearer" in (job.error or "").lower()

        # Correct token succeeds.
        good = HubConfig(
            hub_base_url=server.base_url,
            auth_enabled=True,
            auth_token="correct-token",
            timeout_sec=10.0,
            poll_interval_sec=0.05,
        )
        job2 = run_hub_generation(
            room_dir,
            surface="wall_1",
            config=good,
            preset_id=wall_id,
            width=32,
            height=32,
            wait=True,
            fallback_local_presets=False,
        )
        assert job2.status == JobStatus.SUCCEEDED


def test_hub_input_uploads_for_controls(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockSynesynHubServer() as server:
        floor_id, _wall = _seed_floor_and_wall(server)
        cfg = HubConfig(
            hub_base_url=server.base_url,
            timeout_sec=10.0,
            poll_interval_sec=0.05,
        )
        job = run_hub_generation(
            room_dir,
            surface="floor",
            config=cfg,
            preset_id=floor_id,
            width=64,
            height=48,
            wait=True,
            include_controls=True,
            fallback_local_presets=False,
        )
        assert job.status == JobStatus.SUCCEEDED
        submitted = server.state.submits[-1]
        uploads = submitted.get("input_uploads") or []
        assert isinstance(uploads, list) and len(uploads) >= 1
        assert uploads[0]["node_id"] == "10"
        assert uploads[0]["artifact_id"]
        # Control artifacts were created on the Hub.
        control_arts = [
            a
            for a in server.state.artifacts.values()
            if a.get("artifact_type") == "image.control"
        ]
        assert len(control_arts) >= 1


def test_register_room_package(tmp_path: Path):
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockSynesynHubServer() as server:
        cfg = HubConfig(hub_base_url=server.base_url)
        client = SynesynHubClient(cfg)
        res = register_room_package(client, room_dir, room_id="studio_a")
        assert res["ok"] is True
        assert res["artifact_type"] == ROOM_ARTIFACT_TYPE
        art = server.state.artifacts[res["artifact_id"]]
        assert art["artifact_type"] == ROOM_ARTIFACT_TYPE
        assert art["inline_json"]["room_id"] == "studio_a"


def test_provider_swap_same_interface(tmp_path: Path):
    """Paint consumers see SurfaceGenerator; Hub vs ComfyUI is config only."""
    room_dir, _rig, _result = _scan_room(tmp_path)
    export_godot_paint_assets(room_dir)

    with MockSynesynHubServer() as server:
        _floor, wall_id = _seed_floor_and_wall(server)
        cfg = HubConfig(
            hub_base_url=server.base_url,
            timeout_sec=10.0,
            poll_interval_sec=0.05,
        )
        request, _ = build_hub_surface_request(
            room_dir,
            surface="wall_1",
            config=cfg,
            preset_id=wall_id,
            width=40,
            height=30,
            include_controls=False,
            fallback_local_presets=False,
        )
        provider = SynesynHubSurfaceGenerator(cfg, room_package_dir=room_dir)
        runner = JobRunner(provider)
        job_id = runner.submit(request)
        job = runner.wait(job_id, timeout_sec=10.0)
        runner.shutdown()
        assert job.status == JobStatus.SUCCEEDED


def test_core_does_not_import_lumur_synesyn():
    """Boundary: lumur.generate must not depend on the optional bridge."""
    import lumur.generate as gen
    import lumur.generate.comfy_provider as cp
    import lumur.generate.pipeline as pipe

    for mod in (gen, cp, pipe):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "lumur_synesyn" not in src
        assert "synesyn_core" not in src
        assert "SynesynHub" not in src


def test_invalid_token_raises_on_protected_call():
    with MockSynesynHubServer() as server:
        server.state.auth_token = "secret"
        cfg = HubConfig(
            hub_base_url=server.base_url, auth_enabled=True, auth_token="wrong"
        )
        client = SynesynHubClient(cfg)
        with pytest.raises(HubAuthError):
            client.query_artifacts_by_type("json.workflow")
