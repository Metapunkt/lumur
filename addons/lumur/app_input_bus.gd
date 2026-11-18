class_name LumurAppInputBus
extends Node

## Per-app room input event bus (PRD-003 slice 2 / ADR 0019).
## Filters ``LumurEventReceiver`` (or injected) events by each app's manifest
## ``inputs`` allowlist. Undeclared subscriptions are refused and logged.
## Delivered events carry fitted surface coordinates when the app bound a floor.

signal app_event(app_id: String, event: Dictionary)
signal subscription_refused(app_id: String, event_type: String, reason: String)

const KNOWN_INPUTS := [
	"footstep",
	"presence",
	"zone_enter",
	"zone_leave",
	"gathering",
]

const _POSITIONED_TYPES := ["footstep", "zone_enter", "zone_leave"]

@export var receiver_path: NodePath

var _receiver: LumurEventReceiver
## app_id -> { allowed: PackedStringArray, bindings: Dictionary, delivered: Array, is_host: bool }
var _apps: Dictionary = {}
var refused: Array = []
var published: Array = []
var _seq: int = 0


func _ready() -> void:
	if receiver_path != NodePath(""):
		_receiver = get_node_or_null(receiver_path) as LumurEventReceiver
	if _receiver == null:
		_receiver = get_node_or_null("EventReceiver") as LumurEventReceiver
	bind_receiver(_receiver)


func bind_receiver(receiver: LumurEventReceiver) -> void:
	if _receiver != null and _receiver.raw_event.is_connected(_on_raw_event):
		_receiver.raw_event.disconnect(_on_raw_event)
	_receiver = receiver
	if _receiver != null and not _receiver.raw_event.is_connected(_on_raw_event):
		_receiver.raw_event.connect(_on_raw_event)


func register_app(manifest: LumurAppManifest, fit_result: Dictionary = {}) -> Dictionary:
	## Register from a validated manifest. Returns the session dictionary.
	if manifest == null:
		push_error("LumurAppInputBus: manifest is null")
		return {}
	var app_id := manifest.app_id()
	var allowed := manifest.inputs()
	var bindings: Dictionary = fit_result.get("bindings", {})
	var session := {
		"app_id": app_id,
		"allowed": allowed,
		"bindings": bindings,
		"delivered": [],
		"is_host": false,
	}
	_apps[app_id] = session
	return session


func register_app_document(doc: Dictionary, fit_result: Dictionary = {}) -> Dictionary:
	var m := LumurAppManifest.new()
	var err := m.load_document(doc)
	if err != OK:
		push_error("LumurAppInputBus: invalid manifest document")
		return {}
	return register_app(m, fit_result)


func register_host(host_id: String, allowed: PackedStringArray) -> Dictionary:
	## Privileged launcher / host path — explicit allowlist, not a silent firehose.
	for t in allowed:
		if not KNOWN_INPUTS.has(str(t)):
			push_error("LumurAppInputBus: unknown host input type %s" % t)
			return {}
	var session := {
		"app_id": host_id,
		"allowed": allowed,
		"bindings": {},
		"delivered": [],
		"is_host": true,
	}
	_apps[host_id] = session
	return session


func unregister(app_id: String) -> void:
	_apps.erase(app_id)


func subscribe(app_id: String, event_type: String) -> bool:
	## Refuse + log when the type is not in the app's manifest allowlist.
	if not _apps.has(app_id):
		_refuse(app_id, event_type, "unknown_app")
		return false
	var session: Dictionary = _apps[app_id]
	var allowed: PackedStringArray = session.get("allowed", PackedStringArray())
	if not allowed.has(event_type):
		_refuse(app_id, event_type, "undeclared_input")
		return false
	return true


func allows(app_id: String, event_type: String) -> bool:
	if not _apps.has(app_id):
		return false
	var allowed: PackedStringArray = _apps[app_id].get("allowed", PackedStringArray())
	return allowed.has(event_type)


