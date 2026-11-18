class_name LumurSurfaceTarget
extends RefCounted

## Small surface-addressing helper consistent with the room-as-OS idea
## (ADR 0006): apps ask for ``floor`` / ``wall_n`` / plane id, not raw UVs.

signal content_changed

const MODE_SOLID := "solid"
const MODE_TEXTURE := "texture"
const MODE_PULSE := "pulse"

var surface_id: int = 0
var roles: PackedStringArray = PackedStringArray()
var kind: String = ""
var label: String = ""

var mode: String = MODE_SOLID
var color: Color = Color.WHITE
var texture: Texture2D
var pulse_hz: float = 1.0


func _init(info: Dictionary = {}) -> void:
	if info.is_empty():
		return
	surface_id = int(info.get("id", 0))
	kind = str(info.get("kind", ""))
	label = str(info.get("label", ""))
	roles = PackedStringArray()
	for r in info.get("roles", []):
		roles.append(str(r))


func set_solid_color(c: Color) -> void:
	mode = MODE_SOLID
	color = c
	content_changed.emit()


func set_texture(tex: Texture2D, tint: Color = Color.WHITE) -> void:
	mode = MODE_TEXTURE
	texture = tex
	color = tint
	content_changed.emit()


func set_pulse(c: Color, hz: float = 1.0) -> void:
	mode = MODE_PULSE
	color = c
	pulse_hz = hz
	content_changed.emit()


func matches(key: Variant) -> bool:
	if typeof(key) == TYPE_INT or typeof(key) == TYPE_FLOAT:
		return int(key) == surface_id
	var name := str(key)
	if name == label:
		return true
	for r in roles:
		if r == name:
			return true
	return false
