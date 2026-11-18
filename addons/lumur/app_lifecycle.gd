class_name LumurAppLifecycle
extends RefCounted

## Install / launch / pause / resume / switch / stop (PRD-003 slice 3).
## Paused apps receive no input-bus events.

const STATE_INSTALLED := "installed"
const STATE_RUNNING := "running"
const STATE_PAUSED := "paused"
const STATE_STOPPED := "stopped"

var package: LumurRoomPackage
var compositor: LumurCompositor
var input_bus: LumurAppInputBus
## app_id -> {app_id, manifest, state, fit, path, last_error}
var apps: Dictionary = {}
var foreground_app_id: String = ""
var history: Array = []
var last_error: String = ""


func setup(p_package: LumurRoomPackage, bus: LumurAppInputBus, comp: LumurCompositor = null) -> void:
	package = p_package
	input_bus = bus
	compositor = comp if comp != null else LumurCompositor.new()
	if package != null:
		compositor.confidence_threshold = package.confidence_threshold_default()


func install_document(doc: Dictionary, path: String = "") -> Dictionary:
	var manifest := LumurAppManifest.new()
	var err := manifest.load_document(doc)
	if err != OK:
		last_error = "invalid manifest"
		return {}
	var app_id := manifest.app_id()
	var record := {
		"app_id": app_id,
		"manifest": manifest,
		"document": doc,
		"state": STATE_INSTALLED,
		"fit": {},
		"path": path,
		"last_error": "",
	}
	apps[app_id] = record
	_log("install", app_id)
	return record


func install_file(path: String) -> Dictionary:
	var manifest := LumurAppManifest.new()
	var err := manifest.load_file(path)
	if err != OK:
		last_error = manifest.last_error
		return {}
	return install_document(manifest.document, path)


func states() -> Dictionary:
	var out := {}
	for app_id in apps.keys():
		out[app_id] = apps[app_id].get("state", "")
	return out


func launch(app_id: String, make_foreground: bool = true) -> Dictionary:
	if not apps.has(app_id):
		last_error = "unknown_app"
		return {}
	var record: Dictionary = apps[app_id]
	if str(record.get("state", "")) == STATE_RUNNING:
		return record
	if str(record.get("state", "")) == STATE_PAUSED:
		return resume(app_id, make_foreground)

	var manifest: LumurAppManifest = record["manifest"]
	var shares := PackedStringArray()
	for s in manifest.document.get("shares", []):
		shares.append(str(s))
	var fitter := LumurAppFit.new()
	var owned: Array = compositor.exclusive_owned_ids()
	var fit: Dictionary = fitter.fit(manifest, package, owned, shares)
	if not bool(fit.get("ok", false)):
		record["last_error"] = fitter.last_error
		last_error = fitter.last_error
		_log("launch_failed", app_id, {"reason": "unmet_surface"})
		return {}

	var claims: Array = compositor.claim_from_fit(app_id, fit, shares, false)
	# claim_from_fit returns [] on exclusive conflict for base.
	if claims.is_empty():
		# Optional-only apps may have null bindings — still "running" degraded.
		var bindings: Dictionary = fit.get("bindings", {})
		var any_sid := false
		for k in bindings.keys():
			if bindings[k].get("surface_id", null) != null:
				any_sid = true
				break
		if any_sid:
			last_error = "exclusive_conflict"
			record["last_error"] = last_error
			_log("launch_failed", app_id, {"reason": "exclusive_conflict"})
			return {}

	record["fit"] = fit
	record["state"] = STATE_RUNNING
	record["last_error"] = ""
	if input_bus != null:
		input_bus.register_app(manifest, fit)
		input_bus.set_paused(app_id, false)
		for ev in manifest.inputs():
			input_bus.subscribe(app_id, str(ev))

	if make_foreground:
		var prev := foreground_app_id
		foreground_app_id = app_id
		compositor.switch_handoff(
			prev if not prev.is_empty() else null,
			app_id,
			"launch"
		)
	_log("launch", app_id)
	return record


func pause(app_id: String) -> Dictionary:
	if not apps.has(app_id):
		return {}
	var record: Dictionary = apps[app_id]
	if str(record.get("state", "")) != STATE_RUNNING:
		last_error = "invalid_state"
		return {}
	compositor.pause_handoff(app_id)
	if input_bus != null:
		input_bus.set_paused(app_id, true)
	record["state"] = STATE_PAUSED
	if foreground_app_id == app_id:
		foreground_app_id = ""
	_log("pause", app_id)
	return record


func resume(app_id: String, make_foreground: bool = true) -> Dictionary:
	if not apps.has(app_id):
		return {}
	var record: Dictionary = apps[app_id]
	if str(record.get("state", "")) == STATE_RUNNING:
		return record
	if str(record.get("state", "")) != STATE_PAUSED:
		return launch(app_id, make_foreground)

	var manifest: LumurAppManifest = record["manifest"]
	var shares := PackedStringArray()
	for s in manifest.document.get("shares", []):
		shares.append(str(s))
	var fitter := LumurAppFit.new()
	var owned: Array = compositor.exclusive_owned_ids()
	var fit: Dictionary = fitter.fit(manifest, package, owned, shares)
	if not bool(fit.get("ok", false)):
		last_error = fitter.last_error
		return {}
	compositor.claim_from_fit(app_id, fit, shares, false)
	record["fit"] = fit
	record["state"] = STATE_RUNNING
	if input_bus != null:
		if not input_bus.has_app(app_id):
			input_bus.register_app(manifest, fit)
		else:
			input_bus.set_bindings(app_id, fit.get("bindings", {}))
		input_bus.set_paused(app_id, false)
	if make_foreground:
		var prev := foreground_app_id
		foreground_app_id = app_id
		compositor.switch_handoff(
			prev if not prev.is_empty() else null,
			app_id,
			"resume"
		)
	_log("resume", app_id)
	return record


func stop(app_id: String) -> Dictionary:
	if not apps.has(app_id):
		return {}
	var record: Dictionary = apps[app_id]
	var st := str(record.get("state", ""))
	if st == STATE_RUNNING or st == STATE_PAUSED:
		compositor.release(app_id, "stop")
	if input_bus != null:
		input_bus.unregister(app_id)
	record["state"] = STATE_STOPPED
	record["fit"] = {}
	if foreground_app_id == app_id:
		foreground_app_id = ""
	_log("stop", app_id)
	return record


func switch_to(app_id: String) -> Dictionary:
	if foreground_app_id == app_id and apps.has(app_id):
		var cur: Dictionary = apps[app_id]
		if str(cur.get("state", "")) == STATE_RUNNING:
			return cur
	if not foreground_app_id.is_empty() and apps.has(foreground_app_id):
		var fg: Dictionary = apps[foreground_app_id]
		if str(fg.get("state", "")) == STATE_RUNNING:
			pause(foreground_app_id)
	if not apps.has(app_id):
		last_error = "unknown_app"
		return {}
	var record: Dictionary = apps[app_id]
	var st := str(record.get("state", ""))
	if st == STATE_PAUSED:
		return resume(app_id, true)
	if st == STATE_RUNNING:
		foreground_app_id = app_id
		return record
	return launch(app_id, true)


func _log(action: String, app_id: String, extra: Dictionary = {}) -> void:
	var entry := {"action": action, "app_id": app_id}
	for k in extra.keys():
		entry[k] = extra[k]
	history.append(entry)
