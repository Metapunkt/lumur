"""In-process Synesyn Hub mock mirroring public Hub API shapes (read from Synesyn).

Endpoints exercised by the Lumur bridge:

- ``GET /health``
- ``POST /substrate/artifacts`` (inline_json / inline_bytes_base64)
- ``GET /substrate/artifacts/{id}/content`` (byte/json download; remote touchpoint)
- ``POST /substrate/query`` (artifacts by type / id)
- ``POST /render/submit`` → ``{ok, job_id}``
- ``GET /render/jobs/{job_id}`` → render job shape with ``image.generated`` artifacts

Optional Bearer auth mirrors ``services/synesyn_hub/app/auth.py``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

import cv2
import numpy as np


def _png_bytes(width: int, height: int, color_bgr: tuple[int, int, int] = (40, 90, 200)) -> bytes:
    img = np.zeros((max(height, 1), max(width, 1), 3), dtype=np.uint8)
    img[:, :] = color_bgr
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("png encode failed")
    return buf.tobytes()


def _extract_size(workflow: dict[str, Any]) -> tuple[int, int]:
    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs") or {}
        if not isinstance(inputs, dict):
            continue
        if "width" in inputs and "height" in inputs:
            try:
                return int(inputs["width"]), int(inputs["height"])
            except (TypeError, ValueError):
                continue
    return 64, 64


class MockHubState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.jobs: dict[str, dict[str, Any]] = {}
        self.auth_token: str | None = None  # None = auth disabled
        self.fail_next = False
        self.timeout_next = False
        self.delay_sec = 0.05
        self.require_auth_paths = True
        self.submits: list[dict[str, Any]] = []


class MockSynesynHubServer:
    """Threading HTTP server mimicking Synesyn Hub render + substrate routes."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.state = MockHubState()
        parent = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
                return

            def _read_json(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                obj = json.loads(raw.decode("utf-8") or "{}")
                return obj if isinstance(obj, dict) else {}

            def _send(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_json(self, code: int, obj: dict[str, Any]) -> None:
                raw = json.dumps(obj).encode("utf-8")
                self._send(code, raw, "application/json")

            def _check_auth(self) -> bool:
                token = parent.state.auth_token
                if not token:
                    return True
                path = urlparse(self.path).path
                if path in ("/health", "/status", "/version"):
                    return True
                h = self.headers.get("Authorization", "")
                if not h.startswith("Bearer "):
                    self._send_json(401, {"ok": False, "error": "missing_bearer_token"})
                    return False
                if h.removeprefix("Bearer ").strip() != token:
                    self._send_json(403, {"ok": False, "error": "invalid_token"})
                    return False
                return True

            def do_GET(self) -> None:  # noqa: N802
                if not self._check_auth():
                    return
                parsed = urlparse(self.path)
                path = parsed.path

                if path == "/health":
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "version": "mock",
                            "capabilities": {
                                "substrate": True,
                                "render_submit": True,
                                "workspace_configured": True,
                            },
                        },
                    )
                    return

                if path.startswith("/render/jobs/"):
                    job_id = path[len("/render/jobs/") :].strip("/")
                    with parent.state.lock:
                        job = parent.state.jobs.get(job_id)
                    if not job:
                        self._send_json(404, {"ok": False, "error": "Job not found"})
                        return
                    self._send_json(200, dict(job))
                    return

                if path.startswith("/substrate/artifacts/") and path.endswith("/content"):
                    art_id = path[len("/substrate/artifacts/") : -len("/content")].strip("/")
                    with parent.state.lock:
                        art = parent.state.artifacts.get(art_id)
                    if not art:
                        self._send_json(404, {"ok": False, "error": "Artifact not found"})
                        return
                    if art.get("bytes") is not None:
                        self._send(200, art["bytes"], art.get("content_type") or "application/octet-stream")
                        return
                    if art.get("inline_json") is not None:
                        self._send_json(200, {"ok": True, "json": art["inline_json"]})
                        return
                    self._send_json(404, {"ok": False, "error": "no content"})
                    return

                self._send_json(404, {"ok": False, "error": "not found"})

            def do_POST(self) -> None:  # noqa: N802
                if not self._check_auth():
                    return
                parsed = urlparse(self.path)
                path = parsed.path
                body = self._read_json()

                if path == "/substrate/artifacts":
                    art_id = f"art_{uuid.uuid4().hex[:12]}"
                    artifact_type = str(body.get("artifact_type") or "unknown")
                    meta = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
                    rec: dict[str, Any] = {
                        "id": art_id,
                        "artifact_type": artifact_type,
                        "uri": f"mock://artifacts/{art_id}",
                        "hash": hashlib.sha256(art_id.encode()).hexdigest()[:16],
                        "created_at": time.time(),
                        "metadata": meta,
                        "metadata_json": json.dumps(meta),
                    }
                    if body.get("inline_json") is not None:
                        rec["inline_json"] = body["inline_json"]
                    if body.get("inline_bytes_base64") is not None:
                        raw = base64.b64decode(str(body["inline_bytes_base64"]))
                        ext = str(body.get("ext") or "bin").lstrip(".")
                        rec["bytes"] = raw
                        rec["ext"] = ext
                        rec["inline_bytes_base64"] = str(body["inline_bytes_base64"])
                        rec["content_type"] = (
                            "image/png" if ext == "png" else "application/octet-stream"
                        )
                    with parent.state.lock:
                        parent.state.artifacts[art_id] = rec
                    self._send_json(
                        200,
                        {
                            "ok": True,
                            "id": art_id,
                            "uri": rec["uri"],
                            "hash": rec["hash"],
                        },
                    )
                    return

                if path == "/substrate/query":
                    table = str(body.get("table") or "")
                    where = body.get("where") if isinstance(body.get("where"), dict) else {}
                    limit = int(body.get("limit") or 50)
                    if table != "artifacts":
                        self._send_json(
                            200,
                            {"ok": True, "result": {"columns": [], "rows": []}},
                        )
                        return
                    cols = [
                        "id",
                        "artifact_type",
                        "uri",
                        "hash",
                        "created_at",
                        "metadata_json",
                    ]
                    rows: list[list[Any]] = []
                    with parent.state.lock:
                        arts = list(parent.state.artifacts.values())
                    for art in arts:
                        if "id" in where and str(art.get("id")) != str(where["id"]):
                            continue
                        if (
                            "artifact_type" in where
                            and str(art.get("artifact_type")) != str(where["artifact_type"])
                        ):
                            continue
                        # Attach inline_json onto a parallel lookup; query rows match Hub shape.
                        rows.append(
                            [
                                art.get("id"),
                                art.get("artifact_type"),
                                art.get("uri"),
                                art.get("hash"),
                                art.get("created_at"),
                                art.get("metadata_json") or json.dumps(art.get("metadata") or {}),
                            ]
                        )
                        if len(rows) >= limit:
                            break
                    # Stash inline payloads so client get_artifact_json can recover via content.
                    self._send_json(200, {"ok": True, "result": {"columns": cols, "rows": rows}})
                    return

                if path == "/render/submit":
                    rr = body.get("request") if isinstance(body.get("request"), dict) else {}
                    with parent.state.lock:
                        parent.state.submits.append(rr)
                    job_id = f"job_{uuid.uuid4().hex[:12]}"
                    client = rr.get("client") if isinstance(rr.get("client"), dict) else {}
                    request_id = str(client.get("request_id") or "")
                    # Schedule async-ish completion on a worker thread.
                    threading.Thread(
                        target=parent._complete_job,
                        args=(job_id, rr, request_id),
                        daemon=True,
                    ).start()
                    with parent.state.lock:
                        parent.state.jobs[job_id] = {
                            "ok": True,
                            "job_id": job_id,
                            "status": "queued",
                            "provider": "comfyui",
                            "job_type": "render.comfyui",
                            "created_at": time.time(),
                            "error": None,
                            "output": {},
                            "artifacts": [],
                        }
                    self._send_json(200, {"ok": True, "job_id": job_id})
                    return

                self._send_json(404, {"ok": False, "error": "not found"})

        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self.host, self.port = self._httpd.server_address[:2]
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _complete_job(self, job_id: str, rr: dict[str, Any], request_id: str) -> None:
        delay = float(self.state.delay_sec)
        time.sleep(delay)
        with self.state.lock:
            job = self.state.jobs.get(job_id)
            if not job:
                return
            job["status"] = "running"
            job["started_at"] = time.time()
            job["output"] = {"percent": 25.0}

        if self.state.timeout_next:
            # Leave job running forever (caller times out).
            with self.state.lock:
                self.state.timeout_next = False
                job = self.state.jobs.get(job_id)
                if job:
                    job["status"] = "running"
                    job["output"] = {"percent": 40.0}
            return

        if self.state.fail_next:
            with self.state.lock:
                self.state.fail_next = False
                job = self.state.jobs.get(job_id)
                if job:
                    job["status"] = "failed"
                    job["error"] = "mock hub render failure"
                    job["completed_at"] = time.time()
                    job["output"] = {"percent": 100.0}
            return

        # Resolve workflow size.
        wf = rr.get("workflow") if isinstance(rr.get("workflow"), dict) else {}
        inline = wf.get("inline") if isinstance(wf.get("inline"), dict) else {}
        if not inline:
            art_id = str(wf.get("artifact_id") or "").strip()
            with self.state.lock:
                art = self.state.artifacts.get(art_id) if art_id else None
            if art and isinstance(art.get("inline_json"), dict):
                inline = art["inline_json"]
        # Apply patches for size.
        workflow = dict(inline or {})
        for p in rr.get("patches") or []:
            if not isinstance(p, dict):
                continue
            node_id = str(p.get("node_id") or "")
            input_key = str(p.get("input") or "")
            if not node_id or not input_key:
                continue
            node = workflow.setdefault(node_id, {"class_type": "Unknown", "inputs": {}})
            inputs = node.setdefault("inputs", {})
            if isinstance(inputs, dict):
                inputs[input_key] = p.get("value")
        width, height = _extract_size(workflow)
        image_bytes = _png_bytes(width, height)

        # Persist render_request + image.generated artifacts (Hub worker shape).
        rr_art_id = f"art_rr_{uuid.uuid4().hex[:10]}"
        img_art_id = f"art_img_{uuid.uuid4().hex[:10]}"
        with self.state.lock:
            self.state.artifacts[rr_art_id] = {
                "id": rr_art_id,
                "artifact_type": "json.render_request",
                "uri": f"mock://artifacts/{rr_art_id}",
                "hash": "rr",
                "created_at": time.time(),
                "metadata": {"provenance": {"job_id": job_id, "request_id": request_id}},
                "metadata_json": "{}",
                "inline_json": rr,
            }
            self.state.artifacts[img_art_id] = {
                "id": img_art_id,
                "artifact_type": "image.generated",
                "uri": f"mock://artifacts/{img_art_id}",
                "hash": "img",
                "created_at": time.time(),
                "metadata": {
                    "provenance": {
                        "generated_by": "synesyn_hub.render.comfyui",
                        "job_id": job_id,
                        "request_id": request_id,
                        "route_mode": "hub",
                    }
                },
                "metadata_json": "{}",
                "bytes": image_bytes,
                "ext": "png",
                "content_type": "image/png",
                "inline_bytes_base64": base64.b64encode(image_bytes).decode("ascii"),
            }
            job = self.state.jobs[job_id]
            job["status"] = "completed"
            job["completed_at"] = time.time()
            job["prompt_id"] = f"prompt_{uuid.uuid4().hex[:8]}"
            job["render_request_artifact_id"] = rr_art_id
            job["image_artifact_ids"] = [img_art_id]
            job["output"] = {
                "prompt_id": job["prompt_id"],
                "image_artifact_ids": [img_art_id],
                "final_image_artifact_ids": [img_art_id],
                "render_request_artifact_id": rr_art_id,
                "percent": 100.0,
            }
            job["artifacts"] = [
                {
                    "artifact_id": img_art_id,
                    "artifact_type": "image.generated",
                    "uri": f"mock://artifacts/{img_art_id}",
                    "is_final_output": True,
                },
                {
                    "artifact_id": rr_art_id,
                    "artifact_type": "json.render_request",
                    "uri": f"mock://artifacts/{rr_art_id}",
                    "is_final_output": False,
                },
            ]

    def seed_workflow_preset(
        self,
        *,
        tags: list[str],
        workflow: dict[str, Any] | None = None,
        name: str = "mock preset",
        controls: dict[str, Any] | None = None,
        control_nodes: dict[str, Any] | None = None,
        size_patches: list[dict[str, Any]] | None = None,
        preset_id: str | None = None,
    ) -> str:
        art_id = preset_id or f"art_wf_{uuid.uuid4().hex[:10]}"
        wf = workflow or {
            "1": {
                "class_type": "EmptyImage",
                "inputs": {"width": 64, "height": 48, "batch_size": 1, "color": 0},
            },
            "2": {
                "class_type": "SaveImage",
                "inputs": {"filename_prefix": "mock", "images": ["1", 0]},
            },
        }
        preset_meta: dict[str, Any] = {"name": name, "tags": list(tags)}
        if controls:
            preset_meta["controls"] = controls
        if control_nodes:
            preset_meta["control_nodes"] = control_nodes
        if size_patches:
            # Store on metadata so pipeline can read via normalize; also keep on record.
            pass
        meta = {"preset": preset_meta, "provenance": {"generated_by": "mock_synesyn_hub"}}
        rec = {
            "id": art_id,
            "artifact_type": "json.workflow",
            "uri": f"mock://artifacts/{art_id}",
            "hash": "wf",
            "created_at": time.time(),
            "metadata": meta,
            "metadata_json": json.dumps(meta),
            "inline_json": wf,
        }
        # Expose size_patches / controls at top-level via metadata for our normalizer.
        if size_patches:
            meta["preset"]["size_patches"] = size_patches
            # Also stash where Lumur local presets put them (pipeline reads preset keys).
            rec["_size_patches"] = size_patches
        with self.state.lock:
            self.state.artifacts[art_id] = rec
        return art_id

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> MockSynesynHubServer:
        self.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.stop()
