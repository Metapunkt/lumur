"""Lean local UDP JSON event bus (ADR 0014).

Companion sends footstep / presence / zone / gathering events as one JSON
object per datagram. Godot listens with PacketPeerUDP. No framing, no TLS —
loopback / LAN only for the first milestone.
"""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SCHEMA = "lumur.event"
SCHEMA_VERSION = "1.0"


def encode_event(payload: dict[str, Any]) -> bytes:
    """Wrap a typed event dict in the transport envelope."""
    doc = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "event": payload,
    }
    return (json.dumps(doc, separators=(",", ":")) + "\n").encode("utf-8")


def decode_datagram(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8").strip()
    doc = json.loads(text)
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"unexpected event schema {doc.get('schema')!r}")
    if "event" not in doc:
        raise ValueError("event envelope missing 'event'")
    return doc


@dataclass
class EventSender:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    _sock: socket.socket | None = None

    def __post_init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)

    def send(self, payload: dict[str, Any]) -> None:
        assert self._sock is not None
        self._sock.sendto(encode_event(payload), (self.host, self.port))

    def send_footstep(self, event: Any) -> None:
        if hasattr(event, "to_dict"):
            self.send(event.to_dict())
        else:
            self.send(dict(event))

    def send_audience(self, event: Any) -> None:
        """Send presence / zone_enter / zone_leave / gathering (or footstep)."""
        if hasattr(event, "to_dict"):
            self.send(event.to_dict())
        else:
            self.send(dict(event))

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None


@dataclass
class EventReceiver:
    """Python mock of the Godot UDP listener (for headless tests)."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    _sock: socket.socket | None = None

    def bind(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.setblocking(False)

    def poll(self, max_messages: int = 64) -> list[dict[str, Any]]:
        assert self._sock is not None
        out: list[dict[str, Any]] = []
        for _ in range(max_messages):
            try:
                data, _addr = self._sock.recvfrom(65535)
            except BlockingIOError:
                break
            out.append(decode_datagram(data))
        return out

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
