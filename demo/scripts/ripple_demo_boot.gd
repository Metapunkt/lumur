extends Node

## Boot the ripple demo: load Godot paint assets from LUMUR_GODOT_ASSETS
## (or a default), paint a calm floor, and listen for footstep UDP events.

func _ready() -> void:
	var assets := OS.get_environment("LUMUR_GODOT_ASSETS")
	if assets.is_empty():
		assets = "/tmp/sim-room/godot"
	var runtime := $Runtime as LumurRoomRuntime
	var err := runtime.load_room(assets)
	if err != OK:
		push_warning("ripple_demo: could not load %s (err %s)" % [assets, err])
		return
	runtime.paint_surface("floor", Color(0.12, 0.18, 0.22))
	for i in range(1, 6):
		var wall := runtime.surface("wall_%d" % i)
		if wall == null:
			break
		runtime.paint_surface("wall_%d" % i, Color(0.18, 0.22, 0.28))
	var receiver := runtime.get_node_or_null("EventReceiver") as LumurEventReceiver
	if receiver != null:
		runtime.bind_event_receiver(receiver)
