class_name LumurStoryStageHost
extends RefCounted

## Lumur-side Story Stage host seam (PRD-002 slice 3 / Synesyn ADR 0029).
##
## This class intentionally does **not** extend Synesyn ``StoryStageHost`` so
## ``addons/lumur`` and this bridge still load without ``story_stage`` /
## ``synesyn_core``. When those addons are present, hand an instance of this
## host (or a thin subclass) to ``stage.host`` before ``add_child`` — same
## contract as Synesyn's playback host.
##
## Audience steering (slice 4): presence / zone / gathering advance story state
## only when ``lumur_audience`` opts in (see ``LumurAudienceSteering``).

signal story_log_changed
signal voice_owner_changed(stage_owns_voice: bool)
signal phase_changed(phase: String)
signal ambience_event(event: Dictionary)
signal audience_steered(action: Dictionary)

var audience_steering: LumurAudienceSteering = LumurAudienceSteering.new()
var steered_actions: Array = []

const FEATURE_STORY_LOG_VIEW := &"story_log_view"
const FEATURE_LANDING := &"landing"
const FEATURE_SERVICES := &"services"
const FEATURE_NEW_STORY_LOG := &"new_story_log"
const FEATURE_LOAD_STORY_LOG := &"load_story_log"
const FEATURE_RENDER := &"render"
const FEATURE_MODEL_CONTROLS := &"model_controls"
const FEATURE_DUAL_WINDOW := &"dual_window"
const FEATURE_SAVE_RECORDINGS := &"save_recordings"
const FEATURE_TYPED_INPUT := &"typed_input"
## Optional Synesyn-side flag if/when Story Stage grows a surface-mapping
## capability declaration (see PR Synesyn touchpoints). Not required today.
const FEATURE_LUMUR_SURFACES := &"lumur_surfaces"

var scenario: Dictionary = {}
var story_log: Array = []
var layout: LumurStoryStageLayout = LumurStoryStageLayout.new()
var _granted: Dictionary = {}
var _stage_voice_owned: bool = true


func set_scenario(next: Dictionary) -> void:
	scenario = next.duplicate(true)
	layout = LumurStoryStageLayout.from_scenario(scenario)
	audience_steering.host = self
	audience_steering.configure_from_scenario(scenario)
	steered_actions.clear()


func audience_steering_enabled() -> bool:
	return audience_steering.enabled


func process_audience_event(event: Dictionary) -> Array:
	return audience_steering.process_event(event)


func tick_audience(timestamp: float) -> Array:
	return audience_steering.tick(timestamp)


func apply_audience_action(action: Dictionary) -> void:
	## Called by LumurAudienceSteering when opted in.
	steered_actions.append(action)
	audience_steered.emit(action)
	var kind := str(action.get("kind", ""))
	if kind == "choose_option":
		var label := str(action.get("option_label", "option:%s" % str(action.get("option_index", 0))))
		append_story_log_entry({
			"sender": "_audience",
			"message": label,
			"timestamp_us": int(float(action.get("timestamp", 0.0)) * 1000000.0),
		})
	elif kind == "advance_beat":
		phase_changed.emit("beat_%d" % steered_actions.size())
	elif kind == "append_log" and action.has("entry"):
		append_story_log_entry(action["entry"])


func get_scenario() -> Dictionary:
	return scenario


func get_layout() -> LumurStoryStageLayout:
	return layout


func get_story_log_entries() -> Array:
	return story_log


func set_story_log_entries(entries: Array) -> void:
	story_log = entries.duplicate(true)
	story_log_changed.emit()


func append_story_log_entry(entry: Dictionary) -> void:
	story_log.append(entry)
	story_log_changed.emit()


func plays_existing_log() -> bool:
	return true


func granted_capabilities() -> Dictionary:
	return _granted.duplicate(true)


func set_granted_capabilities(caps: Dictionary) -> void:
	_granted = caps.duplicate(true)


func supports(feature: StringName) -> bool:
	## Declare surface-mapping support only. ScenSyn-only UI features stay off.
	return feature == FEATURE_LUMUR_SURFACES


func stage_owns_voice() -> bool:
	return _stage_voice_owned


func set_stage_owns_voice(owns: bool) -> void:
	_stage_voice_owned = owns
	voice_owner_changed.emit(owns)


func get_default_background_name() -> String:
	var name := str(scenario.get("default_background", ""))
	if name.to_lower().ends_with(".png"):
		name = name.substr(0, name.length() - 4)
	return name


func has_session() -> bool:
	return false


func commit_local_line(_sender: String, _text: String) -> bool:
	return false


func get_local_speaker_name(_peer_id: int) -> String:
	return ""


func get_local_character_name() -> String:
	return ""


func load_story_log(_path: String) -> void:
	pass


func get_story_log_dir() -> String:
	return OS.get_user_data_dir()


func get_opening_welcome_text() -> String:
	return ""


func mark_opening_spoken_on_stage() -> void:
	pass


func opening_was_spoken() -> bool:
	return true


func is_ai_busy() -> bool:
	return false


func attach_session_services(_stage: Node) -> void:
	pass


func populate_settings(_stage: Node) -> void:
	pass


func navigate(_stage: Node, _target: String) -> void:
	pass


func request_render(_stage: Node, _kind: String) -> void:
	pass


func get_sprite_roots() -> Array:
	return []


func get_scenario_art_dir() -> String:
	return ""


func get_backgrounds_dir() -> String:
	return ""


func forward_ambience_event(event: Dictionary) -> void:
	## Presence / footstep may drive ambience and PRD-001 ripples (REQ-002-012).
	## Story advancement is gated by ``lumur_audience`` via audience_steering.
	ambience_event.emit(event)


func load_story_log_entries(entries: Array) -> void:
	## Playback host pattern (Synesyn StoryLogPlaybackHost analogue).
	set_story_log_entries(entries)


func ignore_unknown_scenario_sections() -> bool:
	## Documented contract: layout reader already ignores unknown keys.
	return true
