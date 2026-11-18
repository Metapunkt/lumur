"""Hub URL + optional Bearer token (never commit secrets)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class HubConfig:
    """Synesyn Hub connection settings for the optional Lumur bridge."""

    hub_base_url: str
    auth_token: str = ""
    auth_enabled: bool = False
    comfy_base_url: str = "http://127.0.0.1:8188"
    timeout_sec: float = 180.0
    poll_interval_sec: float = 0.5

    def normalized_url(self) -> str:
        return self.hub_base_url.strip().rstrip("/")

    def bearer_headers(self) -> dict[str, str]:
        if not self.auth_enabled:
            return {}
        token = self.auth_token.strip()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}


def load_hub_config(
    *,
    hub_url: str | None = None,
    auth_token: str | None = None,
    auth_enabled: bool | None = None,
    comfy_url: str | None = None,
    config_path: str | Path | None = None,
    timeout_sec: float | None = None,
) -> HubConfig:
    """Resolve Hub settings from args, env, then optional JSON config file.

    Env (preferred for secrets)::

        LUMUR_SYNESYN_HUB_URL
        LUMUR_SYNESYN_HUB_TOKEN
        LUMUR_SYNESYN_HUB_AUTH=1
        LUMUR_SYNESYN_COMFY_URL

    Config file (optional, do not commit tokens)::

        {
          "hub": {
            "base_url": "http://127.0.0.1:8787",
            "auth": {"enabled": false, "token": ""},
            "comfy_base_url": "http://127.0.0.1:8188"
          }
        }
    """
    file_cfg: dict[str, Any] = {}
    if config_path:
        path = Path(config_path)
        if path.is_file():
            raw = json.loads(path.read_text(encoding="utf-8"))
            hub = raw.get("hub") if isinstance(raw, dict) else {}
            file_cfg = dict(hub) if isinstance(hub, dict) else {}

    env_url = os.environ.get("LUMUR_SYNESYN_HUB_URL", "").strip()
    env_token = os.environ.get("LUMUR_SYNESYN_HUB_TOKEN", "").strip()
    env_auth = os.environ.get("LUMUR_SYNESYN_HUB_AUTH", "").strip().lower()
    env_comfy = os.environ.get("LUMUR_SYNESYN_COMFY_URL", "").strip()

    auth_block = file_cfg.get("auth") if isinstance(file_cfg.get("auth"), dict) else {}
    url = (
        (hub_url or "").strip()
        or env_url
        or str(file_cfg.get("base_url") or "").strip()
    )
    if not url:
        raise ValueError(
            "hub_base_url required (pass --hub-url, set LUMUR_SYNESYN_HUB_URL, "
            "or provide a config file)"
        )

    token = (
        (auth_token if auth_token is not None else "").strip()
        or env_token
        or str(auth_block.get("token") or "").strip()
    )
    if auth_enabled is None:
        if env_auth in ("1", "true", "yes", "on"):
            enabled = True
        elif env_auth in ("0", "false", "no", "off"):
            enabled = False
        else:
            enabled = bool(auth_block.get("enabled", False)) or bool(token)
    else:
        enabled = bool(auth_enabled)

    comfy = (
        (comfy_url or "").strip()
        or env_comfy
        or str(file_cfg.get("comfy_base_url") or "").strip()
        or "http://127.0.0.1:8188"
    )
    return HubConfig(
        hub_base_url=url,
        auth_token=token,
        auth_enabled=enabled,
        comfy_base_url=comfy.rstrip("/"),
        timeout_sec=float(timeout_sec if timeout_sec is not None else 180.0),
    )
