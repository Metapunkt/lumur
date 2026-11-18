extends SceneTree

## Headless check: per-app input allowlist on LumurAppInputBus (PRD-003 slice 2).
##
## Usage:
##   godot --headless --path . \
##     --script res://demo/scripts/headless_app_input.gd \
##     -- --manifest=res://apps/examples/ripples/lumur.app.json

func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var manifest_path: String = str(
		args.get("manifest", "res://apps/examples/ripples/lumur.app.json")
	)

	var manifest := LumurAppManifest.new()
	var err := manifest.load_file(ProjectSettings.globalize_path(manifest_path))
	if err != OK:
		err = manifest.load_file(manifest_path)
	if err != OK:
		push_error("manifest load failed: %s (%s)" % [manifest_path, manifest.last_error])
		quit(2)
		return

	var bus := LumurAppInputBus.new()
	var fit := {
		"ok": true,
		"bindings": {
			"floor": {
				"key": "floor",
				"role_requested": "floor",
				"surface_id": 0,
				"roles": ["floor"],
			}
		},
	}
	bus.register_app(manifest, fit)

	if not bus.subscribe(manifest.app_id(), "footstep"):
		push_error("expected footstep subscription to succeed")
		quit(3)
		return
	if bus.subscribe(manifest.app_id(), "zone_enter"):
		push_error("expected zone_enter subscription to be refused")
		quit(4)
		return

	bus.inject({
		"type": "footstep",
		"person_id": 1,
		"foot": "left",
		"position_floor": [0.2, 0.3],
		"position_room": [0.2, 0.0, 0.3],
		"timestamp": 1.0,
		"confidence": 1.0,
	})
	bus.inject({
		"type": "zone_enter",
		"person_id": 1,
		"zone_id": "left",
		"position_floor": [-0.5, 0.4],
		"timestamp": 1.1,
	})
	bus.inject({
		"type": "presence",
		"person_ids": [1],
		"count": 1,
		"timestamp": 1.2,
	})

	var stream: Array = bus.stream_for(manifest.app_id())
	if stream.size() != 1:
		push_error("expected exactly one delivered event, got %d" % stream.size())
		quit(5)
		return
	var ev: Dictionary = stream[0]
	if str(ev.get("type", "")) != "footstep":
		push_error("expected footstep, got %s" % ev.get("type"))
		quit(6)
		return
	if int(ev.get("surface_id", -1)) != 0:
		push_error("expected fitted surface_id 0")
		quit(7)
		return
	if not ev.has("position_surface"):
		push_error("expected position_surface on fitted delivery")
		quit(8)
		return

	var refused: Array = bus.refused_log()
	if refused.is_empty():
		push_error("expected refused subscription log entry")
		quit(9)
		return

	print(JSON.stringify({
		"ok": true,
		"delivered": stream,
		"refused": refused,
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
