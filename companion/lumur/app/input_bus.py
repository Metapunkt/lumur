"""Per-app room input event bus (PRD-003 slice 2 / ADR 0019).

Companion audience + footstep events remain the ADR 0014 vocabulary on
``lumur.event``. This module is the runtime fan-out: each registered app
receives only the types listed in its manifest ``inputs`` allowlist.
Undeclared subscriptions are refused and logged. Delivery annotates fitted
surface coordinates (``surface_key`` / ``surface_id`` / ``position_surface``)
from the app's room fit — never projector pixels.

Lumur core — no Synesyn imports.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from lumur.app.fit import FitResult, SurfaceBinding
from lumur.schema.app import KNOWN_INPUTS, validate_app_manifest

logger = logging.getLogger("lumur.app.input_bus")

EventHandler = Callable[[dict[str, Any]], None]

# Events that carry floor surface u/v and should be tagged with the app's
# fitted floor binding when present.
_POSITIONED_TYPES = frozenset({"footstep", "zone_enter", "zone_leave"})


@dataclass
class RefusedSubscription:
    """One refused subscribe() attempt (undeclared input type)."""

    app_id: str
    event_type: str
    reason: str = "undeclared_input"

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_id": self.app_id,
            "event_type": self.event_type,
            "reason": self.reason,
        }


@dataclass
class AppInputSession:
    """Filtered view of the room input bus for one registered app (or host)."""

    app_id: str
    allowed: frozenset[str]
    bindings: dict[str, SurfaceBinding] = field(default_factory=dict)
    is_host: bool = False
    paused: bool = False
    delivered: list[dict[str, Any]] = field(default_factory=list)
    _handlers: dict[str, list[EventHandler]] = field(default_factory=dict)
    _catch_all: list[EventHandler] = field(default_factory=list)

    def allows(self, event_type: str) -> bool:
        return event_type in self.allowed

    def set_paused(self, paused: bool) -> None:
        """Paused apps keep subscriptions but receive no events (REQ-003-011)."""
        self.paused = bool(paused)

    def subscribe(
        self, event_type: str, handler: EventHandler | None = None
    ) -> bool:
        """Subscribe to one declared type. Returns False if undeclared."""
        if event_type not in self.allowed:
            return False
        if handler is not None:
            self._handlers.setdefault(event_type, []).append(handler)
        return True

    def subscribe_all(self, handler: EventHandler) -> None:
        """Receive every event type this session is allowed to see."""
        self._catch_all.append(handler)

    def stream(self) -> list[dict[str, Any]]:
        """Copy of delivered events in bus order (deterministic)."""
        return [dict(e) for e in self.delivered]

    def types_seen(self) -> list[str]:
        return [str(e.get("type", "")) for e in self.delivered]

    def clear(self) -> None:
        self.delivered.clear()

    def floor_binding(self) -> SurfaceBinding | None:
        """Prefer an exact ``floor`` key, else any floor-role binding."""
        if "floor" in self.bindings:
            return self.bindings["floor"]
        for binding in self.bindings.values():
            if binding.role_requested == "floor" or "floor" in binding.roles:
                return binding
            if binding.surface_id is not None and (
                "floor" in binding.roles or binding.role_requested == "floor"
            ):
                return binding
        return None


@dataclass
class AppInputBus:
    """Room input devices → per-app filtered delivery (ADR 0019).

    The companion may still emit the full vocabulary over UDP; this bus is the
    API contract for well-behaved apps and for headless tests.
    """

    apps: dict[str, AppInputSession] = field(default_factory=dict)
    refused: list[RefusedSubscription] = field(default_factory=list)
    published: list[dict[str, Any]] = field(default_factory=list)
    _seq: int = 0

    def register_app(
        self,
        manifest: Mapping[str, Any],
        *,
        fit: FitResult | None = None,
        bindings: Mapping[str, SurfaceBinding] | None = None,
    ) -> AppInputSession:
        """Register an app from its validated ``lumur.app`` manifest.

        ``inputs`` is the allowlist. Empty list → display-only (no room events).
        """
        validate_app_manifest(dict(manifest))
        app_id = str(manifest["id"])
        allowed = frozenset(str(x) for x in (manifest.get("inputs") or []))
        unknown = allowed - KNOWN_INPUTS
        if unknown:
            raise ValueError(f"unknown input permissions: {sorted(unknown)}")

        bound: dict[str, SurfaceBinding] = {}
        if bindings is not None:
            bound = dict(bindings)
        elif fit is not None:
            bound = dict(fit.bindings)

        session = AppInputSession(
            app_id=app_id,
            allowed=allowed,
            bindings=bound,
            is_host=False,
        )
        self.apps[app_id] = session
        return session

    def register_host(
        self,
        host_id: str,
        *,
        allowed: Sequence[str],
    ) -> AppInputSession:
        """Privileged host / launcher path (not an ordinary app manifest).

        Used later for optional zone→app switching (REQ-003-013). Filtering is
        still explicit — hosts name their vocabulary rather than receiving a
        silent firehose.
        """
        allow = frozenset(str(x) for x in allowed)
        unknown = allow - KNOWN_INPUTS
        if unknown:
            raise ValueError(f"unknown host input types: {sorted(unknown)}")
        session = AppInputSession(
            app_id=str(host_id),
            allowed=allow,
            bindings={},
            is_host=True,
        )
        self.apps[session.app_id] = session
        return session

    def unregister(self, app_id: str) -> None:
        self.apps.pop(app_id, None)

    def get(self, app_id: str) -> AppInputSession | None:
        return self.apps.get(app_id)

    def set_paused(self, app_id: str, paused: bool) -> bool:
        """Pause/resume event delivery for an app. Returns False if unknown."""
        session = self.apps.get(app_id)
        if session is None:
            return False
        session.set_paused(paused)
        return True

    def subscribe(
        self,
        app_id: str,
        event_type: str,
        handler: EventHandler | None = None,
    ) -> bool:
        """Subscribe ``app_id`` to ``event_type``.

        Undeclared types are refused, logged, and recorded on ``refused``.
        """
        session = self.apps.get(app_id)
        if session is None:
            refusal = RefusedSubscription(
                app_id=app_id,
                event_type=event_type,
                reason="unknown_app",
            )
            self.refused.append(refusal)
            logger.warning(
                "refused input subscription app=%s type=%s reason=%s",
                app_id,
                event_type,
                refusal.reason,
            )
            return False
        if not session.subscribe(event_type, handler):
            refusal = RefusedSubscription(
                app_id=app_id,
                event_type=event_type,
                reason="undeclared_input",
            )
            self.refused.append(refusal)
            logger.warning(
                "refused input subscription app=%s type=%s reason=%s "
                "allowed=%s",
                app_id,
                event_type,
                refusal.reason,
                sorted(session.allowed),
            )
            return False
        return True

    def publish(self, event: Any) -> dict[str, list[dict[str, Any]]]:
        """Fan-out one room event to every registered app that allows its type.

        Returns ``{app_id: [delivered_event, ...]}`` for apps that received it
        (at most one delivery per app). Order of ``apps`` iteration is
        insertion order (deterministic).
        """
        payload = _normalize_event(event)
        ev_type = str(payload.get("type", ""))
        self._seq += 1
        envelope = dict(payload)
        envelope["_bus_seq"] = self._seq
        self.published.append(dict(envelope))

        delivered: dict[str, list[dict[str, Any]]] = {}
        for app_id, session in self.apps.items():
            if session.paused and not session.is_host:
                continue
            if not session.allows(ev_type):
                continue
            app_event = _fit_event_for_app(envelope, session)
            session.delivered.append(app_event)
            for handler in session._handlers.get(ev_type, []):
                handler(app_event)
            for handler in session._catch_all:
                handler(app_event)
            delivered[app_id] = [app_event]
        return delivered

    def inject(self, event: Any) -> dict[str, list[dict[str, Any]]]:
        """Test helper alias for :meth:`publish` (no hardware / UDP)."""
        return self.publish(event)

    def publish_batch(
        self, events: Sequence[Any]
    ) -> dict[str, list[dict[str, Any]]]:
        """Publish many events in order; return per-app concatenated streams."""
        out: dict[str, list[dict[str, Any]]] = {aid: [] for aid in self.apps}
        for event in events:
            batch = self.publish(event)
            for app_id, items in batch.items():
                out.setdefault(app_id, []).extend(items)
        return out

    def clear_streams(self) -> None:
        self.published.clear()
        self._seq = 0
        for session in self.apps.values():
            session.clear()

    def streams(self) -> dict[str, list[dict[str, Any]]]:
        """Snapshot of every app's delivered stream (bus order)."""
        return {aid: s.stream() for aid, s in self.apps.items()}

    def replay(
        self, events: Sequence[Any]
    ) -> dict[str, list[dict[str, Any]]]:
        """Clear per-app streams and re-publish ``events`` deterministically."""
        self.clear_streams()
        return self.publish_batch(events)

    def refused_log(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.refused]


