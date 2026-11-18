# 0014 — Local UDP JSON for companion → Godot events

- **Status:** Accepted (refined by [ADR 0019](0019-app-input-permissions.md)
  for per-app delivery filtering; transport unchanged)
- **Date:** 2026-11-18
- **Area:** runtime / interchange / interaction
- **Relates to:** ADR 0004, ADR 0005, ADR 0006, ADR 0019; PRD-001, PRD-003

## Context

Footstep ripples need the Python companion to deliver room-input events
(person id, foot, floor position, timestamp) into Godot apps. The companion
already owns capture and pose; Godot owns projection. A transport must stay
lean for loopback / LAN demos, easy to mock in headless tests, and replaceable
later without rewriting apps.

## Options considered

1. **WebSocket (JSON).** Bidirectional, familiar, but needs a handshake,
   framing, and a small server even for one local client.
2. **gRPC / protobuf.** Strong schema; overweight for a single event type on
   localhost, and GDScript support is poor without extras.
3. **Shared memory / file drop.** Awkward for streaming; harder for Godot.
4. **Local UDP datagrams carrying one JSON object each.** Fire-and-forget,
   trivial in both Python (`socket`) and Godot (`PacketPeerUDP`), easy to
   record and replay.

## Decision

Option 4. Envelope:

```json
{"schema":"lumur.event","schema_version":"1.0","event":{...}}
```

Default bind is `127.0.0.1:8765`. No TLS, no multi-client fan-out, no
guaranteed delivery — acceptable for presence / footstep effects where a
dropped datagram means a missed ripple, not a corrupt room.

Godot’s `LumurEventReceiver` listens; apps subscribe to signals. Python tests
use `EventReceiver` as a mock Godot. A later ADR may introduce WebSocket or a
Unix socket if reliability or discovery becomes a product need.

## Consequences

- Positive: zero new required dependencies; headless e2e is a few dozen lines.
- Positive: apps depend on the event dict shape, not on pose models (ADR 0006).
- Trade-off: unordered / lossy under load; fine for ripples, not for
  authoritative state sync.
- Follow-up: optional sequence numbers or a reliable channel when a second
  app needs them.
