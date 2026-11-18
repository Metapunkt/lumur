class_name LumurRoomRuntime
extends Node

## Thin room-as-OS facade: load a scanned room's Godot assets and expose
## surfaces by id or role. Owns the projector paint output when a
## ``LumurPaintMode`` child (or assigned node) is present.
##
## PRD-003 slice 1 also exposes app-manifest load + room-fit against the
## current package (ADR 0017 / 0018). Apps should ask for surfaces through
## this facade rather than hard-coding projector pixels.

@export var godot_assets_path: String = ""
@export var paint_path: NodePath

var package: LumurRoomPackage
var paint: LumurPaintMode
var app_manifest: LumurAppManifest
var last_fit: Dictionary = {}


func _ready() -> void:
	if paint_path != NodePath(""):
		paint = get_node_or_null(paint_path) as LumurPaintMode
	if paint == null:
		paint = get_node_or_null("Paint") as LumurPaintMode
	if not godot_assets_path.is_empty():
		load_room(godot_assets_path)


func load_room(path: String) -> Error:
	package = LumurRoomPackage.new()
	var err := package.load_godot_dir(path)
	if err != OK:
		return err
	if paint != null:
		paint.bind_package(package)
	return OK


func surface(key: Variant) -> LumurSurfaceTarget:
	if paint == null:
		return null
	return paint.get_target(key)


func paint_surface(key: Variant, color: Color) -> void:
	if paint != null:
		paint.set_surface_color(key, color)


func pulse_surface(key: Variant, color: Color, hz: float = 1.0) -> void:
	if paint != null:
		paint.set_surface_pulse(key, color, hz)


func texture_surface(key: Variant, tex: Texture2D, tint: Color = Color.WHITE) -> void:
	if paint != null:
		paint.set_surface_texture(key, tex, tint)


func apply_generated_textures() -> int:
	## Apply companion-generated textures from paint_manifest.generated_textures.
	## Safe to call when none exist (returns 0). Never talks to ComfyUI.
	if paint == null:
		return 0
	return paint.apply_generated_from_package()


func list_roles() -> PackedStringArray:
	var out := PackedStringArray()
	if package == null:
		return out
	var index: Dictionary = package.manifest.get("role_index", {})
	for k in index.keys():
		out.append(str(k))
	return out


func list_surfaces() -> Array:
	if package == null:
		return []
	return package.list_surfaces()


func floor_plane_id() -> int:
	if package == null:
		return -1
	var fid = package.manifest.get("floor_plane_id", null)
	if fid == null:
		return -1
	return int(fid)


func confidence_threshold() -> float:
	if package == null:
		return 0.05
	return package.confidence_threshold_default()


func generated_texture_handles() -> Dictionary:
	if package == null:
		return {}
	return package.manifest.get("generated_textures", {})


func load_app_manifest(path: String) -> Error:
	app_manifest = LumurAppManifest.new()
	var err := app_manifest.load_file(path)
	if err != OK:
		push_error("LumurRoomRuntime: %s" % app_manifest.last_error)
	return err


func fit_app(manifest: LumurAppManifest = null, exclusive_owned: Array = []) -> Dictionary:
	## Bind manifest surface requests to the loaded room package.
	var m := manifest if manifest != null else app_manifest
	if m == null:
		push_error("LumurRoomRuntime: no app manifest loaded")
		last_fit = {"ok": false, "bindings": {}, "unmet": []}
		return last_fit
	if package == null:
		push_error("LumurRoomRuntime: no room package loaded")
		last_fit = {"ok": false, "bindings": {}, "unmet": []}
		return last_fit
	var fitter := LumurAppFit.new()
	last_fit = fitter.fit(m, package, exclusive_owned)
	return last_fit


func bound_surface_id(request_key: String) -> int:
	## After ``fit_app``, resolve a manifest key to a concrete surface id (-1 if none).
	var bindings: Dictionary = last_fit.get("bindings", {})
	if not bindings.has(request_key):
		return -1
	var entry = bindings[request_key]
	if typeof(entry) != TYPE_DICTIONARY:
		return -1
	var sid = entry.get("surface_id", null)
	if sid == null:
		return -1
	return int(sid)


func bind_event_receiver(receiver: LumurEventReceiver) -> void:
	## Convenience: apps can subscribe without knowing UDP details.
	if receiver == null:
		return
	if not receiver.footstep.is_connected(_on_runtime_footstep):
		receiver.footstep.connect(_on_runtime_footstep)


signal footstep(event: Dictionary)


func _on_runtime_footstep(event: Dictionary) -> void:
	footstep.emit(event)
