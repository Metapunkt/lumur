class_name LumurRippleLayer
extends Node

## Draws expanding ripples on the floor surface via paint-mode targeting.
## Listens to ``LumurEventReceiver.footstep`` and stamps rings into a floor
## overlay texture sampled by ``paint_mode.gdshader`` (ripple mode).

@export var receiver_path: NodePath
@export var paint_path: NodePath
@export var runtime_path: NodePath
@export var max_ripples: int = 24
@export var ripple_duration_s: float = 1.4
@export var ripple_color: Color = Color(0.55, 0.85, 1.0, 1.0)
@export var floor_key: String = "floor"

var _receiver: LumurEventReceiver
var _paint: LumurPaintMode
var _runtime: LumurRoomRuntime
var _ripples: Array = []  # dictionaries
var _overlay: Image
var _overlay_tex: ImageTexture
var _proj_w: int = 64
var _proj_h: int = 48
var _floor_id: int = -1
# Floor world extents for mapping position_floor → projector approx via UV.
var _floor_span: float = 4.0


func _ready() -> void:
	if receiver_path != NodePath(""):
		_receiver = get_node_or_null(receiver_path) as LumurEventReceiver
	if _receiver == null:
		_receiver = get_node_or_null("EventReceiver") as LumurEventReceiver
	if paint_path != NodePath(""):
		_paint = get_node_or_null(paint_path) as LumurPaintMode
	if runtime_path != NodePath(""):
		_runtime = get_node_or_null(runtime_path) as LumurRoomRuntime
	if _runtime == null:
		_runtime = get_parent() as LumurRoomRuntime
	if _paint == null and _runtime != null:
		_paint = _runtime.paint
	if _receiver != null:
		_receiver.footstep.connect(_on_footstep)
	call_deferred("_bind_overlay")


func _process(delta: float) -> void:
	if _ripples.is_empty():
		return
	var alive: Array = []
	for r in _ripples:
		r["age"] = float(r["age"]) + delta
		if float(r["age"]) <= ripple_duration_s:
			alive.append(r)
	_ripples = alive
	_redraw_overlay()


func _bind_overlay() -> void:
	if _runtime != null and _runtime.package != null:
		var size := _runtime.package.projector_size()
		_proj_w = size.x
		_proj_h = size.y
		var floor_info := _runtime.package.get_surface(floor_key)
		if not floor_info.is_empty():
			_floor_id = int(floor_info.get("id", -1))
	if _proj_w <= 0 or _proj_h <= 0:
		_proj_w = 64
		_proj_h = 48
	_overlay = Image.create(_proj_w, _proj_h, false, Image.FORMAT_RGBA8)
	_overlay.fill(Color(0, 0, 0, 0))
	_overlay_tex = ImageTexture.create_from_image(_overlay)
	if _paint != null:
		_paint.set_ripple_overlay(_overlay_tex, _floor_id)


func _on_footstep(event: Dictionary) -> void:
	var pf: Array = event.get("position_floor", [0.0, 0.0])
	if pf.size() < 2:
		return
	# Map floor surface metres → normalised UV roughly centred on the room.
	var u := 0.5 + float(pf[0]) / _floor_span
	var v := 0.5 + float(pf[1]) / _floor_span
	u = clampf(u, 0.0, 1.0)
	v = clampf(v, 0.0, 1.0)
	_ripples.append({"u": u, "v": v, "age": 0.0})
	if _ripples.size() > max_ripples:
		_ripples.pop_front()
	_redraw_overlay()


func inject_footstep(position_floor: Vector2, person_id: int = 1, foot: String = "left") -> void:
	_on_footstep({
		"type": "footstep",
		"person_id": person_id,
		"foot": foot,
		"position_floor": [position_floor.x, position_floor.y],
		"position_room": [position_floor.x, 0.0, position_floor.y],
		"timestamp": Time.get_ticks_msec() / 1000.0,
	})


func _redraw_overlay() -> void:
	if _overlay == null:
		return
	_overlay.fill(Color(0, 0, 0, 0))
	for r in _ripples:
		var age: float = float(r["age"])
		var t: float = age / maxf(ripple_duration_s, 1e-3)
		var radius_px: float = lerpf(2.0, float(mini(_proj_w, _proj_h)) * 0.35, t)
		var alpha: float = (1.0 - t) * ripple_color.a
		var cx := int(float(r["u"]) * float(_proj_w))
		var cy := int(float(r["v"]) * float(_proj_h))
		_stroke_circle(cx, cy, radius_px, Color(ripple_color.r, ripple_color.g, ripple_color.b, alpha))
	_overlay_tex.update(_overlay)
	if _paint != null:
		_paint.set_ripple_overlay(_overlay_tex, _floor_id)


func _stroke_circle(cx: int, cy: int, radius: float, color: Color) -> void:
	var r_i := int(ceil(radius))
	var thickness := 1.5
	for y in range(cy - r_i - 1, cy + r_i + 2):
		for x in range(cx - r_i - 1, cx + r_i + 2):
			if x < 0 or y < 0 or x >= _proj_w or y >= _proj_h:
				continue
			var d := Vector2(x - cx, y - cy).length()
			if absf(d - radius) <= thickness:
				var existing := _overlay.get_pixel(x, y)
				_overlay.set_pixel(x, y, Color(
					maxf(existing.r, color.r),
					maxf(existing.g, color.g),
					maxf(existing.b, color.b),
					maxf(existing.a, color.a)
				))
