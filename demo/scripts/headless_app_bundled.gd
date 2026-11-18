extends SceneTree

## Headless smoke: discover bundled paint + ripples manifests via lifecycle.
## Run: godot --headless --path . -s demo/scripts/headless_app_bundled.gd


func _init() -> void:
	var assets := OS.get_environment("LUMUR_GODOT_ASSETS")
	if assets.is_empty():
		push_error("Set LUMUR_GODOT_ASSETS to a godot/ paint export dir")
		quit(2)
		return
	var runtime := LumurRoomRuntime.new()
	root.add_child(runtime)
	var err := runtime.load_room(assets)
	if err != OK:
		push_error("load_room failed")
		quit(3)
		return
	var paint_path := ProjectSettings.globalize_path("res://apps/paint/lumur.app.json")
	var ripples_path := ProjectSettings.globalize_path("res://apps/ripples/lumur.app.json")
	runtime.install_app(paint_path)
	runtime.install_app(ripples_path)
	var paint := runtime.launch_app("lumur.paint")
	var ripples := runtime.launcher.start("lumur.ripples")
	if paint.is_empty() or ripples.is_empty():
		push_error("launch failed paint=%s ripples=%s" % [paint, ripples])
		quit(4)
		return
	print("bundled_ok paint=%s ripples=%s" % [
		paint.get("state", ""),
		ripples.get("state", ""),
	])
	quit(0)
