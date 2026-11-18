extends Node

## Bundled paint-the-room app boot (PRD-003 REQ-003-015 / 014).

const APP_ID := "lumur.paint"
const MANIFEST_PATH := "res://apps/paint/lumur.app.json"


func _ready() -> void:
	var runtime := get_parent() as LumurRoomRuntime
	if runtime == null:
		push_error("paint_app: parent is not LumurRoomRuntime")
		return
	var assets := OS.get_environment("LUMUR_GODOT_ASSETS")
	if assets.is_empty():
		assets = "/tmp/sim-room/godot"
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(assets)) \
			and not DirAccess.dir_exists_absolute(assets):
		push_warning("paint_app: no assets at %s — set LUMUR_GODOT_ASSETS" % assets)
		return
	var err := runtime.load_room(assets)
	if err != OK:
		push_error("paint_app: failed to load %s" % assets)
		return

	runtime.install_app(ProjectSettings.globalize_path(MANIFEST_PATH))
	var launched := runtime.launch_app(APP_ID)
	if launched.is_empty():
		push_warning("paint_app: launch failed — %s" % runtime.lifecycle.last_error)
		return

	runtime.paint_surface("floor", Color(0.85, 0.15, 0.12))
	if runtime.surface("wall_1") != null:
		runtime.paint_surface("wall_1", Color(0.12, 0.55, 0.85))
	if runtime.surface("wall_2") != null:
		runtime.pulse_surface("wall_2", Color(0.9, 0.75, 0.2), 0.7)

	# Optional generation: package provider applies companion textures; null
	# finishes without blocking. Authored paint remains on failure.
	var gen := LumurSurfaceGenerator.new()
	gen.configure_package(runtime.paint)
	if runtime.compositor != null and runtime.compositor.app_controls_surface(
		APP_ID, runtime.floor_plane_id()
	):
		gen.request_surface("floor")
