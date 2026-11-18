class_name LumurStoryStageLayerSource
extends RefCounted

## Abstract Story Stage layer source for the Lumur bridge.
##
## Live installs may subclass this to observe Synesyn ``story_stage`` nodes
## non-invasively (read %Background / portrait / DialogLine textures). Headless
## verification uses ``LumurStubStoryStageLayerSource``.

signal layers_changed

const LAYER_BACKDROP := LumurStoryStageLayout.LAYER_BACKDROP
const LAYER_CHARACTER := LumurStoryStageLayout.LAYER_CHARACTER
const LAYER_CLIP := LumurStoryStageLayout.LAYER_CLIP
const LAYER_CAPTION := LumurStoryStageLayout.LAYER_CAPTION
const LAYER_AMBIENCE := LumurStoryStageLayout.LAYER_AMBIENCE


func get_scenario() -> Dictionary:
	return {}


func snapshot(time_s: float = 0.0) -> Dictionary:
	## Returns {layer_name: {color: Color, texture: Texture2D|null, meta: Dictionary}}
	return {}


func list_layers() -> PackedStringArray:
	return PackedStringArray(LumurStoryStageLayout.CANONICAL_LAYERS)