func publish(event: Dictionary) -> Dictionary:
	## Fan-out one event. Returns {app_id: delivered_event} for recipients.
	var payload := _normalize(event)
	var ev_type := str(payload.get("type", ""))
	_seq += 1
	var envelope := payload.duplicate(true)
	envelope["_bus_seq"] = _seq
	published.append(envelope.duplicate(true))

	var delivered := {}
	for app_id in _apps.keys():
		var session: Dictionary = _apps[app_id]
		var allowed: PackedStringArray = session.get("allowed", PackedStringArray())
		if not allowed.has(ev_type):
			continue
		var fitted := _fit_event_for_app(envelope, session)
		fitted["app_id"] = str(app_id)
		session["delivered"].append(fitted.duplicate(true))
		delivered[app_id] = fitted
		self.app_event.emit(str(app_id), fitted)
	return delivered


func inject(event: Dictionary) -> Dictionary:
	## Test helper: feed an event without UDP.
	return publish(event)


func inject_event_json(text: String) -> Dictionary:
	var parsed: Variant = JSON.parse_string(text)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	var doc: Dictionary = parsed
	if str(doc.get("schema", "")) == "lumur.event" and doc.has("event"):
		return inject(doc["event"])
	return inject(doc)


func publish_batch(events: Array) -> Dictionary:
	var out := {}
	for app_id in _apps.keys():
		out[app_id] = []
	for ev in events:
		if typeof(ev) != TYPE_DICTIONARY:
			continue
		var batch := publish(ev)
		for app_id in batch.keys():
			if not out.has(app_id):
				out[app_id] = []
			out[app_id].append(batch[app_id])
	return out


func clear_streams() -> void:
	published.clear()
	_seq = 0
	for app_id in _apps.keys():
		_apps[app_id]["delivered"] = []


func streams() -> Dictionary:
	var out := {}
	for app_id in _apps.keys():
		out[app_id] = _apps[app_id].get("delivered", []).duplicate(true)
	return out


func replay(events: Array) -> Dictionary:
	clear_streams()
	return publish_batch(events)


func stream_for(app_id: String) -> Array:
	if not _apps.has(app_id):
		return []
	return _apps[app_id].get("delivered", []).duplicate(true)


func refused_log() -> Array:
	return refused.duplicate(true)


func _on_raw_event(event: Dictionary) -> void:
	publish(event)


func _refuse(app_id: String, event_type: String, reason: String) -> void:
	var entry := {
		"app_id": app_id,
		"event_type": event_type,
		"reason": reason,
	}
	refused.append(entry)
	push_warning(
		"LumurAppInputBus: refused subscription app=%s type=%s reason=%s"
		% [app_id, event_type, reason]
	)
	subscription_refused.emit(app_id, event_type, reason)


func _normalize(event: Dictionary) -> Dictionary:
	if str(event.get("schema", "")) == "lumur.event" and event.has("event"):
		var inner = event["event"]
		if typeof(inner) == TYPE_DICTIONARY:
			return (inner as Dictionary).duplicate(true)
	return event.duplicate(true)


func _fit_event_for_app(event: Dictionary, session: Dictionary) -> Dictionary:
	var out := event.duplicate(true)
	var floor := _floor_binding(session.get("bindings", {}))
	if not floor.is_empty() and floor.get("surface_id", null) != null:
		out["surface_key"] = str(floor.get("key", ""))
		out["surface_id"] = int(floor.get("surface_id", -1))
		var ev_type := str(out.get("type", ""))
		if _POSITIONED_TYPES.has(ev_type):
			var pf = out.get("position_floor", null)
			if typeof(pf) == TYPE_ARRAY and pf.size() >= 2:
				out["position_surface"] = [float(pf[0]), float(pf[1])]
	return out


func _floor_binding(bindings: Dictionary) -> Dictionary:
	if bindings.has("floor") and typeof(bindings["floor"]) == TYPE_DICTIONARY:
		return bindings["floor"]
	for key in bindings.keys():
		var b = bindings[key]
		if typeof(b) != TYPE_DICTIONARY:
			continue
		var role := str(b.get("role_requested", ""))
		var roles = b.get("roles", [])
		if role == "floor" or (typeof(roles) == TYPE_ARRAY and roles.has("floor")):
			return b
	return {}
