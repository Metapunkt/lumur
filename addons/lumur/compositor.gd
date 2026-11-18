class_name LumurCompositor
extends RefCounted

## Surface ownership + paint-mode compositing (PRD-003 slice 3 / ADR 0018).
## Exclusive ownership by default; overlays when the app declares ``shares``.
## Confidence masking stays with ``LumurPaintMode`` — apps cannot invent coverage.

signal ownership_changed()
signal transitioned(record: Dictionary)

var confidence_threshold: float = 0.05
## surface_id -> {base_app_id, base_key, overlays: [{app_id, surface_key}]}
var ownership: Dictionary = {}
## app_id -> {surface_id: {app_id, surface_id, surface_key, layer}}
var claims_by_app: Dictionary = {}
var share_keys: Dictionary = {}  ## app_id -> PackedStringArray
var transitions: Array = []
var last_transition: Dictionary = {}


func exclusive_owned_ids() -> Array:
	var out: Array = []
	for sid in ownership.keys():
		var entry: Dictionary = ownership[sid]
		if entry.get("base_app_id", null) != null:
			out.append(int(sid))
	return out


func ownership_table() -> Dictionary:
	var out := {}
	for sid in ownership.keys():
		out[sid] = (ownership[sid] as Dictionary).duplicate(true)
	return out


func set_share_keys(app_id: String, keys: PackedStringArray) -> void:
	share_keys[app_id] = keys


func claim_from_fit(
	app_id: String,
	fit_result: Dictionary,
	shares: PackedStringArray = PackedStringArray(),
	as_overlay: bool = false
) -> Array:
	set_share_keys(app_id, shares)
	var claimed: Array = []
	var bindings: Dictionary = fit_result.get("bindings", {})
	for key in bindings.keys():
		var binding = bindings[key]
		if typeof(binding) != TYPE_DICTIONARY:
			continue
		var sid = binding.get("surface_id", null)
		if sid == null:
			continue
		var want_overlay := as_overlay or shares.has(str(key))
		var claim: Dictionary
		if want_overlay:
			claim = _claim_overlay(app_id, int(sid), str(key))
		else:
			claim = _claim_base(app_id, int(sid), str(key))
		if claim.is_empty():
			return []
		claimed.append(claim)
	ownership_changed.emit()
	return claimed


func _claim_base(app_id: String, surface_id: int, key: String) -> Dictionary:
	var entry: Dictionary = ownership.get(surface_id, {
		"surface_id": surface_id,
		"base_app_id": null,
		"base_key": null,
		"overlays": [],
	})
	var existing = entry.get("base_app_id", null)
	if existing != null and str(existing) != app_id:
		push_error(
			"LumurCompositor: surface %d owned by %s; %s cannot take base"
			% [surface_id, existing, app_id]
		)
		return {}
	entry["base_app_id"] = app_id
	entry["base_key"] = key
	ownership[surface_id] = entry
	var claim := {
		"app_id": app_id,
		"surface_id": surface_id,
		"surface_key": key,
		"layer": "base",
	}
	if not claims_by_app.has(app_id):
		claims_by_app[app_id] = {}
	claims_by_app[app_id][surface_id] = claim
	return claim


func _claim_overlay(app_id: String, surface_id: int, key: String) -> Dictionary:
	var shares: PackedStringArray = share_keys.get(app_id, PackedStringArray())
	if not shares.has(key):
		push_error("LumurCompositor: overlay requires shares declaration for %s" % key)
		return {}
	var entry: Dictionary = ownership.get(surface_id, {
		"surface_id": surface_id,
		"base_app_id": null,
		"base_key": null,
		"overlays": [],
	})
	var overlays: Array = entry.get("overlays", [])
	var found := false
	for o in overlays:
		if str(o.get("app_id", "")) == app_id and str(o.get("surface_key", "")) == key:
			found = true
			break
	if not found:
		overlays.append({"app_id": app_id, "surface_key": key})
	entry["overlays"] = overlays
	ownership[surface_id] = entry
	var claim := {
		"app_id": app_id,
		"surface_id": surface_id,
		"surface_key": key,
		"layer": "overlay",
	}
	if not claims_by_app.has(app_id):
		claims_by_app[app_id] = {}
	claims_by_app[app_id][surface_id] = claim
	return claim


func release(app_id: String, reason: String = "stop") -> Dictionary:
	var claims: Dictionary = claims_by_app.get(app_id, {})
	var surface_ids: Array = claims.keys()
	surface_ids.sort()
	for sid_v in surface_ids:
		var sid := int(sid_v)
		if not ownership.has(sid):
			continue
		var entry: Dictionary = ownership[sid]
		if str(entry.get("base_app_id", "")) == app_id:
			entry["base_app_id"] = null
			entry["base_key"] = null
		var overlays: Array = []
		for o in entry.get("overlays", []):
			if str(o.get("app_id", "")) != app_id:
				overlays.append(o)
		entry["overlays"] = overlays
		if entry.get("base_app_id", null) == null and overlays.is_empty():
			ownership.erase(sid)
		else:
			ownership[sid] = entry
	claims_by_app.erase(app_id)
	share_keys.erase(app_id)
	var rec := {
		"kind": "cut",
		"from_app_id": app_id,
		"to_app_id": null,
		"surface_ids": surface_ids,
		"reason": reason,
	}
	transitions.append(rec)
	last_transition = rec
	transitioned.emit(rec)
	ownership_changed.emit()
	return rec


func pause_handoff(app_id: String) -> Dictionary:
	return release(app_id, "pause")


func switch_handoff(from_app_id, to_app_id, reason: String = "switch") -> Dictionary:
	var surfaces: Array = []
	if from_app_id != null and claims_by_app.has(str(from_app_id)):
		for sid in claims_by_app[str(from_app_id)].keys():
			surfaces.append(int(sid))
	if to_app_id != null and claims_by_app.has(str(to_app_id)):
		for sid in claims_by_app[str(to_app_id)].keys():
			if not surfaces.has(int(sid)):
				surfaces.append(int(sid))
	surfaces.sort()
	var rec := {
		"kind": "cut",
		"from_app_id": from_app_id,
		"to_app_id": to_app_id,
		"surface_ids": surfaces,
		"reason": reason,
	}
	transitions.append(rec)
	last_transition = rec
	transitioned.emit(rec)
	return rec


func clear_owned_paint(paint: LumurPaintMode, app_id: String) -> void:
	## Cut handoff: clear colours on surfaces this app owned (paint-mode path).
	if paint == null or not claims_by_app.has(app_id):
		return
	for sid in claims_by_app[app_id].keys():
		paint.set_surface_color(int(sid), paint.clear_color)
