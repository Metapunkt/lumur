class_name LumurDefaultAssets
extends RefCounted

## Resolve Godot paint assets: ``LUMUR_GODOT_ASSETS``, else the committed
## ``demo/fixtures/sample_room/godot`` fixture (no ``/tmp/sim-room`` hardcode).


static func resolve() -> String:
	var env := OS.get_environment("LUMUR_GODOT_ASSETS")
	if not env.is_empty():
		return env
	var fixture := ProjectSettings.globalize_path("res://demo/fixtures/sample_room/godot")
	if FileAccess.file_exists(fixture.path_join("paint_manifest.json")):
		return fixture
	return "demo/fixtures/sample_room/godot"
