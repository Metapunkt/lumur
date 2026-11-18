class_name LumurSynesynHubConfig
extends RefCounted

## Hub URL + optional Bearer token for the Lumur↔Synesyn bridge.
## Never commit tokens. Prefer environment / local user config.

const ENV_HUB_URL := "LUMUR_SYNESYN_HUB_URL"
const ENV_HUB_TOKEN := "LUMUR_SYNESYN_HUB_TOKEN"
const ENV_HUB_AUTH := "LUMUR_SYNESYN_HUB_AUTH"


var hub_base_url: String = ""
var auth_token: String = ""
var auth_enabled: bool = false
var comfy_base_url: String = "http://127.0.0.1:8188"


func configure(
	url: String,
	token: String = "",
	enabled: bool = false,
	comfy_url: String = "http://127.0.0.1:8188"
) -> void:
	hub_base_url = url.strip_edges().rstrip("/")
	auth_token = token.strip_edges()
	auth_enabled = enabled or not auth_token.is_empty()
	comfy_base_url = comfy_url.strip_edges().rstrip("/")


func apply_env_overrides() -> void:
	## Best-effort: Godot cannot always read process env in exported builds.
	## Companion CLI uses the same variable names.
	var url := OS.get_environment(ENV_HUB_URL).strip_edges()
	if not url.is_empty():
		hub_base_url = url.rstrip("/")
	var token := OS.get_environment(ENV_HUB_TOKEN).strip_edges()
	if not token.is_empty():
		auth_token = token
	var auth := OS.get_environment(ENV_HUB_AUTH).strip_edges().to_lower()
	if auth in ["1", "true", "yes", "on"]:
		auth_enabled = true
	elif auth in ["0", "false", "no", "off"]:
		auth_enabled = false
	elif not auth_token.is_empty():
		auth_enabled = true


func to_dict() -> Dictionary:
	return {
		"hub_base_url": hub_base_url,
		"auth_enabled": auth_enabled,
		# Token intentionally omitted from serialised dumps by default.
		"comfy_base_url": comfy_base_url,
		"has_token": not auth_token.is_empty(),
	}


func bearer_header() -> String:
	if not auth_enabled or auth_token.is_empty():
		return ""
	return "Authorization: Bearer %s" % auth_token
