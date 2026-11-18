class_name LumurSurfaceGenerator
extends RefCounted

## Godot-side surface generator interface (ADR 0016).
##
## Slice 1 keeps ComfyUI HTTP in the Python companion. Godot consumes results
## asynchronously from the room package (``generated_textures``) so the
## projector path never awaits a provider. A future provider may wrap a
## companion bridge; the null provider is the safe default.

signal generation_finished(surface_key: Variant, ok: bool, meta: Dictionary)

const PROVIDER_NULL := "null"
const PROVIDER_PACKAGE := "package"


var provider_id: String = PROVIDER_NULL
var paint: LumurPaintMode


func configure_null() -> void:
	provider_id = PROVIDER_NULL


func configure_package(paint_mode: LumurPaintMode) -> void:
	## Apply textures already written by ``lumur-generate``.
	provider_id = PROVIDER_PACKAGE
	paint = paint_mode


func request_surface(_key: Variant, _opts: Dictionary = {}) -> void:
	## Non-blocking. Null provider finishes immediately with ok=false.
	## Package provider loads generated textures off the critical path.
	if provider_id == PROVIDER_PACKAGE and paint != null:
		var applied := paint.apply_generated_from_package()
		generation_finished.emit(_key, applied > 0, {"applied": applied, "provider": provider_id})
		return
	generation_finished.emit(_key, false, {"provider": PROVIDER_NULL})
