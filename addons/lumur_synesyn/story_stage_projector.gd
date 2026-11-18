class_name LumurStoryStageProjector
extends Node

## Maps Story Stage layers onto Lumur paint surfaces (PRD-002 slice 3).
##
## Observes a ``LumurStoryStageLayerSource`` (stub or live wrapper) and pushes
## composed textures through ``LumurPaintMode`` / ``LumurRoomRuntime``. Does not
## modify Synesyn ``story_stage`` — bind an observer source when that addon is
## present.

@export var paint_path: NodePath
@export var runtime_path: NodePath
@export var texture_size: Vector2i = Vector2i(64, 64)

var source: LumurStoryStageLayerSource
var host: LumurStoryStageHost
var layout: LumurStoryStageLayout = LumurStoryStageLayout.new()
var paint: LumurPaintMode
var runtime: LumurRoomRuntime
var package: LumurRoomPackage

## Last resolved layer → surface role (empty string = skipped).
var last_binding: Dictionary = {}
var last_time_s: float = 0.0


func _ready() -> void:
	if paint_path != NodePath(""):
		paint = get_node_or_null(paint_path) as LumurPaintMode
	if runtime_path != NodePath(""):
		runtime = get_node_or_null(runtime_path) as LumurRoomRuntime
	if paint == null and runtime != null:
		paint = runtime.paint
	if package == null and runtime != null:
		package = runtime.package
	if source == null:
		source = LumurStubStoryStageLayerSource.new()
	if host == null:
		host = LumurStoryStageHost.new()


func configure(
	layer_source: LumurStoryStageLayerSource,
	paint_mode: LumurPaintMode,
	stage_host: LumurStoryStageHost = null,
	room_package: LumurRoomPackage = null,
) -> void:
	source = layer_source
	paint = paint_mode
	if room_package != null:
		package = room_package
	if stage_host != null:
		host = stage_host
		layout = host.get_layout()
	elif source != null:
		layout = LumurStoryStageLayout.from_scenario(source.get_scenario())


func available_roles() -> PackedStringArray:
	if runtime != null:
		return runtime.list_roles()
	var out := PackedStringArray()
	if package == null:
		return out
	var index: Dictionary = package.manifest.get("role_index", {})
	for k in index.keys():
		out.append(str(k))
	return out


func project_at(time_s: float = 0.0) -> Dictionary:
	## Apply the current source snapshot to paint. Returns binding + applied count.
	last_time_s = time_s
	if source == null or paint == null:
		return {"ok": false, "applied": 0, "binding": {}, "skipped": []}
	layout = LumurStoryStageLayout.from_scenario(source.get_scenario())
	if host != null:
		host.set_scenario(source.get_scenario())
		layout = host.get_layout()
	var roles := available_roles()
	last_binding = layout.resolve_all(roles)
	var snap: Dictionary = source.snapshot(time_s)
	var applied := 0
	var skipped: Array = []
	var surface_colors: Dictionary = {}
	var textured_roles: Dictionary = {}
	for layer in LumurStoryStageLayout.CANONICAL_LAYERS:
		var key := str(layer)
		if not snap.has(key):
			continue
		var role := str(last_binding.get(key, ""))
		if role.is_empty():
			skipped.append(key)
			continue
		var entry: Dictionary = snap[key]
		var color: Color = entry.get("color", Color.WHITE)
		var meta: Variant = entry.get("meta", {})
		var fade := 1.0
		if typeof(meta) == TYPE_DICTIONARY:
			fade = float(meta.get("fade", 1.0))
		var tex: Texture2D = entry.get("texture", null)
		if tex != null and key != LumurStoryStageLayout.LAYER_CLIP:
			if runtime != null:
				runtime.texture_surface(role, tex)
			else:
				paint.set_surface_texture(role, tex)
			textured_roles[role] = true
			applied += 1
			continue
		if key == LumurStoryStageLayout.LAYER_CLIP and surface_colors.has(role):
			var base: Color = surface_colors[role]
			surface_colors[role] = base.lerp(color, fade)
		elif key == LumurStoryStageLayout.LAYER_CAPTION and surface_colors.has(role):
			var base2: Color = surface_colors[role]
			surface_colors[role] = base2.lerp(color, 0.35)
		else:
			surface_colors[role] = color
	for role in surface_colors.keys():
		if textured_roles.has(role):
			continue
		var solid := _solid_texture(surface_colors[role])
		if runtime != null:
			runtime.texture_surface(role, solid)
		else:
			paint.set_surface_texture(role, solid)
		applied += 1
	return {
		"ok": true,
		"applied": applied,
		"binding": last_binding.duplicate(),
		"skipped": skipped,
		"time_s": time_s,
	}


func _solid_texture(color: Color) -> ImageTexture:
	var img := Image.create(maxi(1, texture_size.x), maxi(1, texture_size.y), false, Image.FORMAT_RGBA8)
	img.fill(color)
	return ImageTexture.create_from_image(img)


## Optional non-invasive bind: read textures from a live Story Stage node tree
## when ``addons/story_stage`` is installed. Missing nodes are ignored.
func observe_story_stage(stage_root: Node) -> void:
	if stage_root == null:
		return
	var observer := LumurStoryStageObserverSource.new()
	observer.bind_stage(stage_root)
	source = observer
	if not observer.layers_changed.is_connected(_on_layers_changed):
		observer.layers_changed.connect(_on_layers_changed)


func _on_layers_changed() -> void:
	project_at(last_time_s)
