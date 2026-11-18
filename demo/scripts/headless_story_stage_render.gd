extends SceneTree

## Headless Story Stage → paint render (PRD-002 slice 3).
##
## Uses the stub layer source (no Synesyn required). Prefer the Python
## reference path in CI; this script is optional when Godot + xvfb are present.
##
## Usage:
##   xvfb-run -a godot --path . --display-driver x11 --rendering-driver opengl3 \
##     --script res://demo/scripts/headless_story_stage_render.gd \
##     -- --assets=/path/to/room/godot --out=/tmp/story_stage_paint.png

func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var assets_path: String = str(args.get("assets", ""))
	var out_path: String = str(args.get("out", "story_stage_paint.png"))
	if assets_path.is_empty():
		push_error("headless_story_stage_render: missing --assets=/path/to/godot")
		quit(2)
		return

	var package := LumurRoomPackage.new()
	var err := package.load_godot_dir(assets_path)
	if err != OK:
		push_error("failed to load assets: %s" % assets_path)
		quit(3)
		return

	var size := package.projector_size()
	var viewport := SubViewport.new()
	viewport.size = size
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.transparent_bg = false
	root.add_child(viewport)

	var paint := LumurPaintMode.new()
	paint.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	viewport.add_child(paint)
	paint.bind_package(package)

	var stub := LumurStubStoryStageLayerSource.new()
	var projector := LumurStoryStageProjector.new()
	root.add_child(projector)
	projector.configure(stub, paint, null, package)
	var result: Dictionary = projector.project_at(0.0)
	print("story_stage binding=%s applied=%s" % [result.get("binding", {}), result.get("applied", 0)])

	await process_frame
	await process_frame

	var tex := viewport.get_texture()
	if tex == null:
		push_error("viewport texture missing")
		quit(4)
		return
	var img: Image = tex.get_image()
	if img == null or img.is_empty():
		push_error("viewport image empty")
		quit(5)
		return
	err = img.save_png(out_path)
	if err != OK:
		push_error("save_png failed: %s" % out_path)
		quit(6)
		return
	print("wrote %s (%dx%d)" % [out_path, img.get_width(), img.get_height()])
	quit(0)


func _parse_args() -> Dictionary:
	var out := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--") and "=" in a:
			var parts := a.substr(2).split("=", false, 1)
			if parts.size() == 2:
				out[parts[0]] = parts[1]
		elif a.begins_with("--"):
			out[a.substr(2)] = true
	return out
