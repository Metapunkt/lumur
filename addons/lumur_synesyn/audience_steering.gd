class_name LumurAudienceSteering
extends RefCounted

## Opt-in audience steering (PRD-002 slice 4 / REQ-002-011).
##
## Enabled only when the scenario declares ``lumur_audience`` (or the free-text
## ``lumur_audience_text`` fallback). Absent that section, events are forwarded
## as ambience only and never advance story / director state.

signal steered(action: Dictionary)
signal rejected(info: Dictionary)
signal ambience(event: Dictionary)

var enabled: bool = false
var min_dwell_s: float = 1.5
var debounce_s: float = 0.8
var zone_actions: Dictionary = {}  ## zone_id → {action, option_index, ...}
var gathering_action: String = "advance_beat"
var intensity_parameter: String = "intensity"
var presence_intensity_scale: float = 0.25

var _dwell: Dictionary = {}  ## "pid|zone" → {enter_t, fired}
var _last_fire_t: Dictionary = {}
var _last_gathering_fire_t: float = -1.0e9
var _intensity: float = 0.0
var host: Object = null  ## LumurStoryStageHost


func configure_from_scenario(scenario: Dictionary) -> void:
	var section: Variant = null
	if scenario.has("lumur_audience") and typeof(scenario["lumur_audience"]) == TYPE_DICTIONARY:
		section = scenario["lumur_audience"]
	elif scenario.has("lumur_audience_text"):
		section = {"enabled": "true"}
	if section == null:
		enabled = false
		return
	var s: Dictionary = section
	var en := str(s.get("enabled", "true")).to_lower()
	enabled = en not in ["0", "false", "no", "off"]
	min_dwell_s = float(s.get("min_dwell_s", s.get("dwell_s", 1.5)))
	debounce_s = float(s.get("debounce_s", s.get("debounce", 0.8)))
	gathering_action = str(s.get("gathering_action", "advance_beat"))
	intensity_parameter = str(s.get("intensity_parameter", "intensity"))
	presence_intensity_scale = float(s.get("presence_intensity_scale", 0.25))
	zone_actions.clear()
	var actions: Variant = s.get("zone_actions", s.get("actions", {}))
	if typeof(actions) == TYPE_DICTIONARY:
		for zid in actions.keys():
			zone_actions[str(zid)] = actions[zid]


func process_event(event: Dictionary) -> Array:
	## Always emit ambience; steer only when enabled.
	ambience.emit(event)
	if host != null and host.has_method("forward_ambience_event"):
		host.forward_ambience_event(event)
	if not enabled:
		return []
	var applied: Array = []
	var ev_type := str(event.get("type", ""))
	var ts := float(event.get("timestamp", 0.0))
	match ev_type:
		"presence":
			var count := int(event.get("count", 0))
			_intensity = clampf(float(count) * presence_intensity_scale, 0.0, 1.0)
			var action := {
				"kind": "set_parameter",
				"parameter": intensity_parameter,
				"value": _intensity,
				"timestamp": ts,
			}
			applied.append(action)
			steered.emit(action)
			if host != null and host.has_method("apply_audience_action"):
				host.apply_audience_action(action)
		"zone_enter":
			var pid := int(event.get("person_id", -1))
			var zid := str(event.get("zone_id", ""))
			_dwell["%d|%s" % [pid, zid]] = {"enter_t": ts, "fired": false, "zone_id": zid, "person_id": pid}
		"zone_leave":
			var pid2 := int(event.get("person_id", -1))
			var zid2 := str(event.get("zone_id", ""))
			var key := "%d|%s" % [pid2, zid2]
			if _dwell.has(key):
				var watch: Dictionary = _dwell[key]
				var dwell := ts - float(watch.get("enter_t", ts))
				if not bool(watch.get("fired", false)) and dwell < min_dwell_s:
					rejected.emit({"reason": "dwell_too_short", "dwell_s": dwell, "event": event})
				_dwell.erase(key)
		"gathering":
			if (ts - _last_gathering_fire_t) < debounce_s:
				rejected.emit({"reason": "gathering_debounce", "event": event})
			else:
				var gaction := {"kind": gathering_action, "timestamp": ts, "source_event": event}
				_last_gathering_fire_t = ts
				applied.append(gaction)
				steered.emit(gaction)
				if host != null and host.has_method("apply_audience_action"):
					host.apply_audience_action(gaction)
		"footstep":
			pass
	return applied


func tick(timestamp: float) -> Array:
	if not enabled:
		return []
	var applied: Array = []
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
			rejected.emit({"reason": "zone_debounce", "zone_id": zid})
			watch["fired"] = true
			continue
		if not zone_actions.has(zid):
			continue
		var spec: Variant = zone_actions[zid]
		var action := _action_from_spec(spec, zid, timestamp, watch)
		watch["fired"] = true
		_last_fire_t[zid] = timestamp
		applied.append(action)
		steered.emit(action)
		if host != null and host.has_method("apply_audience_action"):
			host.apply_audience_action(action)
	return applied


func _action_from_spec(spec: Variant, zid: String, ts: float, watch: Dictionary) -> Dictionary:
	var action_kind := "choose_option"
	var option_index = null
	var option_label = null
	if typeof(spec) == TYPE_STRING:
		var s := str(spec)
		if s.begins_with("option:") or s.begins_with("choose:"):
			var rest := s.split(":")[1]
			if rest.is_valid_int():
				option_index = int(rest)
			else:
				option_label = rest
		elif s in ["advance", "advance_beat", "beat"]:
			action_kind = "advance_beat"
		else:
			action_kind = "set_parameter"
			option_label = s
	elif typeof(spec) == TYPE_DICTIONARY:
		var d: Dictionary = spec
		action_kind = str(d.get("action", "choose_option"))
		if d.has("option_index"):
			option_index = int(d["option_index"])
		if d.has("option_label"):
			option_label = str(d["option_label"])
	return {
		"kind": action_kind,
		"timestamp": ts,
		"option_index": option_index,
		"option_label": option_label,
		"zone_id": zid,
		"person_id": watch.get("person_id", -1),
	}
