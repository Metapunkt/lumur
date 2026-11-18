@tool
extends EditorPlugin

## Optional Synesyn bridge (ADR 0015). Hub generator helpers (slice 2) and
## Story Stage → surface mapping (slice 3). Does not hard-require synesyn_core
## or story_stage at editor load.


func _enter_tree() -> void:
	add_custom_type(
		"LumurSynesynHubSurfaceGenerator",
		"RefCounted",
		preload("res://addons/lumur_synesyn/hub_surface_generator.gd"),
		null
	)
	add_custom_type(
		"LumurStoryStageLayout",
		"RefCounted",
		preload("res://addons/lumur_synesyn/story_stage_layout.gd"),
		null
	)
	add_custom_type(
		"LumurStoryStageHost",
		"RefCounted",
		preload("res://addons/lumur_synesyn/story_stage_host.gd"),
		null
	)
	add_custom_type(
		"LumurStoryStageProjector",
		"Node",
		preload("res://addons/lumur_synesyn/story_stage_projector.gd"),
		null
	)
	add_custom_type(
		"LumurStubStoryStageLayerSource",
		"RefCounted",
		preload("res://addons/lumur_synesyn/stub_story_stage_layer_source.gd"),
		null
	)


func _exit_tree() -> void:
	remove_custom_type("LumurStubStoryStageLayerSource")
	remove_custom_type("LumurStoryStageProjector")
	remove_custom_type("LumurStoryStageHost")
	remove_custom_type("LumurStoryStageLayout")
	remove_custom_type("LumurSynesynHubSurfaceGenerator")
