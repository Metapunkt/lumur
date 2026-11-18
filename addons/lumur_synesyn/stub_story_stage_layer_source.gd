class_name LumurStubStoryStageLayerSource
extends LumurStoryStageLayerSource

## Deterministic mock producing known solid colours per layer (PRD-002 slice 3).

var scenario: Dictionary = {}
var colors: Dictionary = {
	LAYER_BACKDROP: Color(0.08, 0.12, 0.92),
	LAYER_CHARACTER: Color(0.12, 0.88, 0.18),
	LAYER_CLIP: Color(0.95, 0.55, 0.08),
	LAYER_CAPTION: Color(0.95, 0.92, 0.15),
	LAYER_AMBIENCE: Color(0.92, 0.10, 0.12),
}
var clip_start_s: float = 0.5
var clip_fade_s: float = 0.25
var include_clip: bool = true


func get_scenario() -> Dictionary:
	return scenario


func snapshot(time_s: float = 0.0) -> Dictionary:
	var out := {}
	for layer in LumurStoryStageLayout.CANONICAL_LAYERS:
		var key := str(layer)
		if key == LAYER_CLIP and not include_clip:
			continue
		if key == LAYER_CLIP and time_s < clip_start_s:
			continue
		var color: Color = colors.get(key, Color(0.5, 0.5, 0.5))
		var meta := {}
		var transition := "cut"
		if key == LAYER_CLIP and include_clip and clip_fade_s > 0.0:
			var fade := clampf((time_s - clip_start_s) / clip_fade_s, 0.0, 1.0)
			meta["fade"] = fade
			if fade < 1.0:
				transition = "crossfade"
		out[key] = {
			"color": color,
			"texture": null,
			"transition": transition,
			"meta": meta,
		}
	return out
