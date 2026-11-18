class_name LumurAppFit
extends RefCounted

## Bind a ``lumur.app`` manifest to surfaces from a loaded ``LumurRoomPackage``
## (ADR 0018 allocation for one app). Uses paint-export ``width_m`` /
## ``mean_confidence`` when present.

var last_error: String = ""
var last_unmet: Array = []


func fit(
	manifest: LumurAppManifest,
	package: LumurRoomPackage,
	exclusive_owned: Array = [],
	share_keys: PackedStringArray = PackedStringArray()
) -> Dictionary:
	## Returns ``{ok, app_id, bindings, unmet}``. On required failure ``ok`` is
	## false and ``last_error`` is set; bindings collected so far are included.
	## ``share_keys`` (manifest shares) may bind surfaces already base-owned.
	last_error = ""
	last_unmet = []
	var owned := {}
	for oid in exclusive_owned:
		owned[int(oid)] = true
	var shares := {}
	for sk in share_keys:
		shares[str(sk)] = true
	var used := {}
	var bindings := {}
	var unmet: Array = []
	var surfaces: Array = _allocatable_surfaces(package)

	for req_v in manifest.surface_requests():
		var req: Dictionary = req_v
		var key := str(req.get("key", ""))
		var role := str(req.get("role", ""))
		var required := bool(req.get("required", true))
		var count := int(req.get("count", 1))
		var min_width = req.get("min_width_m", null)
		var min_conf = req.get("min_confidence", null)
		var constraints := {
			"min_width_m": min_width,
			"min_confidence": min_conf,
			"count": count,
			"required": required,
		}
		var skip_owned := not shares.has(key)
		var assigned: Array = []
		for _i in range(count):
			var candidates: Array = []
			for s in surfaces:
				var sid := int(s.get("id", -1))
				if used.has(sid):
					continue
				if skip_owned and owned.has(sid):
					continue
				if not _role_matches(s, role):
					continue
				if not _passes_constraints(s, min_width, min_conf):
					continue
				candidates.append(s)
			candidates.sort_custom(func(a, b):
				var wa := float(a.get("width_m", 0.0))
				var wb := float(b.get("width_m", 0.0))
				if wa == wb:
					return int(a.get("id", 0)) < int(b.get("id", 0))
				return wa > wb
			)
			if candidates.is_empty():
				break
			var pick: Dictionary = candidates[0]
			assigned.append(pick)
			used[int(pick.get("id", -1))] = true

		if assigned.size() < count:
			var entry := {
				"key": key,
				"role": role,
				"reason": "unmet_surface",
				"constraints": constraints,
			}
			unmet.append(entry)
			last_unmet.append(entry)
			if required:
				last_error = "unmet_surface key=%s role=%s" % [key, role]
				return {
					"ok": false,
					"app_id": manifest.app_id(),
					"bindings": bindings,
					"unmet": unmet,
				}
			bindings[key] = {
				"key": key,
				"role_requested": role,
				"surface_id": null,
				"roles": [],
				"width_m": null,
				"mean_confidence": null,
				"optional_unmet": true,
			}
			continue

		for i in range(assigned.size()):
			var surf: Dictionary = assigned[i]
			var bind_key := key if i == 0 else "%s#%d" % [key, i + 1]
			bindings[bind_key] = {
				"key": bind_key,
				"role_requested": role,
				"surface_id": int(surf.get("id", -1)),
				"roles": surf.get("roles", []),
				"width_m": float(surf.get("width_m", 0.0)),
				"mean_confidence": float(surf.get("mean_confidence", 0.0)),
				"optional_unmet": false,
			}

	return {
		"ok": true,
		"app_id": manifest.app_id(),
		"bindings": bindings,
		"unmet": unmet,
	}


func _allocatable_surfaces(package: LumurRoomPackage) -> Array:
	var out: Array = []
	for s in package.list_surfaces():
		if typeof(s) != TYPE_DICTIONARY:
			continue
		if str(s.get("kind", "")) == "non_planar":
			continue
		out.append(s)
	return out


func _role_matches(surface: Dictionary, role: String) -> bool:
	var role_l := role.strip_edges()
	if role_l.is_empty():
		return false
	var roles: Array = surface.get("roles", [])
	if roles.has(role_l) or str(surface.get("label", "")) == role_l:
		return true
	if role_l == "floor":
		return str(surface.get("kind", "")) == "floor" or roles.has("floor")
	if role_l == "wall":
		if str(surface.get("kind", "")) == "wall":
			return true
		for r in roles:
			var rs := str(r)
			if rs == "wall" or rs.begins_with("wall_"):
				return true
	return false


func _passes_constraints(surface: Dictionary, min_width, min_conf) -> bool:
	if min_width != null and float(surface.get("width_m", 0.0)) + 1e-9 < float(min_width):
		return false
	if min_conf != null and float(surface.get("mean_confidence", 0.0)) + 1e-9 < float(min_conf):
		return false
	return true
