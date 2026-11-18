extends Node

## Interactive demo boot: load ``LUMUR_GODOT_ASSETS`` or a bundled fixture path.


func _ready() -> void:
	var runtime := get_parent() as LumurRoomRuntime
	if runtime == null:
		push_error("paint_demo_boot: parent is not LumurRoomRuntime")
		return
	var path := LumurDefaultAssets.resolve()
	if not DirAccess.dir_exists_absolute(ProjectSettings.globalize_path(path)) \
			and not DirAccess.dir_exists_absolute(path):
		push_warning("No paint assets at %s — set LUMUR_GODOT_ASSETS" % path)
		return
	var err := runtime.load_room(path)
	if err != OK:
		push_error("Failed to load room assets from %s" % path)
		return
	runtime.paint_surface("floor", Color(0.85, 0.15, 0.12))
	runtime.paint_surface("wall_1", Color(0.12, 0.55, 0.85))
	# Remaining surfaces: gentle pulse on wall_2 if present.
	if runtime.surface("wall_2") != null:
		runtime.pulse_surface("wall_2", Color(0.9, 0.75, 0.2), 0.7)
