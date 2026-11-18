class_name LumurAppGeneration
extends RefCounted

## App-side SurfaceGenerator gate (PRD-003 REQ-003-014).
## Requests apply only to surfaces the app owns or overlays. Core stays free
## of Synesyn — providers are injected (null / package / companion bridge).

signal generation_finished(app_id: String, surface_key: String, ok: bool, meta: Dictionary)

var lifecycle: LumurAppLifecycle
var generator: LumurSurfaceGenerator
var history: Array = []


func setup(life: LumurAppLifecycle, gen: LumurSurfaceGenerator = null) -> void:
	lifecycle = life
	generator = gen if gen != null else LumurSurfaceGenerator.new()
	generator.configure_null()


func configure_package(paint: LumurPaintMode) -> void:
	if generator == null:
		generator = LumurSurfaceGenerator.new()
	generator.configure_package(paint)


func request(app_id: String, surface_key: String) -> Dictionary:
	## Returns a result dictionary; ``ok`` false when denied or provider skipped.
	if lifecycle == null or not lifecycle.apps.has(app_id):
		return _deny(app_id, surface_key, "unknown_app")
	var record: Dictionary = lifecycle.apps[app_id]
	var manifest: LumurAppManifest = record.get("manifest")
	if manifest == null or not bool(manifest.document.get("generation", false)):
		return _deny(app_id, surface_key, "generation_not_declared")
	if str(record.get("state", "")) != LumurAppLifecycle.STATE_RUNNING:
		return _deny(app_id, surface_key, "not_running")
	var fit: Dictionary = record.get("fit", {})
	var bindings: Dictionary = fit.get("bindings", {})
	if not bindings.has(surface_key):
		return _deny(app_id, surface_key, "unknown_surface_key")
	var sid = bindings[surface_key].get("surface_id", null)
	if sid == null:
		return _deny(app_id, surface_key, "surface_unbound")
	if lifecycle.compositor == null or not lifecycle.compositor.app_controls_surface(
		app_id, int(sid)
	):
		return _deny(app_id, surface_key, "surface_not_owned", int(sid))

	if generator == null:
		generator = LumurSurfaceGenerator.new()
		generator.configure_null()
	var done := {"ok": false, "meta": {}}
	var handler := func(key: Variant, ok: bool, meta: Dictionary) -> void:
		done["ok"] = ok
		done["meta"] = meta
		generation_finished.emit(app_id, str(key), ok, meta)
	if not generator.generation_finished.is_connected(handler):
		generator.generation_finished.connect(handler, CONNECT_ONE_SHOT)
	generator.request_surface(surface_key)
	var entry := {
		"app_id": app_id,
		"surface_key": surface_key,
		"surface_id": int(sid),
		"ok": bool(done.get("ok", false)),
		"meta": done.get("meta", {}),
		"denied_reason": null,
	}
	history.append(entry)
	return entry


func _deny(app_id: String, surface_key: String, reason: String, surface_id: int = -1) -> Dictionary:
	var entry := {
		"app_id": app_id,
		"surface_key": surface_key,
		"surface_id": surface_id if surface_id >= 0 else null,
		"ok": false,
		"meta": {},
		"denied_reason": reason,
	}
	history.append(entry)
	push_warning("LumurAppGeneration: denied %s/%s (%s)" % [app_id, surface_key, reason])
	generation_finished.emit(app_id, surface_key, false, {"denied_reason": reason})
	return entry
