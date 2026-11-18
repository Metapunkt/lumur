"""Direct ComfyUI HTTP (+ optional WebSocket progress) client.

Uses only the standard library so the companion stays lean. Completion is
determined by polling ``/history/{prompt_id}``; WebSocket messages refine
progress when available (ComfyUI ``/ws?clientId=``).
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading
import time
import uuid
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class ComfyUIError(RuntimeError):
    """ComfyUI HTTP / protocol failure."""


class ComfyUITimeout(TimeoutError):
    """History poll exceeded the configured timeout."""


def _post_json(url: str, payload: dict[str, Any], timeout_sec: float = 30.0) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8") if resp else ""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ComfyUIError(f"POST {url} -> HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ComfyUIError(f"POST {url} failed: {exc}") from exc
    obj = json.loads(raw) if raw else {}
    if not isinstance(obj, dict):
        raise ComfyUIError(f"invalid JSON object from {url}")
    return obj


def _get_json(url: str, timeout_sec: float = 12.0) -> dict[str, Any]:
    req = Request(url=url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8") if resp else ""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ComfyUIError(f"GET {url} -> HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ComfyUIError(f"GET {url} failed: {exc}") from exc
    obj = json.loads(raw) if raw else {}
    if not isinstance(obj, dict):
        raise ComfyUIError(f"invalid JSON object from {url}")
    return obj


def _get_bytes(url: str, timeout_sec: float = 60.0) -> bytes:
    req = Request(url=url, headers={"Accept": "*/*"}, method="GET")
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            return resp.read() if resp else b""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ComfyUIError(f"GET {url} -> HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ComfyUIError(f"GET {url} failed: {exc}") from exc


def multipart_body(
    fields: dict[str, str],
    *,
    file_field: str,
    filename: str,
    data: bytes,
) -> tuple[bytes, str]:
    boundary = f"----lumur{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    safe_name = filename.replace('"', "_")
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; '
            f'filename="{safe_name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8")
        + data
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _post_multipart(
    url: str, body: bytes, content_type: str, timeout_sec: float = 60.0
) -> dict[str, Any]:
    req = Request(
        url=url,
        data=body,
        headers={"Content-Type": content_type, "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            raw = resp.read().decode("utf-8") if resp else ""
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        raise ComfyUIError(f"POST {url} -> HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ComfyUIError(f"POST {url} failed: {exc}") from exc
    obj = json.loads(raw) if raw else {}
    if not isinstance(obj, dict):
        raise ComfyUIError(f"invalid JSON object from {url}")
    return obj


class ComfyUIClient:
    """Thin ComfyUI API wrapper."""

    def __init__(self, base_url: str, *, client_id: str | None = None) -> None:
        self.base_url = (base_url or "").strip().rstrip("/")
        if not self.base_url:
            raise ValueError("comfy_base_url is required")
        self.client_id = client_id or f"lumur_{uuid.uuid4().hex[:12]}"

    def ping(self) -> dict[str, Any]:
        # ComfyUI exposes /system_stats; fall back to /object_info.
        for path in ("/system_stats", "/object_info"):
            try:
                data = _get_json(f"{self.base_url}{path}", timeout_sec=5.0)
                return {"ok": True, "endpoint": path, "data_keys": sorted(data.keys())[:12]}
            except ComfyUIError:
                continue
        return {"ok": False, "error": "unreachable"}

    def upload_image(
        self,
        data: bytes,
        *,
        filename: str,
        subfolder: str = "lumur",
        image_type: str = "input",
        overwrite: bool = True,
    ) -> str:
        fields = {
            "type": image_type,
            "overwrite": "true" if overwrite else "false",
        }
        if subfolder:
            fields["subfolder"] = subfolder
        body, content_type = multipart_body(
            fields, file_field="image", filename=filename, data=data
        )
        res = _post_multipart(
            f"{self.base_url}/upload/image", body, content_type, timeout_sec=60.0
        )
        name = str(res.get("name") or "").strip()
        if not name:
            raise ComfyUIError(f"upload returned no name: {res}")
        sub = str(res.get("subfolder") or "").strip()
        return f"{sub}/{name}" if sub else name

    def queue_prompt(self, workflow: dict[str, Any]) -> str:
        res = _post_json(
            f"{self.base_url}/prompt",
            {"prompt": workflow, "client_id": self.client_id},
            timeout_sec=30.0,
        )
        if res.get("error"):
            raise ComfyUIError(f"ComfyUI rejected prompt: {res.get('error')}")
        pid = str(res.get("prompt_id") or "").strip()
        if not pid:
            raise ComfyUIError(f"ComfyUI missing prompt_id: {res}")
        return pid

    def get_history(self, prompt_id: str) -> dict[str, Any] | None:
        obj = _get_json(f"{self.base_url}/history/{prompt_id}", timeout_sec=12.0)
        entry = obj.get(prompt_id)
        return entry if isinstance(entry, dict) else None

    def poll_until_done(
        self,
        prompt_id: str,
        *,
        timeout_sec: float = 180.0,
        poll_interval_sec: float = 0.25,
        on_progress: Callable[[float], None] | None = None,
        fail_statuses: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        fail_statuses = fail_statuses or frozenset({"error", "failed"})
        t0 = time.time()
        while True:
            elapsed = time.time() - t0
            if elapsed > float(timeout_sec):
                raise ComfyUITimeout(
                    f"ComfyUI history poll timed out after {timeout_sec:.1f}s "
                    f"(prompt_id={prompt_id})"
                )
            if on_progress:
                # Time-based heartbeat; WS listener may override with finer values.
                on_progress(min(99.0, max(1.0, (elapsed / max(1.0, float(timeout_sec))) * 100.0)))
            entry = self.get_history(prompt_id)
            if isinstance(entry, dict):
                status_obj = entry.get("status")
                if isinstance(status_obj, dict):
                    st = str(status_obj.get("status_str") or status_obj.get("status") or "").lower()
                    if st in fail_statuses or status_obj.get("completed") is False and st == "error":
                        raise ComfyUIError(f"ComfyUI job failed: {status_obj}")
                outputs = entry.get("outputs")
                if isinstance(outputs, dict) and len(outputs) > 0:
                    if on_progress:
                        on_progress(100.0)
                    return entry
                # Explicit failure without outputs.
                if isinstance(status_obj, dict) and status_obj.get("status_str") == "error":
                    raise ComfyUIError(f"ComfyUI job failed: {status_obj}")
            time.sleep(float(poll_interval_sec))

    def fetch_image(
        self, *, filename: str, subfolder: str = "", typ: str = "output"
    ) -> bytes:
        q = urlencode(
            {
                "filename": filename,
                "subfolder": subfolder or "",
                "type": typ or "output",
            }
        )
        return _get_bytes(f"{self.base_url}/view?{q}", timeout_sec=120.0)

    def first_image_ref(self, history_entry: dict[str, Any]) -> dict[str, str]:
        outputs = history_entry.get("outputs") or {}
        if not isinstance(outputs, dict):
            raise ComfyUIError("history entry has no outputs")
        for _node_id, node_out in outputs.items():
            if not isinstance(node_out, dict):
                continue
            for key in ("images", "gifs"):
                items = node_out.get(key)
                if isinstance(items, list) and items:
                    item = items[0]
                    if isinstance(item, dict) and item.get("filename"):
                        return {
                            "filename": str(item["filename"]),
                            "subfolder": str(item.get("subfolder") or ""),
                            "type": str(item.get("type") or "output"),
                        }
        raise ComfyUIError("no image outputs in ComfyUI history")


def _ws_accept_key(sec_key: str) -> str:
    digest = hashlib.sha1(
        (sec_key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")
    ).digest()
    return base64.b64encode(digest).decode("ascii")


class ComfyUIProgressSocket:
    """Best-effort WebSocket progress listener (stdlib only)."""

    def __init__(self, base_url: str, client_id: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.progress = 0.0
        self.last_message: dict[str, Any] | None = None
        self.error: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="lumur-comfy-ws", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        scheme = parsed.scheme or "http"
        port = parsed.port or (443 if scheme == "https" else 80)
        ws_path = f"/ws?clientId={self.client_id}"
        try:
            sock = socket.create_connection((host, port), timeout=5.0)
        except OSError as exc:
            self.error = str(exc)
            return
        try:
            key = base64.b64encode(uuid.uuid4().bytes).decode("ascii")
            req = (
                f"GET {ws_path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            )
            sock.sendall(req.encode("ascii"))
            sock.settimeout(1.0)
            # Read handshake (small).
            buf = b""
            while b"\r\n\r\n" not in buf and len(buf) < 8192:
                try:
                    chunk = sock.recv(1024)
                except socket.timeout:
                    if self._stop.is_set():
                        return
                    continue
                if not chunk:
                    break
                buf += chunk
            if b"101" not in buf.split(b"\r\n", 1)[0]:
                self.error = "websocket handshake failed"
                return
            expected = _ws_accept_key(key)
            if expected.encode("ascii") not in buf:
                # Some stubs skip the accept header; continue best-effort.
                pass
            while not self._stop.is_set():
                try:
                    header = self._recv_exact(sock, 2)
                except (OSError, TimeoutError):
                    continue
                if header is None:
                    break
                b1, b2 = header[0], header[1]
                opcode = b1 & 0x0F
                masked = bool(b2 & 0x80)
                length = b2 & 0x7F
                if length == 126:
                    ext = self._recv_exact(sock, 2)
                    if ext is None:
                        break
                    length = struct.unpack("!H", ext)[0]
                elif length == 127:
                    ext = self._recv_exact(sock, 8)
                    if ext is None:
                        break
                    length = struct.unpack("!Q", ext)[0]
                mask_key = b""
                if masked:
                    mask_key = self._recv_exact(sock, 4) or b""
                payload = self._recv_exact(sock, length) or b""
                if masked and mask_key:
                    payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
                if opcode == 0x8:  # close
                    break
                if opcode == 0x1:
                    try:
                        msg = json.loads(payload.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if isinstance(msg, dict):
                        self.last_message = msg
                        self._handle_message(msg)
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _handle_message(self, msg: dict[str, Any]) -> None:
        mtype = str(msg.get("type") or "")
        data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
        if mtype == "progress":
            value = float(data.get("value") or 0.0)
            vmax = float(data.get("max") or 1.0)
            if vmax > 0:
                self.progress = max(self.progress, min(99.0, 100.0 * value / vmax))
        elif mtype == "executing":
            if data.get("node") is None:
                self.progress = max(self.progress, 99.0)
        elif mtype == "execution_error":
            self.error = str(data.get("exception_message") or data or "execution_error")

    def _recv_exact(self, sock: socket.socket, n: int) -> bytes | None:
        buf = b""
        while len(buf) < n:
            if self._stop.is_set():
                return None
            try:
                chunk = sock.recv(n - len(buf))
            except socket.timeout:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf
