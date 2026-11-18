@tool
extends EditorPlugin

## Optional Synesyn bridge (ADR 0015). Registers Hub surface-generator helpers.
## Does not hard-require synesyn_core at editor load — enable synesyn_core when
## using live Hub client scripts from Godot; Python companion covers Hub HTTP.


func _enter_tree() -> void:
	add_custom_type(
		"LumurSynesynHubSurfaceGenerator",
		"RefCounted",
		preload("res://addons/lumur_synesyn/hub_surface_generator.gd"),
		null
	)


func _exit_tree() -> void:
	remove_custom_type("LumurSynesynHubSurfaceGenerator")
