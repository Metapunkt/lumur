extends SceneTree

## Headless ripple stamp verification.
## Usage:
##   godot --path . --script res://demo/scripts/headless_ripple_render.gd \
##     -- --assets=/path/to/godot --out=/tmp/ripple.png \
##        --foot=0.2,0.1 --foot=-0.3,0.4

func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var assets_path: String = str(args.get("assets", ""))
	var out_path: String = str(args.get("out", "ripple_out.png"))
	if assets_path.is_empty():
		push_error("missing --assets=")
		quit(2)
		return

	var package := LumurRoomPackage.new()
	if package.load_godot_dir(assets_path) != OK:
		quit(3)
		return

	var size := package.projector_size()
	var viewport := SubViewport.new()
	viewport.size = size
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)

	var paint := LumurPaintMode.new()
	paint.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	viewport.add_child(paint)
	paint.bind_package(package)
	var floor_t := paint.get_target("floor")
	if floor_t != null:
		floor_t.set_solid_color(Color(0.12, 0.18, 0.22))

	var runtime := LumurRoomRuntime.new()
	runtime.paint = paint
	runtime.package = package
	root.add_child(runtime)

	var ripples := LumurRippleLayer.new()
	ripples._paint = paint
	ripples._runtime = runtime
	root.add_child(ripples)
	ripples._bind_overlay()

	# Inject footsteps from --foot=x,z args (may appear multiple times via CSV list).
	var feet: Array = []
	if args.has("foot"):
		var raw = str(args["foot"])
		for part in raw.split(";"):
			var xy := part.split(",")
			if xy.size() >= 2:
				feet.append(Vector2(float(xy[0]), float(xy[1])))
	if feet.is_empty():
		feet = [Vector2(0.0, 0.0), Vector2(0.4, -0.2)]
	for f in feet:
		ripples.inject_footstep(f)
	# Age ripples a bit so rings are visible.
	for i in range(8):
		ripples._process(0.05)
		await process_frame

	await process_frame
	var img: Image = viewport.get_texture().get_image()
	if img == null or img.is_empty():
		quit(5)
		return
	img.save_png(out_path)
	print("wrote %s" % out_path)
	quit(0)


func _parse_args() -> Dictionary:
	var out := {}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--") and "=" in a:
			var parts := a.substr(2).split("=", false, 1)
			if parts.size() == 2:
				out[parts[0]] = parts[1]
	return out
