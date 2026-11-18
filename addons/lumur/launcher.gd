class_name LumurLauncher
extends RefCounted

## Headless launcher API (PRD-003 REQ-003-012): list installed apps and start one.
## Bridge-hosted apps are omitted from ``list_startable`` unless ``require_bridge``.

var lifecycle: LumurAppLifecycle
var require_bridge: bool = false


func _init(p_lifecycle: LumurAppLifecycle = null) -> void:
	lifecycle = p_lifecycle


func bind(p_lifecycle: LumurAppLifecycle) -> void:
	lifecycle = p_lifecycle


func list_installed() -> Array:
	var out: Array = []
	if lifecycle == null:
		return out
	for app_id in lifecycle.apps.keys():
		var rec: Dictionary = lifecycle.apps[app_id]
		var manifest: LumurAppManifest = rec.get("manifest")
		out.append({
			"app_id": app_id,
			"name": manifest.document.get("name", "") if manifest else "",
			"version": manifest.document.get("version", "") if manifest else "",
			"state": rec.get("state", ""),
			"bridge": manifest.document.get("bridge", null) if manifest else null,
		})
	return out


func list_startable() -> Array:
	var out: Array = []
	for entry in list_installed():
		var bridge = entry.get("bridge", null)
		if bridge != null and not require_bridge:
			continue
		out.append(entry)
	return out


func start(app_id: String, concurrent_overlay: bool = false) -> Dictionary:
	if lifecycle == null:
		return {}
	if not lifecycle.apps.has(app_id):
		return {}
	var rec: Dictionary = lifecycle.apps[app_id]
	var manifest: LumurAppManifest = rec.get("manifest")
	if not concurrent_overlay and manifest != null:
		concurrent_overlay = _is_pure_overlay(manifest.document)
	var st := str(rec.get("state", ""))
	if concurrent_overlay:
		if st == LumurAppLifecycle.STATE_PAUSED:
			return lifecycle.resume(app_id, false)
		if st == LumurAppLifecycle.STATE_RUNNING:
			return rec
		return lifecycle.launch(app_id, false)
	if not lifecycle.foreground_app_id.is_empty() and lifecycle.foreground_app_id != app_id:
		return lifecycle.switch_to(app_id)
	if st == LumurAppLifecycle.STATE_PAUSED:
		return lifecycle.resume(app_id)
	if st == LumurAppLifecycle.STATE_RUNNING:
		lifecycle.foreground_app_id = app_id
		return rec
	return lifecycle.launch(app_id)


func stop(app_id: String) -> Dictionary:
	if lifecycle == null:
		return {}
	return lifecycle.stop(app_id)


func _is_pure_overlay(doc: Dictionary) -> bool:
	var shares := {}
	for s in doc.get("shares", []):
		shares[str(s)] = true
	if shares.is_empty():
		return false
	var keys := {}
	for s in doc.get("surfaces", []):
		keys[str(s.get("key", ""))] = true
	if keys.is_empty():
		return false
	for k in keys.keys():
		if not shares.has(k):
			return false
	return true
