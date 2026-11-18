class_name LumurPaintMode
extends ColorRect

## Fullscreen projector output: maps per-surface content through the
## projector↔surface correspondence textures exported by the companion.

@export var confidence_threshold: float = 0.05
@export var clear_color: Color = Color.BLACK

var _package: LumurRoomPackage
var _targets: Dictionary = {}  # surface_id -> LumurSurfaceTarget
var _material: ShaderMaterial
var _palette_image: Image
var _mode_image: Image
var _palette_tex: ImageTexture
var _mode_tex: ImageTexture
var _time_s: float = 0.0


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_ensure_material()


func _process(delta: float) -> void:
	_time_s += delta
	if _material != null:
		_material.set_shader_parameter("time_seconds", _time_s)


func bind_package(package: LumurRoomPackage) -> void:
	_package = package
	_targets.clear()
	for info in package.list_surfaces():
		var t := LumurSurfaceTarget.new(info)
		_targets[t.surface_id] = t
		t.content_changed.connect(_rebuild_palette)
	confidence_threshold = package.confidence_threshold_default()
	_ensure_material()
	_material.set_shader_parameter("surface_id_tex", package.surface_id_texture)
	_material.set_shader_parameter("confidence_tex", package.confidence_texture)
	_material.set_shader_parameter("lookup_tex", package.lookup_texture)
	_material.set_shader_parameter("confidence_threshold", confidence_threshold)
	_material.set_shader_parameter("clear_color", clear_color)
	_rebuild_palette()
	var size := package.projector_size()
	if size.x > 0 and size.y > 0:
		custom_minimum_size = Vector2(size)


func get_target(key: Variant) -> LumurSurfaceTarget:
	if _package == null:
		return null
	var sid := _package.resolve_surface_id(key)
	if sid < 0:
		return null
	return _targets.get(sid)


func set_surface_color(key: Variant, color: Color) -> void:
	var t := get_target(key)
	if t != null:
		t.set_solid_color(color)


func set_surface_pulse(key: Variant, color: Color, hz: float = 1.0) -> void:
	var t := get_target(key)
	if t != null:
		t.set_pulse(color, hz)


func set_time_seconds(t: float) -> void:
	_time_s = t
	if _material != null:
		_material.set_shader_parameter("time_seconds", _time_s)


func _ensure_material() -> void:
	if _material != null:
		material = _material
		return
	var shader := load("res://addons/lumur/paint_mode.gdshader") as Shader
	_material = ShaderMaterial.new()
	_material.shader = shader
	material = _material
	_palette_image = Image.create(256, 1, false, Image.FORMAT_RGBA8)
	_mode_image = Image.create(256, 1, false, Image.FORMAT_R8)
	_palette_tex = ImageTexture.create_from_image(_palette_image)
	_mode_tex = ImageTexture.create_from_image(_mode_image)
	_material.set_shader_parameter("palette_tex", _palette_tex)
	_material.set_shader_parameter("mode_tex", _mode_tex)


func _rebuild_palette() -> void:
	if _palette_image == null:
		_ensure_material()
	_palette_image.fill(Color(0, 0, 0, 1))
	_mode_image.fill(Color(0, 0, 0, 1))
	for sid in _targets.keys():
		var t: LumurSurfaceTarget = _targets[sid]
		var x := int(sid)
		if x < 0 or x > 255:
			continue
		_palette_image.set_pixel(x, 0, t.color)
		var mode_v := 0.0
		if t.mode == LumurSurfaceTarget.MODE_TEXTURE:
			mode_v = 1.0 / 255.0
		elif t.mode == LumurSurfaceTarget.MODE_PULSE:
			mode_v = 2.0 / 255.0
		_mode_image.set_pixel(x, 0, Color(mode_v, 0, 0))
	_palette_tex.update(_palette_image)
	_mode_tex.update(_mode_image)
	_material.set_shader_parameter("confidence_threshold", confidence_threshold)
	_material.set_shader_parameter("clear_color", clear_color)
