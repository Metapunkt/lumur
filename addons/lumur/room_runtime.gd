class_name LumurRoomRuntime
extends Node

## Thin room-as-OS facade: load a scanned room's Godot assets and expose
## surfaces by id or role. Owns the projector paint output when a
## ``LumurPaintMode`` child (or assigned node) is present.

@export var godot_assets_path: String = ""
@export var paint_path: NodePath

var package: LumurRoomPackage
var paint: LumurPaintMode


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


func list_roles() -> PackedStringArray:
	var out := PackedStringArray()
	if package == null:
		return out
	var index: Dictionary = package.manifest.get("role_index", {})
	for k in index.keys():
		out.append(str(k))
	return out