def _normalize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "to_dict"):
        payload = dict(event.to_dict())
    elif isinstance(event, Mapping):
        payload = dict(event)
        # Unwrap ADR 0014 envelope if present.
        if payload.get("schema") == "lumur.event" and "event" in payload:
            payload = dict(payload["event"])
    else:
        raise TypeError(f"unsupported event type: {type(event)!r}")
    if "type" not in payload:
        raise ValueError("event missing type")
    return payload


def _fit_event_for_app(
    event: Mapping[str, Any], session: AppInputSession
) -> dict[str, Any]:
    """Copy event and attach fitted surface coordinates when applicable.

    Floor-positioned events keep ``position_floor`` (room floor UV) and add
    ``position_surface`` plus the app's bound floor ``surface_key`` /
    ``surface_id``. Projector / pixel placement is never invented.
    """
    out = dict(event)
    out["app_id"] = session.app_id
    floor = session.floor_binding()
    if floor is not None and floor.surface_id is not None:
        out["surface_key"] = floor.key
        out["surface_id"] = int(floor.surface_id)
        pf = out.get("position_floor")
        if (
            str(out.get("type", "")) in _POSITIONED_TYPES
            and isinstance(pf, (list, tuple))
            and len(pf) >= 2
        ):
            out["position_surface"] = [float(pf[0]), float(pf[1])]
    return out
