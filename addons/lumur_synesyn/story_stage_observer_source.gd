class_name LumurStoryStageObserverSource
extends LumurStoryStageLayerSource

## Non-invasive observer for a live Synesyn ``story_stage`` node tree.
##
## Reads public / unique nodes when present (``%Background``, character sprite,
## dialog line). Missing nodes simply omit that layer — no edits to Synesyn.
## Video clips (``.ogv`` / ``VideoStreamPlayer``) are sampled as the player's
## current frame texture when Godot exposes one; otherwise the layer falls back
## to the portrait colour.

var stage_root: Node
var scenario: Dictionary = {}
var fallback_colors: Dictionary = {
	LAYER_BACKDROP: Color(0.08, 0.12, 0.92),
	LAYER_CHARACTER: Color(0.12, 0.88, 0.18),
	LAYER_CLIP: Color(0.95, 0.55, 0.08),
	LAYER_CAPTION: Color(0.95, 0.92, 0.15),
	LAYER_AMBIENCE: Color(0.15, 0.15, 0.18),
}


func bind_stage(root: Node) -> void:
	stage_root = root
	if root != null and root.get("host") != null:
		var host: Variant = root.get("host")
		if host != null and host.has_method("get_scenario"):
			scenario = host.get_scenario()


func get_scenario() -> Dictionary:
	if stage_root != null and stage_root.get("host") != null:
		var host: Variant = stage_root.get("host")
		if host != null and host.has_method("get_scenario"):
			return host.get_scenario()
	return scenario


func snapshot(time_s: float = 0.0) -> Dictionary:
	var out := {}
	out[LAYER_BACKDROP] = _layer_from_texture(
		LAYER_BACKDROP, _find_background_texture(), time_s
	)
	out[LAYER_CHARACTER] = _layer_from_texture(
		LAYER_CHARACTER, _find_portrait_texture(), time_s
	)
	var clip_tex := _find_clip_texture()
	if clip_tex != null:
		out[LAYER_CLIP] = _layer_from_texture(LAYER_CLIP, clip_tex, time_s)
	out[LAYER_CAPTION] = {
		"color": fallback_colors.get(LAYER_CAPTION, Color.YELLOW),
		"texture": null,
		"transition": "cut",
		"meta": {"text": _find_caption_text()},
	}
	out[LAYER_AMBIENCE] = {
		"color": fallback_colors.get(LAYER_AMBIENCE, Color(0.15, 0.15, 0.18)),
		"texture": null,
		"transition": "cut",
		"meta": {},
	}
	return out


func _layer_from_texture(layer: String, tex: Texture2D, _time_s: float) -> Dictionary:
	return {
		"color": fallback_colors.get(layer, Color.WHITE),
		"texture": tex,
		"transition": "cut",
		"meta": {},
	}


func _find_background_texture() -> Texture2D:
	if stage_root == null:
		return null
	var bg := stage_root.get_node_or_null("%Background") as TextureRect
	if bg != null and bg.texture != null:
		return bg.texture
	var path_bg := stage_root.get_node_or_null("CanvasLayer/Background") as TextureRect
	if path_bg != null:
		return path_bg.texture
	return null


func _find_portrait_texture() -> Texture2D:
	if stage_root == null:
		return null
	var sprite := stage_root.get_node_or_null("%AnimatedSprite2D") as AnimatedSprite2D
	if sprite != null and sprite.sprite_frames != null:
		var anim := sprite.animation
		if sprite.sprite_frames.has_animation(anim):
			var frame := sprite.frame
			return sprite.sprite_frames.get_frame_texture(anim, frame)
	var surface := stage_root.get_node_or_null("StageViewport/StageWorld/SurfacePortrait") as Sprite2D
	if surface != null:
		return surface.texture
	return null


func _find_clip_texture() -> Texture2D:
	if stage_root == null:
		return null
	# Prefer an active VideoStreamPlayer under the stage (FlashHead .ogv).
	var players := _find_video_players(stage_root)
	for player in players:
		if player.is_playing():
			# Godot 4 VideoStreamPlayer has no direct get_video_texture on all
			# backends; when unavailable the projector keeps the portrait layer.
			if player.has_method("get_video_texture"):
				return player.call("get_video_texture") as Texture2D
	return null


func _find_caption_text() -> String:
	if stage_root == null:
		return ""
	var line := stage_root.get_node_or_null("%DialogLine") as RichTextLabel
	if line != null:
		return line.get_parsed_text()
	return ""


func _find_video_players(node: Node) -> Array:
	var found: Array = []
	if node is VideoStreamPlayer:
		found.append(node)
	for child in node.get_children():
		found.append_array(_find_video_players(child))
	return found
