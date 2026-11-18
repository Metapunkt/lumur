extends Node

## Bridge-only Story Stage app (PRD-003 REQ-003-016).
## Ships inside ``lumur_synesyn``; core launcher omits it unless the bridge
## is enabled. Projects layers through existing paint mode.

const APP_ID := "lumur.synesyn.story_stage"
const MANIFEST_PATH := "res://addons/lumur_synesyn/apps/story_stage/lumur.app.json"

var _host: LumurStoryStageHost
var _projector: LumurStoryStageProjector


func _ready() -> void:
	var runtime := $Runtime as LumurRoomRuntime
	if runtime == null:
		push_error("story_stage_app: missing Runtime")
		return
	var assets := OS.get_environment("LUMUR_GODOT_ASSETS")
	if assets.is_empty():
		assets = "/tmp/sim-room/godot"
	var err := runtime.load_room(assets)
	if err != OK:
		push_warning("story_stage_app: could not load %s" % assets)
		return

	runtime.install_app(ProjectSettings.globalize_path(MANIFEST_PATH))
	var launched := runtime.launch_app(APP_ID)
	if launched.is_empty():
		push_warning("story_stage_app: launch failed")
		return

	_host = LumurStoryStageHost.new()
	_projector = $StoryStageProjector as LumurStoryStageProjector
	if _projector == null:
		_projector = LumurStoryStageProjector.new()
		_projector.name = "StoryStageProjector"
		add_child(_projector)
	var stub := LumurStubStoryStageLayerSource.new()
	_projector.configure(stub, runtime.paint, _host, runtime.package)
	_projector.runtime = runtime
	_projector.project_at(0.0)
