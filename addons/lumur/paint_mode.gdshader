shader_type canvas_item;

/* Correspondence-based paint: projector pixel → surface_id via exported maps.
 * Lookup RGB encodes normalised camera UV + valid (distortion baked in).
 * Avoid early `return` in fragment — dummy/compat backends reject it.
 *
 * Modes (mode_tex R * 255): 0 solid, 1 texture (surface_textures array), 2 pulse.
 */

uniform sampler2D surface_id_tex : filter_nearest, repeat_disable;
uniform sampler2D confidence_tex : filter_nearest, repeat_disable;
uniform sampler2D lookup_tex : filter_nearest, repeat_disable;
uniform sampler2D palette_tex : filter_nearest, repeat_disable;
uniform sampler2D mode_tex : filter_nearest, repeat_disable; // R: mode id/255
uniform sampler2DArray surface_textures : filter_linear, repeat_disable;
uniform sampler2D ripple_tex : filter_linear, repeat_disable;
uniform float confidence_threshold = 0.05;
uniform float time_seconds = 0.0;
uniform vec4 clear_color = vec4(0.0, 0.0, 0.0, 1.0);
uniform float ripple_floor_id = -1.0;
uniform bool ripple_enabled = false;
uniform bool textures_enabled = false;

const float MODE_TEXTURE = 1.0;
const float MODE_PULSE = 2.0;

void fragment() {
	vec2 uv = UV;
	float sid = texture(surface_id_tex, uv).r * 255.0;
	float conf = texture(confidence_tex, uv).r;
	vec4 look = texture(lookup_tex, uv);
	bool ok = conf >= confidence_threshold && look.b > 0.5 && sid >= 0.5;

	float palette_u = (sid + 0.5) / 256.0;
	vec4 base = texture(palette_tex, vec2(palette_u, 0.5));
	float mode = texture(mode_tex, vec2(palette_u, 0.5)).r * 255.0;

	vec3 lit = base.rgb;
	if (textures_enabled && mode > MODE_TEXTURE - 0.5 && mode < MODE_TEXTURE + 0.5) {
		vec4 sampled = texture(surface_textures, vec3(look.rg, sid));
		lit = sampled.rgb * base.rgb;
	} else if (mode > MODE_PULSE - 0.5) {
		float phase = sin(6.2831853 * time_seconds + (look.r + look.g) * 3.1415926);
		float amp = 0.55 + 0.45 * phase;
		lit = base.rgb * amp;
	}

	vec4 ripple = texture(ripple_tex, uv);
	bool on_floor = ripple_enabled && ripple_floor_id >= 0.5 && abs(sid - ripple_floor_id) < 0.5;
	vec3 with_ripple = mix(lit, ripple.rgb, on_floor ? ripple.a : 0.0);

	COLOR = ok ? vec4(with_ripple, 1.0) : clear_color;
}
