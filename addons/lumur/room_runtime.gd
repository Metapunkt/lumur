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


func bind_event_receiver(receiver: LumurEventReceiver) -> void:
	## Convenience: apps can subscribe without knowing UDP details.
	if receiver == null:
		return
	if not receiver.footstep.is_connected(_on_runtime_footstep):
		receiver.footstep.connect(_on_runtime_footstep)


signal footstep(event: Dictionary)


func _on_runtime_footstep(event: Dictionary) -> void:
	footstep.emit(event)
