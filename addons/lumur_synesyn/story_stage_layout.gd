class_name LumurStoryStageLayout
extends RefCounted

## Story Stage layer roles → Lumur surface roles (PRD-002 slice 3).
## Mapping is by role name, not projector UV (REQ-002-009).

const LAYER_BACKDROP := "backdrop"
const LAYER_CHARACTER := "character"
const LAYER_CLIP := "clip"
const LAYER_CAPTION := "caption"
const LAYER_AMBIENCE := "ambience"

const CANONICAL_LAYERS := [
	LAYER_BACKDROP,
	LAYER_CHARACTER,
	LAYER_CLIP,
	LAYER_CAPTION,
	LAYER_AMBIENCE,
]

## layer -> ordered surface-role preference chain
var preferences: Dictionary = {
	LAYER_BACKDROP: ["wall_1", "wall_2", "floor"],
	LAYER_CHARACTER: ["wall_2", "wall_1", "floor"],
	LAYER_CLIP: ["wall_2", "wall_1", "floor"],
	LAYER_CAPTION: ["wall_1", "wall_2", "floor"],
	LAYER_AMBIENCE: ["floor", "wall_2", "wall_1"],
}

## Optional single-role overrides from a scenario section.
var overrides: Dictionary = {}

## layer -> {left,right,top,bottom} normalised insets
var safe_areas: Dictionary = {
	LAYER_BACKDROP: {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
	LAYER_CHARACTER: {"left": 0.1, "right": 0.1, "top": 0.05, "bottom": 0.15},
	LAYER_CLIP: {"left": 0.1, "right": 0.1, "top": 0.05, "bottom": 0.15},
	LAYER_CAPTION: {"left": 0.05, "right": 0.05, "top": 0.72, "bottom": 0.04},
	LAYER_AMBIENCE: {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0},
}


static func canonical_layer(name: String) -> String:
	var key := name.strip_edges().to_lower().replace("-", "_").replace(" ", "_")
	match key:
		"background", "vis_story", "backdrop":
			return LAYER_BACKDROP
		"portrait", "portraits", "characters", "character", "sprites", "sprite":
			return LAYER_CHARACTER
		"flashhead", "video", "clip", "talking_clip", "ogv":
			return LAYER_CLIP
		"text", "captions", "caption", "dialogue", "dialog":
			return LAYER_CAPTION
		"ambient", "ambience", "ripples":
			return LAYER_AMBIENCE
		_:
			return key


static func from_scenario(scenario: Dictionary) -> LumurStoryStageLayout:
	## Only reads known lumur_* layout sections; all other keys are ignored
	## (REQ-002-010).
	var layout := LumurStoryStageLayout.new()
	if scenario.is_empty():
		return layout
	var section: Dictionary = {}
	for key in scenario.keys():
		var lk := str(key).strip_edges().to_lower()
		if lk in ["lumur_layout", "lumur_story_stage", "lumur_surfaces"]:
			var value: Variant = scenario[key]
			if typeof(value) == TYPE_DICTIONARY:
				section = value
				break
	if section.is_empty():
		return layout
	var enabled := str(section.get("enabled", "true")).to_lower()
	if enabled in ["0", "false", "no", "off"]:
		return layout
	var mapping: Variant = section.get("layout", section.get("surfaces", section))
	if typeof(mapping) == TYPE_DICTIONARY:
		for raw_layer in mapping.keys():
			var layer := canonical_layer(str(raw_layer))
			if layer not in CANONICAL_LAYERS:
				continue
			var raw_role: Variant = mapping[raw_layer]
			if typeof(raw_role) == TYPE_ARRAY:
				var roles: Array = []
				for r in raw_role:
					var s := str(r).strip_edges()
					if not s.is_empty():
						roles.append(s)
				if not roles.is_empty():
					layout.preferences[layer] = roles
					layout.overrides[layer] = str(roles[0])
			else:
				var role := str(raw_role).strip_edges()
				if role.is_empty():
					continue
				if role.to_lower() in ["enabled", "safe_areas", "layout", "surfaces"]:
					continue
				layout.overrides[layer] = role
	var safe_raw: Variant = section.get("safe_areas", {})
	if typeof(safe_raw) == TYPE_DICTIONARY:
		for raw_layer in safe_raw.keys():
			var layer := canonical_layer(str(raw_layer))
			if layer not in CANONICAL_LAYERS:
				continue
			var area: Variant = safe_raw[raw_layer]
			if typeof(area) == TYPE_DICTIONARY:
				layout.safe_areas[layer] = {
					"left": float(area.get("left", 0.0)),
					"right": float(area.get("right", 0.0)),
					"top": float(area.get("top", 0.0)),
					"bottom": float(area.get("bottom", 0.0)),
				}
	return layout


func preference_for(layer: String) -> PackedStringArray:
	var canonical := canonical_layer(layer)
	var out := PackedStringArray()
	if overrides.has(canonical):
		out.append(str(overrides[canonical]))
	var prefs: Array = preferences.get(canonical, ["floor"])
	for role in prefs:
		var r := str(role)
		if r in out:
			continue
		out.append(r)
	return out


func safe_area_for(layer: String) -> Dictionary:
	var canonical := canonical_layer(layer)
	return safe_areas.get(canonical, {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0})


func resolve_surface_role(layer: String, available_roles: PackedStringArray) -> String:
	## Empty string when the room has no candidate (skip that layer).
	var present := {}
	for r in available_roles:
		present[str(r)] = true
	for role in preference_for(layer):
		if present.has(role):
			return role
	return ""


func resolve_all(available_roles: PackedStringArray) -> Dictionary:
	var out := {}
	for layer in CANONICAL_LAYERS:
		var role := resolve_surface_role(str(layer), available_roles)
		out[str(layer)] = role
	return out
