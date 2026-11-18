@tool
extends EditorPlugin

## Registers Lumur custom types for the room runtime and paint mode.


func _enter_tree() -> void:
	add_custom_type(
		"LumurRoomRuntime",
		"Node",
		preload("res://addons/lumur/room_runtime.gd"),
		null
	)
	add_custom_type(
		"LumurPaintMode",
		"ColorRect",
		preload("res://addons/lumur/paint_mode.gd"),
		null
	)


func _exit_tree() -> void:
	remove_custom_type("LumurRoomRuntime")
	remove_custom_type("LumurPaintMode")
