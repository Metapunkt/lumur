extends Node

## Bundled footstep-ripples app (PRD-003 REQ-003-015).
## Loads room assets, paints a calm floor base, and stamps ripples from the
## filtered input bus (manifest declares ``footstep`` + ``shares: ["floor"]``).

const APP_ID := "lumur.ripples"
const MANIFEST_PATH := "res://apps/ripples/lumur.app.json"


func _ready() -> void:
	var runtime := $Runtime as LumurRoomRuntime
	if runtime == null:
		push_error("ripple_app: missing Runtime")
		return
	var assets := LumurDefaultAssets.resolve()
	var err := runtime.load_room(assets)
	if err != OK:
		push_warning("ripple_app: could not load %s (err %s)" % [assets, err])
		return

	runtime.install_app(ProjectSettings.globalize_path(MANIFEST_PATH))
	var launched := runtime.launch_app(APP_ID)
	if launched.is_empty():
		# Overlay path: paint may already own the floor in multi-app hosts.
		push_warning("ripple_app: launch returned empty — check fit/ownership")

	# Calm floor base when we are the sole occupant; overlays still stamp.
	if runtime.paint != null and runtime.surface("floor") != null:
		if runtime.compositor != null:
			var floor_id := runtime.floor_plane_id()
			var owns_base := false
			var table: Dictionary = runtime.compositor.ownership_table()
			if table.has(floor_id):
				owns_base = str(table[floor_id].get("base_app_id", "")) == APP_ID
			if owns_base or table.is_empty():
				runtime.paint_surface("floor", Color(0.12, 0.18, 0.22))

	var receiver := runtime.get_node_or_null("EventReceiver") as LumurEventReceiver
	if receiver != null:
		runtime.bind_event_receiver(receiver)

	# Prefer filtered bus over raw UDP for the app contract.
	if runtime.app_manifest == null:
		runtime.load_app_manifest(MANIFEST_PATH)
	if runtime.input_bus != null and runtime.app_manifest != null:
		runtime.register_app_inputs(runtime.app_manifest, runtime.last_fit)
		runtime.subscribe_app_input(APP_ID, "footstep")
		if not runtime.input_bus.app_event.is_connected(_on_app_event):
			runtime.input_bus.app_event.connect(_on_app_event)


func _on_app_event(app_id: String, event: Dictionary) -> void:
	if app_id != APP_ID:
		return
	if str(event.get("type", "")) != "footstep":
		return
	var ripples := $Runtime/Ripples as LumurRippleLayer
	if ripples == null:
		return
	var pf: Array = event.get("position_floor", [0.0, 0.0])
	if pf.size() < 2:
		return
	ripples.inject_footstep(Vector2(float(pf[0]), float(pf[1])))
