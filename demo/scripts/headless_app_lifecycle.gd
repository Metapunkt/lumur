extends SceneTree

## Headless check: compositor ownership + lifecycle pause (PRD-003 slice 3).
##
## Usage:
##   godot --headless --path . \
##     --script res://demo/scripts/headless_app_lifecycle.gd \
##     -- --assets=/tmp/sim-room/godot

func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var assets: String = str(args.get("assets", ""))
	if assets.is_empty():
		push_error("pass --assets=/path/to/godot paint export")
		quit(2)
		return

	var runtime := LumurRoomRuntime.new()
	var err := runtime.load_room(assets)
	if err != OK:
		push_error("load_room failed")
		quit(3)
		return

	var floor_doc := {
		"schema": "lumur.app",
		"schema_version": "1.0",
		"id": "test.floor",
		"name": "Floor",
		"version": "0.0.1",
		"scene": "res://apps/examples/ripples/ripple_app.tscn",
		"surfaces": [{"key": "floor", "role": "floor", "min_confidence": 0.05, "required": true}],
		"inputs": ["footstep"],
		"generation": false,
		"bridge": null,
	}
	var wall_doc := {
		"schema": "lumur.app",
		"schema_version": "1.0",
		"id": "test.wall",
		"name": "Wall",
		"version": "0.0.1",
		"scene": "res://apps/examples/wall_panel/wall_panel_app.tscn",
		"surfaces": [{"key": "panel", "role": "wall", "min_width_m": 0.5, "required": false}],
		"inputs": [],
		"generation": false,
		"bridge": null,
	}

	runtime.lifecycle.install_document(floor_doc)
	runtime.lifecycle.install_document(wall_doc)
	var launched := runtime.lifecycle.launch("test.floor")
	if launched.is_empty() or str(launched.get("state", "")) != "running":
		push_error("expected floor app running")
		quit(4)
		return

	runtime.input_bus.inject({
		"type": "footstep",
		"person_id": 1,
		"foot": "left",
		"position_floor": [0.1, 0.2],
		"timestamp": 1.0,
	})
	if runtime.input_bus.stream_for("test.floor").size() != 1:
		push_error("expected footstep delivery while running")
		quit(5)
		return

	runtime.lifecycle.pause("test.floor")
	runtime.input_bus.inject({
		"type": "footstep",
		"person_id": 1,
		"foot": "right",
		"position_floor": [0.2, 0.3],
		"timestamp": 2.0,
	})
	if runtime.input_bus.stream_for("test.floor").size() != 1:
		push_error("paused app must not receive events")
		quit(6)
		return

	var listed: Array = runtime.launcher.list_startable()
	if listed.size() < 2:
		push_error("launcher should list installed apps")
		quit(7)
		return

	print(JSON.stringify({
		"ok": true,
		"states": runtime.lifecycle.states(),
		"ownership": runtime.compositor.ownership_table(),
		"listed": listed.size(),
	}))
	quit(0)


func _parse_args() -> Dictionary:
	var out := {}
	for a in OS.get_cmdline_user_args():
		if not a.begins_with("--"):
			continue
		var body := a.substr(2)
		var eq := body.find("=")
		if eq < 0:
			out[body] = true
		else:
			out[body.substr(0, eq)] = body.substr(eq + 1)
	return out
