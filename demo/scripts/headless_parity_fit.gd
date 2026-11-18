extends SceneTree

## Parity harness: fit a manifest against godot/ assets and print JSON.
## Shared fixtures under companion/tests/fixtures/parity/ drive Python + Godot.
##
## Usage:
##   godot --headless --path . \
##     --script res://demo/scripts/headless_parity_fit.gd \
##     -- --assets=/path/to/room/godot \
##        --manifest=/path/to/lumur.app.json \
##        --out=/tmp/fit.json

func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var args := _parse_args()
	var assets_path: String = str(args.get("assets", ""))
	var manifest_path: String = str(args.get("manifest", ""))
	var out_path: String = str(args.get("out", ""))
	if assets_path.is_empty() or manifest_path.is_empty():
		push_error("headless_parity_fit: need --assets= and --manifest=")
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
		err = manifest.load_file(manifest_path)
	if err != OK:
		push_error("manifest load failed: %s (%s)" % [manifest_path, manifest.last_error])
		quit(4)
		return

	var fitter := LumurAppFit.new()
	var result: Dictionary = fitter.fit(manifest, package)
	var text := JSON.stringify(result)
	print(text)
	if not out_path.is_empty():
		var f := FileAccess.open(out_path, FileAccess.WRITE)
		if f == null:
			push_error("cannot write %s" % out_path)
			quit(5)
			return
		f.store_string(text)
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
