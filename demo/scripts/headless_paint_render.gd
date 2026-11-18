extends SceneTree

## Headless paint render: load exported godot/ assets, paint surfaces, save PNG.
##
## Usage:
##   godot --headless --path . \
##     --script res://demo/scripts/headless_paint_render.gd \
##     -- --assets=/path/to/room/godot --out=/tmp/paint.png

const FLOOR_COLOR := Color(0.85, 0.15, 0.12, 1.0)
const WALL_COLOR := Color(0.12, 0.55, 0.85, 1.0)
const OTHER_COLOR := Color(0.20, 0.75, 0.35, 1.0)


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var assets_path: String = str(args.get("assets", ""))
	var out_path: String = str(args.get("out", "paint_out.png"))
	if assets_path.is_empty():
		push_error("headless_paint_render: missing --assets=/path/to/godot")
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

	# Distinct solid colours per role / remaining surfaces.
	var painted_ids: Dictionary = {}
	var floor_t := paint.get_target("floor")
	if floor_t != null:
		floor_t.set_solid_color(FLOOR_COLOR)
		painted_ids[floor_t.surface_id] = true
	for role_i in range(1, 8):
		var wall_t := paint.get_target("wall_%d" % role_i)
		if wall_t == null:
			break
		wall_t.set_solid_color(WALL_COLOR)
		painted_ids[wall_t.surface_id] = true
	for info in package.list_surfaces():
		var sid := int(info.get("id", 0))
		if painted_ids.has(sid):
			continue
		var t := paint.get_target(sid)
		if t != null:
			t.set_solid_color(OTHER_COLOR)

	# Allow one frame for the viewport to draw.
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
	# gl_compatibility + SubViewport already matches surface_id.png row order;
	# do not flip_y here or floor/wall colours disagree with the export maps.
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
