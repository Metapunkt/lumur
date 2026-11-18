class_name LumurRoomPackage
extends RefCounted

## Loads a companion-exported ``godot/`` paint asset directory
## (``paint_manifest.json`` + PNG lookups). Does not read ``.npz``.

var manifest: Dictionary = {}
var assets_dir: String = ""
var surface_id_texture: ImageTexture
var confidence_texture: ImageTexture
var lookup_texture: ImageTexture
var _role_index: Dictionary = {}
var _surfaces_by_id: Dictionary = {}


func load_godot_dir(path: String) -> Error:
	assets_dir = path
	var manifest_path := path.path_join("paint_manifest.json")
	if not FileAccess.file_exists(manifest_path):
		push_error("LumurRoomPackage: missing %s" % manifest_path)
		return ERR_FILE_NOT_FOUND
	var raw := FileAccess.get_file_as_string(manifest_path)
	var parsed: Variant = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		push_error("LumurRoomPackage: invalid paint_manifest.json")
		return ERR_INVALID_DATA
	manifest = parsed
	if str(manifest.get("schema", "")) != "lumur.paint_godot":
		push_error("LumurRoomPackage: unexpected schema %s" % manifest.get("schema"))
		return ERR_INVALID_DATA

	var textures: Dictionary = manifest.get("textures", {})
	surface_id_texture = _load_image_texture(path.path_join(str(textures.get("surface_id", "surface_id.png"))))
	confidence_texture = _load_image_texture(path.path_join(str(textures.get("confidence", "confidence.png"))))
	lookup_texture = _load_image_texture(path.path_join(str(textures.get("lookup", "lookup.png"))))
	if surface_id_texture == null or confidence_texture == null or lookup_texture == null:
		return ERR_FILE_CORRUPT

	_role_index = manifest.get("role_index", {})
	_surfaces_by_id.clear()
	for s in manifest.get("surfaces", []):
		if typeof(s) == TYPE_DICTIONARY:
			_surfaces_by_id[int(s.get("id", 0))] = s
	return OK


func projector_size() -> Vector2i:
	var res: Array = manifest.get("projector_resolution", [0, 0])
	return Vector2i(int(res[0]), int(res[1]))


func confidence_threshold_default() -> float:
	return float(manifest.get("confidence_threshold_default", 0.05))


func list_surfaces() -> Array:
	return manifest.get("surfaces", [])


func list_roles() -> Array:
	var keys: Array = _role_index.keys()
	keys.sort()
	return keys


func resolve_surface_id(key: Variant) -> int:
	## Accept an int id, or a role/label string (``floor``, ``wall_1``, …).
	if typeof(key) == TYPE_INT:
		return int(key)
	if typeof(key) == TYPE_FLOAT:
		return int(key)
	var name := str(key)
	if _role_index.has(name):
		return int(_role_index[name])
	# Fall back: "id:3"
	if name.begins_with("id:"):
		return int(name.substr(3))
	return -1


func get_surface(key: Variant) -> Dictionary:
	var sid := resolve_surface_id(key)
	if sid < 0:
		return {}
	return _surfaces_by_id.get(sid, {})


func _load_image_texture(path: String) -> ImageTexture:
	if not FileAccess.file_exists(path):
		push_error("LumurRoomPackage: missing texture %s" % path)
		return null
	var img := Image.load_from_file(path)
	if img == null or img.is_empty():
		push_error("LumurRoomPackage: failed to decode %s" % path)
		return null
	# Nearest sampling is set on the shader uniforms; keep the image as-is.
	return ImageTexture.create_from_image(img)
