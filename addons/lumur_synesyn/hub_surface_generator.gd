class_name LumurSynesynHubSurfaceGenerator
extends RefCounted

## Godot-side Hub provider registration (PRD-002 slice 2).
##
## Slice 2 keeps Hub HTTP in the optional Python package ``lumur_synesyn``
## (``lumur-generate-synesyn``). Godot consumes finished textures from the room
## package through paint mode — same async contract as standalone ComfyUI
## (ADR 0008 / 0016). When ``synesyn_core`` is present, callers may also wire
## ``HubSubstrateClient`` themselves; this class does not import it so Lumur
## still loads without Synesyn.

signal generation_finished(surface_key: Variant, ok: bool, meta: Dictionary)

const PROVIDER_ID := "synesyn_hub"
const PROVIDER_PACKAGE := "package"


var provider_id: String = PROVIDER_ID
var paint: LumurPaintMode
var config: LumurSynesynHubConfig = LumurSynesynHubConfig.new()


func configure_hub(hub_config: LumurSynesynHubConfig) -> void:
	config = hub_config
	provider_id = PROVIDER_ID


func configure_package(paint_mode: LumurPaintMode) -> void:
	## Apply textures already written by ``lumur-generate-synesyn``.
	provider_id = PROVIDER_PACKAGE
	paint = paint_mode


func request_surface(_key: Variant, _opts: Dictionary = {}) -> void:
	## Non-blocking. Package provider loads generated textures off the critical path.
	## Live Hub submit from Godot is intentionally deferred to the companion CLI /
	## optional synesyn_core client so the projector never awaits HTTP.
	if provider_id == PROVIDER_PACKAGE and paint != null:
		var applied := paint.apply_generated_from_package()
		generation_finished.emit(
			_key,
			applied > 0,
			{"applied": applied, "provider": PROVIDER_ID, "mode": "package"}
		)
		return
	generation_finished.emit(
		_key,
		false,
		{
			"provider": PROVIDER_ID,
			"hub": config.to_dict(),
			"hint": "run lumur-generate-synesyn then configure_package / apply_generated_from_package",
		}
	)
