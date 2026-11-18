"""Minimal in-process ComfyUI HTTP (+ WebSocket progress) stub for tests."""

from __future__ import annotations

import json
import struct
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

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


class MockComfyUIState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.uploads: dict[str, bytes] = {}
        self.history: dict[str, dict[str, Any]] = {}
        self.outputs: dict[str, bytes] = {}
        self.prompts: list[dict[str, Any]] = []
        self.fail_next = False
        self.timeout_next = False
        self.delay_sec = 0.05
        self.ws_clients: list[socket_wrapper] = []
        self.object_info = {"EmptyImage": {}, "SaveImage": {}, "LoadImage": {}}
        self.system_stats = {"system": {"comfyui": "mock"}}


class socket_wrapper:
    """Track a connected WS client socket for progress fan-out."""

    def __init__(self, sock: Any) -> None:
        self.sock = sock
        self.alive = True


def _ws_send_text(sock: Any, payload: dict[str, Any]) -> None:
    data = json.dumps(payload).encode("utf-8")
    header = bytes([0x81])  # fin + text
    n = len(data)
    if n < 126:
        header += bytes([n])
    elif n < 65536:
        header += bytes([126]) + struct.pack("!H", n)
    else:
        header += bytes([127]) + struct.pack("!Q", n)
    try:
        sock.sendall(header + data)
    except OSError:
        pass


class MockComfyUIServer:
    """Threading HTTP server mimicking ComfyUI's upload/prompt/history/view/ws."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0) -> None:
        self.state = MockComfyUIState()
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
                self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

            def do_GET(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/system_stats":
                    self._send_json(200, parent.state.system_stats)
                    return
                if path == "/object_info":
                    self._send_json(200, parent.state.object_info)
                    return
                if path.startswith("/history/"):
                    pid = path[len("/history/") :]
                    with parent.state.lock:
                        entry = parent.state.history.get(pid)
                        if entry is None:
                            self._send_json(200, {})
                        else:
                            self._send_json(200, {pid: entry})
                    return
                if path == "/history":
                    with parent.state.lock:
                        self._send_json(200, dict(parent.state.history))
                    return
                if path == "/view":
                    qs = parse_qs(parsed.query)
                    filename = (qs.get("filename") or [""])[0]
                    with parent.state.lock:
                        data = parent.state.outputs.get(filename)
                    if data is None:
                        self._send_json(404, {"error": "not_found"})
                        return
                    self._send(200, data, "image/png")
                    return
                if path == "/ws":
                    self._handle_ws()
                    return
                self._send_json(404, {"error": "not_found", "path": path})

            def do_POST(self) -> None:  # noqa: N802
                parsed = urlparse(self.path)
                path = parsed.path
                if path == "/upload/image":
                    self._handle_upload()
                    return
                if path == "/prompt":
                    self._handle_prompt()
                    return
                self._send_json(404, {"error": "not_found", "path": path})

            def _handle_upload(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                # Extremely small multipart parse: find filename= and body after headers.
                filename = f"upload_{uuid.uuid4().hex[:8]}.png"
                marker = b'filename="'
                idx = raw.find(marker)
                if idx >= 0:
                    start = idx + len(marker)
                    end = raw.find(b'"', start)
                    if end > start:
                        filename = raw[start:end].decode("utf-8", errors="replace")
                sep = raw.find(b"\r\n\r\n")
                file_bytes = raw[sep + 4 :] if sep >= 0 else raw
                # Trim trailing boundary.
                end_bound = file_bytes.rfind(b"\r\n--")
                if end_bound > 0:
                    file_bytes = file_bytes[:end_bound]
                subfolder = "lumur"
                # sniff subfolder field
                if b'name="subfolder"' in raw:
                    sidx = raw.find(b'name="subfolder"')
                    ssep = raw.find(b"\r\n\r\n", sidx)
                    if ssep > 0:
                        send = raw.find(b"\r\n", ssep + 4)
                        if send > ssep:
                            subfolder = raw[ssep + 4 : send].decode("utf-8", errors="replace")
                with parent.state.lock:
                    parent.state.uploads[f"{subfolder}/{filename}"] = file_bytes
                self._send_json(200, {"name": filename, "subfolder": subfolder, "type": "input"})

            def _handle_prompt(self) -> None:
                body = self._read_json()
                workflow = body.get("prompt") if isinstance(body.get("prompt"), dict) else {}
                client_id = str(body.get("client_id") or "")
                with parent.state.lock:
                    parent.state.prompts.append(body)
                    fail = parent.state.fail_next
                    timeout = parent.state.timeout_next
                    delay = parent.state.delay_sec
                    if fail:
                        parent.state.fail_next = False
                    if timeout:
                        parent.state.timeout_next = False
                if fail:
                    self._send_json(400, {"error": {"message": "mock_fail", "type": "invalid_prompt"}})
                    return
                prompt_id = uuid.uuid4().hex
                self._send_json(200, {"prompt_id": prompt_id, "number": 1})

                def _complete() -> None:
                    if timeout:
                        # Never write history — client should time out.
                        return
                    width, height = _extract_size(workflow)
                    filename = f"mock_{prompt_id[:8]}.png"
                    data = _png_bytes(width, height)
                    # Emit WS progress if clients connected.
                    parent._broadcast(
                        {"type": "progress", "data": {"value": 1, "max": 4, "prompt_id": prompt_id}}
                    )
                    time.sleep(max(0.0, delay * 0.4))
                    parent._broadcast(
                        {"type": "progress", "data": {"value": 3, "max": 4, "prompt_id": prompt_id}}
                    )
                    time.sleep(max(0.0, delay * 0.4))
                    parent._broadcast(
                        {
                            "type": "executing",
                            "data": {"node": None, "prompt_id": prompt_id},
                        }
                    )
                    entry = {
                        "prompt": [0, prompt_id, workflow],
                        "outputs": {
                            "2": {
                                "images": [
                                    {
                                        "filename": filename,
                                        "subfolder": "",
                                        "type": "output",
                                    }
                                ]
                            }
                        },
                        "status": {"status_str": "success", "completed": True},
                    }
                    with parent.state.lock:
                        parent.state.outputs[filename] = data
                        parent.state.history[prompt_id] = entry

                threading.Thread(target=_complete, name="mock-comfy-job", daemon=True).start()
                _ = client_id  # reserved for WS filtering

            def _handle_ws(self) -> None:
                key = self.headers.get("Sec-WebSocket-Key", "")
                accept = __import__("base64").b64encode(
                    __import__("hashlib")
                    .sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8"))
                    .digest()
                ).decode("ascii")
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                wrap = socket_wrapper(self.connection)
                with parent.state.lock:
                    parent.state.ws_clients.append(wrap)
                # Keep the handler thread alive until the client disconnects or server stops.
                try:
                    while parent._running and wrap.alive:
                        try:
                            self.connection.settimeout(0.5)
                            data = self.connection.recv(1)
                            if not data:
                                break
                        except OSError:
                            continue
                finally:
                    wrap.alive = False

        self._handler = Handler
        self._httpd = ThreadingHTTPServer((host, port), Handler)
        self.host, self.port = self._httpd.server_address[:2]
        self.base_url = f"http://{self.host}:{self.port}"
        self._thread: threading.Thread | None = None
        self._running = False

    def _broadcast(self, payload: dict[str, Any]) -> None:
        with self.state.lock:
            clients = list(self.state.ws_clients)
        for c in clients:
            if c.alive:
                _ws_send_text(c.sock, payload)

    def start(self) -> str:
        self._running = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.base_url

    def stop(self) -> None:
        self._running = False
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> MockComfyUIServer:
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.stop()
