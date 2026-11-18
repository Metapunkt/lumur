class_name LumurDwellGate
extends RefCounted

## Minimum dwell + debounce for zone actions (passers-by rejection).
## Same semantics as companion ``lumur.audience.dwell.DwellGate``.

var min_dwell_s: float = 1.5
var debounce_s: float = 0.8
var _dwell: Dictionary = {}  ## "pid|zone" -> {person_id, zone_id, enter_t, fired}
var _last_fire_t: Dictionary = {}
var rejected: Array = []


func reset() -> void:
	_dwell.clear()
	_last_fire_t.clear()
	rejected.clear()


func on_zone_enter(person_id: int, zone_id: String, timestamp: float) -> void:
	var key := "%d|%s" % [person_id, zone_id]
	_dwell[key] = {
		"person_id": person_id,
		"zone_id": zone_id,
		"enter_t": timestamp,
		"last_seen_t": timestamp,
		"fired": false,
	}


func on_zone_leave(person_id: int, zone_id: String, timestamp: float) -> void:
	var key := "%d|%s" % [person_id, zone_id]
	if not _dwell.has(key):
		return
	var watch: Dictionary = _dwell[key]
	_dwell.erase(key)
	if bool(watch.get("fired", false)):
		return
	var dwell := timestamp - float(watch.get("enter_t", timestamp))
	if dwell < min_dwell_s:
		rejected.append({
			"reason": "dwell_too_short",
			"dwell_s": dwell,
			"min_dwell_s": min_dwell_s,
			"person_id": person_id,
			"zone_id": zone_id,
			"timestamp": timestamp,
		})


func tick(timestamp: float) -> Array:
	var fired: Array = []
	for key in _dwell.keys():
		var watch: Dictionary = _dwell[key]
		if bool(watch.get("fired", false)):
			continue
		var dwell := timestamp - float(watch.get("enter_t", timestamp))
		if dwell < min_dwell_s:
			continue
		var zid := str(watch.get("zone_id", ""))
		var last := float(_last_fire_t.get(zid, -1.0e9))
		if (timestamp - last) < debounce_s:
			rejected.append({
				"reason": "zone_debounce",
				"zone_id": zid,
				"timestamp": timestamp,
			})
			watch["fired"] = true
			continue
		watch["fired"] = true
		_last_fire_t[zid] = timestamp
		fired.append({
			"type": "zone_dwell",
			"person_id": int(watch.get("person_id", -1)),
			"zone_id": zid,
			"dwell_s": dwell,
			"timestamp": timestamp,
		})
	return fired


func process_event(event: Dictionary) -> Array:
	var ev_type := str(event.get("type", ""))
	var ts := float(event.get("timestamp", 0.0))
	if ev_type == "zone_enter":
		on_zone_enter(int(event.get("person_id", -1)), str(event.get("zone_id", "")), ts)
	elif ev_type == "zone_leave":
		on_zone_leave(int(event.get("person_id", -1)), str(event.get("zone_id", "")), ts)
	return tick(ts)
