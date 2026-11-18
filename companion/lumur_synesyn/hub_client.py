"""HTTP client for Synesyn Hub endpoints used by the Lumur bridge.

Mirrors shapes from ``Metapunkt/Synesyn`` (read-only reference):
``POST /render/submit``, ``GET /render/jobs/{id}``,
``POST /substrate/artifacts``, ``POST /substrate/query``, ``GET /health``.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from lumur_synesyn.config import HubConfig


class HubError(RuntimeError):
    """Hub HTTP / protocol failure."""


class HubAuthError(HubError):
    """Missing or invalid Bearer token (HTTP 401/403)."""


class HubTimeout(TimeoutError):
    """Render job poll exceeded the configured timeout."""


ProgressCallback = Callable[[float], None]


class SynesynHubClient:
    """Minimal Hub facade — stdlib only, no Synesyn Python package required."""

    def __init__(self, config: HubConfig) -> None:
        self.config = config
        self.base_url = config.normalized_url()

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if json_body:
            headers["Content-Type"] = "application/json"
        headers.update(self.config.bearer_headers())
        return headers

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        timeout_sec: float = 30.0,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}" if path.startswith("/") else f"{self.base_url}/{path}"
        data = None
        headers = self._headers(json_body=body is not None)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = Request(url=url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=timeout_sec) as resp:
                raw = resp.read().decode("utf-8") if resp else ""
                code = getattr(resp, "status", 200) or 200
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            if exc.code in (401, 403):
                raise HubAuthError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc
            raise HubError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise HubError(f"{method} {url} failed: {exc}") from exc
        obj = json.loads(raw) if raw else {}
        if not isinstance(obj, dict):
            raise HubError(f"invalid JSON object from {url}")
        # Some Hub paths return ok:false with 200; surface that.
        if obj.get("ok") is False and code >= 400:
            raise HubError(str(obj.get("error") or obj))
        return obj

    def ping(self) -> dict[str, Any]:
        try:
            res = self._request("GET", "/health", timeout_sec=5.0)
            return {
                "ok": bool(res.get("ok", False)),
                "provider": "synesyn_hub",
                "hub_url": self.base_url,
                "health": res,
            }
        except HubError as exc:
            return {"ok": False, "provider": "synesyn_hub", "error": str(exc)}

    def create_artifact_bytes(
        self,
        artifact_type: str,
        data: bytes,
        *,
        ext: str = "png",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "artifact_type": artifact_type,
            "inline_bytes_base64": base64.b64encode(data).decode("ascii"),
            "ext": ext.lstrip("."),
            "metadata": metadata or {},
        }
        res = self._request("POST", "/substrate/artifacts", payload)
        art_id = str(res.get("id") or res.get("artifact_id") or "").strip()
        if not art_id:
            raise HubError(f"create artifact returned no id: {res}")
        return art_id

    def create_artifact_json(
        self,
        artifact_type: str,
        inline_json: dict[str, Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "artifact_type": artifact_type,
            "inline_json": inline_json,
            "metadata": metadata or {},
        }
        res = self._request("POST", "/substrate/artifacts", payload)
        art_id = str(res.get("id") or res.get("artifact_id") or "").strip()
        if not art_id:
            raise HubError(f"create artifact returned no id: {res}")
        return art_id

    def query_artifacts_by_type(
        self, artifact_type: str, *, limit: int = 100
    ) -> list[dict[str, Any]]:
        payload = {
            "table": "artifacts",
            "where": {"artifact_type": artifact_type},
            "limit": int(max(1, min(limit, 200))),
        }
        res = self._request("POST", "/substrate/query", payload)
        result = res.get("result") if isinstance(res.get("result"), dict) else {}
        cols = [str(c) for c in (result.get("columns") or [])]
        rows = result.get("rows") or []
        out: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, (list, tuple)):
                continue
            rec = {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
            meta = rec.get("metadata_json") or rec.get("metadata") or {}
            if isinstance(meta, str) and meta.strip():
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            rec["metadata"] = meta
            out.append(rec)
        return out

    def get_artifact_record(self, artifact_id: str) -> dict[str, Any]:
        payload = {
            "table": "artifacts",
            "where": {"id": artifact_id},
            "limit": 1,
        }
        res = self._request("POST", "/substrate/query", payload)
        result = res.get("result") if isinstance(res.get("result"), dict) else {}
        cols = [str(c) for c in (result.get("columns") or [])]
        rows = result.get("rows") or []
        if not rows:
            raise HubError(f"Artifact not found: {artifact_id}")
        row = rows[0]
        rec = {cols[i]: row[i] for i in range(min(len(cols), len(row)))}
        meta = rec.get("metadata_json") or rec.get("metadata") or {}
        if isinstance(meta, str) and meta.strip():
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        if not isinstance(meta, dict):
            meta = {}
        rec["metadata"] = meta
        return rec

    def _get_content_raw(self, artifact_id: str) -> tuple[bytes, str]:
        """GET ``/substrate/artifacts/{id}/content`` → (body, content-type)."""
        url = f"{self.base_url}/substrate/artifacts/{artifact_id}/content"
        req = Request(url=url, headers=self._headers(), method="GET")
        try:
            with urlopen(req, timeout=60.0) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                return resp.read(), ctype
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise HubError(
                f"GET artifact content failed ({exc.code}): {detail}. "
                "Synesyn Hub currently exposes file:// URIs; remote byte download "
                "is a documented Synesyn-side touchpoint."
            ) from exc
        except URLError as exc:
            raise HubError(f"GET artifact content failed: {exc}") from exc

    def get_artifact_json(self, artifact_id: str) -> dict[str, Any]:
        rec = self.get_artifact_record(artifact_id)
        inline = rec.get("inline_json")
        if isinstance(inline, dict):
            return inline
        uri = str(rec.get("uri") or "").strip()
        if uri.startswith("file:"):
            path = _file_uri_to_path(uri)
            raw = path.read_text(encoding="utf-8")
            obj = json.loads(raw) if raw else {}
            if not isinstance(obj, dict):
                raise HubError(f"artifact JSON is not an object: {artifact_id}")
            return obj
        # Optional content endpoint (mock + needed remote-Hub touchpoint).
        try:
            data, ctype = self._get_content_raw(artifact_id)
            if "application/json" in ctype or data[:1] in (b"{", b"["):
                obj = json.loads(data.decode("utf-8") or "{}")
                if isinstance(obj, dict) and isinstance(obj.get("json"), dict):
                    return dict(obj["json"])
                if isinstance(obj, dict) and isinstance(obj.get("inline_json"), dict):
                    return dict(obj["inline_json"])
                if isinstance(obj, dict) and obj and "ok" not in obj and "error" not in obj:
                    # Raw workflow graph JSON (node_id → {class_type, inputs}).
                    if all(isinstance(v, dict) for v in obj.values()):
                        return obj
        except HubError:
            pass
        raise HubError(f"cannot load JSON for artifact {artifact_id} (uri={uri!r})")

    def get_artifact_bytes(self, artifact_id: str) -> bytes:
        rec = self.get_artifact_record(artifact_id)
        inline_b64 = rec.get("inline_bytes_base64")
        if isinstance(inline_b64, str) and inline_b64:
            return base64.b64decode(inline_b64)
        uri = str(rec.get("uri") or "").strip()
        if uri.startswith("file:"):
            return _file_uri_to_path(uri).read_bytes()
        if uri.startswith("http://") or uri.startswith("https://"):
            req = Request(url=uri, headers=self._headers(), method="GET")
            with urlopen(req, timeout=60.0) as resp:
                return resp.read()
        data, ctype = self._get_content_raw(artifact_id)
        if "application/json" in ctype:
            obj = json.loads(data.decode("utf-8") or "{}")
            if isinstance(obj, dict) and obj.get("inline_bytes_base64"):
                return base64.b64decode(str(obj["inline_bytes_base64"]))
            raise HubError(f"content endpoint returned JSON without bytes: {artifact_id}")
        return data

    def submit_render(self, render_request: dict[str, Any]) -> str:
        res = self._request(
            "POST",
            "/render/submit",
            {"request": render_request},
            timeout_sec=30.0,
        )
        job_id = str(res.get("job_id") or res.get("id") or "").strip()
        if not job_id:
            raise HubError(f"/render/submit returned no job_id: {res}")
        return job_id

    def get_render_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/render/jobs/{job_id}", timeout_sec=15.0)

    def poll_render_until_done(
        self,
        job_id: str,
        *,
        timeout_sec: float = 180.0,
        poll_interval_sec: float = 0.5,
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        t0 = time.time()
        last: dict[str, Any] = {}
        while True:
            last = self.get_render_job(job_id)
            status = str(last.get("status") or "").strip().lower()
            # Progress best-effort from output or a percent field.
            output = last.get("output") if isinstance(last.get("output"), dict) else {}
            pct = output.get("percent")
            if pct is None:
                pct = last.get("percent")
            if on_progress and pct is not None:
                try:
                    on_progress(float(pct))
                except (TypeError, ValueError):
                    pass
            elif on_progress:
                # Time-based soft progress while queued/running.
                elapsed = time.time() - t0
                soft = min(90.0, 5.0 + (elapsed / max(timeout_sec, 1.0)) * 80.0)
                if status in ("queued", "running", "started"):
                    on_progress(soft)
            if status in ("completed", "succeeded", "success"):
                if on_progress:
                    on_progress(100.0)
                return last
            if status in ("failed", "error", "canceled", "cancelled"):
                return last
            if (time.time() - t0) > timeout_sec:
                raise HubTimeout(f"render job {job_id} timed out after {timeout_sec}s (status={status})")
            time.sleep(poll_interval_sec)


def _file_uri_to_path(uri: str):
    from pathlib import Path

    u = (uri or "").strip()
    if u.startswith("file://"):
        p = unquote(urlparse(u).path or "")
        if len(p) > 2 and p[0] == "/" and p[2] == ":":
            p = p[1:]
        return Path(p)
    return Path(u)
