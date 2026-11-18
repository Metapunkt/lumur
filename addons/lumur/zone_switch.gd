class_name LumurZoneAppSwitcher
extends RefCounted

## Optional zone→app switching (PRD-003 REQ-003-013).
## Host path on the input bus — not an ordinary app permission.

signal switched(record: Dictionary)
signal rejected_switch(info: Dictionary)

var lifecycle: LumurAppLifecycle
var zone_to_app: Dictionary = {}  ## zone_id -> app_id
var enabled: bool = false
var host_id: String = "lumur.launcher.zone_switch"
var gate: LumurDwellGate = LumurDwellGate.new()
var switches: Array = []
var rejected: Array = []


func configure(config: Dictionary) -> void:
	zone_to_app.clear()
	var mapping = config.get("zone_to_app", config.get("zones", {}))
	if typeof(mapping) == TYPE_DICTIONARY:
		for zid in mapping.keys():
			zone_to_app[str(zid)] = str(mapping[zid])
	gate.min_dwell_s = float(config.get("min_dwell_s", config.get("dwell_s", 1.5)))
	gate.debounce_s = float(config.get("debounce_s", config.get("debounce", 0.8)))
	var en := bool(config.get("enabled", true))
	enabled = en and not zone_to_app.is_empty()


func bind_lifecycle(p_lifecycle: LumurAppLifecycle) -> void:
	lifecycle = p_lifecycle


func attach_bus() -> void:
	if lifecycle == null or lifecycle.input_bus == null or not enabled:
		return
	var allowed := PackedStringArray(["zone_enter", "zone_leave"])
	lifecycle.input_bus.register_host(host_id, allowed)
	lifecycle.input_bus.subscribe(host_id, "zone_enter")
	lifecycle.input_bus.subscribe(host_id, "zone_leave")


func process_event(event: Dictionary, publish: bool = true) -> Array:
	if publish and lifecycle != null and lifecycle.input_bus != null:
		lifecycle.input_bus.publish(event)
	if not enabled:
		return []
	var fires: Array = gate.process_event(event)
	return _apply_fires(fires)


func tick(timestamp: float) -> Array:
	if not enabled:
		return []
	return _apply_fires(gate.tick(timestamp))


func _apply_fires(fires: Array) -> Array:
	var applied: Array = []
	for r in gate.rejected:
		if not rejected.has(r):
			rejected.append(r)
			rejected_switch.emit(r)
	for fire in fires:
		var zid := str(fire.get("zone_id", ""))
		if not zone_to_app.has(zid):
			continue
		var app_id := str(zone_to_app[zid])
		if lifecycle == null or not lifecycle.apps.has(app_id):
			var info := {"reason": "unknown_app", "app_id": app_id, "zone_id": zid}
			rejected.append(info)
			rejected_switch.emit(info)
			continue
		lifecycle.switch_to(app_id)
		var rec := {
			"action": "zone_switch",
			"app_id": app_id,
			"zone_id": zid,
			"person_id": int(fire.get("person_id", -1)),
			"dwell_s": float(fire.get("dwell_s", 0.0)),
			"timestamp": float(fire.get("timestamp", 0.0)),
		}
		switches.append(rec)
		applied.append(rec)
		switched.emit(rec)
	return applied
