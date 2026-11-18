class_name LumurAppManifest
extends RefCounted

## Loader / validator for ``lumur.app`` v1.0 (ADR 0017, PRD-003 slice 1).
## Unknown fields are ignored. Placement / pixel / UV keys are rejected.

const SCHEMA_ID := "lumur.app"
const SCHEMA_VERSION := "1.0"

const KNOWN_INPUTS := [
	"footstep",
	"presence",
	"zone_enter",
	"zone_leave",
	"gathering",
]

const _FORBIDDEN_SURFACE_KEYS := [
	"plane_id",
	"surface_id",
	"pixel_rect",
	"projector_rect",
	"rect",
	"uv",
	"uvs",
	"uv_quad",
	"projector_uv",
	"pixels",
	"x",
	"y",
	"width_px",
	"height_px",
]

var document: Dictionary = {}
var path: String = ""
var last_error: String = ""


func load_file(file_path: String) -> Error:
	path = file_path
	last_error = ""
	if not FileAccess.file_exists(file_path):
		last_error = "manifest not found: %s" % file_path
		return ERR_FILE_NOT_FOUND
	var raw := FileAccess.get_file_as_string(file_path)
	var parsed: Variant = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		last_error = "manifest is not a JSON object"
		return ERR_INVALID_DATA
	return load_document(parsed)


func load_document(doc: Dictionary) -> Error:
	document = doc
	last_error = ""
	var err := validate(doc)
	if err != OK:
		return err
	return OK


static func validate(doc: Dictionary) -> Error:
	if str(doc.get("schema", "")) != SCHEMA_ID:
		push_error("LumurAppManifest: expected schema %s, got %s" % [SCHEMA_ID, doc.get("schema")])
		return ERR_INVALID_DATA
	if str(doc.get("schema_version", "")) != SCHEMA_VERSION:
		push_error(
			"LumurAppManifest: unsupported schema_version %s (understands %s)"
			% [doc.get("schema_version"), SCHEMA_VERSION]
		)
		return ERR_INVALID_DATA
	for key in ["id", "name", "version", "scene", "surfaces", "inputs"]:
		if not doc.has(key):
			push_error("LumurAppManifest: missing %s" % key)
			return ERR_INVALID_DATA
	for field in ["id", "name", "version", "scene"]:
		if typeof(doc[field]) != TYPE_STRING or str(doc[field]).strip_edges().is_empty():
			push_error("LumurAppManifest: %s must be a non-empty string" % field)
			return ERR_INVALID_DATA
	if typeof(doc["surfaces"]) != TYPE_ARRAY:
		push_error("LumurAppManifest: surfaces must be an array")
		return ERR_INVALID_DATA
	var keys_seen := {}
	var i := 0
	for req_v in doc["surfaces"]:
		if typeof(req_v) != TYPE_DICTIONARY:
			push_error("LumurAppManifest: surfaces[%d] must be an object" % i)
			return ERR_INVALID_DATA
		var req: Dictionary = req_v
		for bad in _FORBIDDEN_SURFACE_KEYS:
			if req.has(bad):
				push_error(
					"LumurAppManifest: surfaces[%d] must not include placement field %s"
					% [i, bad]
				)
				return ERR_INVALID_DATA
		var skey := str(req.get("key", ""))
		if skey.strip_edges().is_empty():
			push_error("LumurAppManifest: surfaces[%d].key required" % i)
			return ERR_INVALID_DATA
		if keys_seen.has(skey):
			push_error("LumurAppManifest: duplicate surface key %s" % skey)
			return ERR_INVALID_DATA
		keys_seen[skey] = true
		if str(req.get("role", "")).strip_edges().is_empty():
			push_error("LumurAppManifest: surfaces[%d].role required" % i)
			return ERR_INVALID_DATA
		i += 1
	if typeof(doc["inputs"]) != TYPE_ARRAY:
		push_error("LumurAppManifest: inputs must be an array")
		return ERR_INVALID_DATA
	for item in doc["inputs"]:
		var name := str(item)
		if not KNOWN_INPUTS.has(name):
			push_error("LumurAppManifest: unknown input permission %s" % name)
			return ERR_INVALID_DATA
	return OK


func app_id() -> String:
	return str(document.get("id", ""))


func scene_path() -> String:
	return str(document.get("scene", ""))


func surface_requests() -> Array:
	return document.get("surfaces", [])


func inputs() -> PackedStringArray:
	var out := PackedStringArray()
	for item in document.get("inputs", []):
		out.append(str(item))
	return out
