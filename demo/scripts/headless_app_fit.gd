extends SceneTree

## Headless validate + fit a ``lumur.app`` manifest against exported godot/ assets.
##
## Usage:
##   godot --headless --path . \
##     --script res://demo/scripts/headless_app_fit.gd \
##     -- --assets=/path/to/room/godot \
##        --manifest=res://apps/examples/ripples/lumur.app.json \
##        --expect=ok

func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var assets_path: String = str(args.get("assets", ""))
	var manifest_path: String = str(args.get("manifest", "res://apps/examples/ripples/lumur.app.json"))
	var expect: String = str(args.get("expect", "ok"))
	if assets_path.is_empty():
		push_error("headless_app_fit: missing --assets=/path/to/godot")
		quit(2)
		return

	var package := LumurRoomPackage.new()
	var err := package.load_godot_dir(assets_path)
	if err != OK:
		push_error("failed to load assets: %s" % assets_path)
		quit(3)
		return

	var manifest := LumurAppManifest.new()
	err = manifest.load_file(ProjectSettings.globalize_path(manifest_path))
	if err != OK:
		# Also try as an absolute / relative filesystem path.
		err = manifest.load_file(manifest_path)
	if err != OK:
		push_error("manifest load failed: %s (%s)" % [manifest_path, manifest.last_error])
		quit(4)
		return

	var fitter := LumurAppFit.new()
	var result: Dictionary = fitter.fit(manifest, package)
	print(JSON.stringify(result))
	var ok := bool(result.get("ok", false))
	if expect == "ok" and not ok:
		push_error("expected ok fit, got unmet: %s" % str(result.get("unmet")))
		quit(5)
		return
	if expect == "fail" and ok:
		push_error("expected fail fit, got ok")
		quit(6)
		return
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
