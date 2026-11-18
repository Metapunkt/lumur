"""Room input event transport (companion → Godot). See ADR 0014."""

from lumur.events.udp_json import EventReceiver, EventSender, encode_event

__all__ = ["EventSender", "EventReceiver", "encode_event"]
