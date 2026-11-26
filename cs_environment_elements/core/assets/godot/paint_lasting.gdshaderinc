// How long the paint lasts at each spot: core/paint_nodes.py (Blender) in GLSL, shared by
// peel_paint.gdshader (cottages) and ../old-fence/godot/fence_old_paint.gdshaderinc (fences).
//
//   last = mix(0.04, 0.96, smoothstep(D_LO, D_HI, W_PATCH * patches + W_FLAKE * flakes + w_board * board))
//   patches  wear_zones.png read twice: at PATCH_A metres, and turned PATCH_ROT at PATCH_B metres
//            (sizes that never line up, so the big weather patches do not repeat)
//   flakes   paint_flakes.png over FLAKE_SIZE metres: R long flakes along the grain (wood),
//            B round flakes (metal); G the cracks (1 none, 0 a crack)
//   board    the surface's own map (siding / roof _paint R, the fence's peel mask)
// Keep the constants equal to core/paint_nodes.py.

uniform sampler2D cs_wear_zones : hint_default_white, filter_linear, repeat_enable;          // wear_zones.png
uniform sampler2D cs_paint_flakes : hint_default_white, filter_linear_mipmap, repeat_enable;  // paint_flakes.png

const float CS_PATCH_A = 2.7;
const float CS_PATCH_B = 6.3;
const float CS_PATCH_ROT = 1.0995574;   // 63 degrees
const float CS_PATCH_MIX = 0.6;
const float CS_FLAKE_SIZE = 3.0;
const float CS_W_PATCH = 0.72;
const float CS_W_FLAKE = 0.21;
const float CS_W_BOARD = 0.07;
const float CS_W_BOARD_FENCE = 0.025;
const float CS_D_LO = 0.15;
const float CS_D_HI = 0.85;
const float CS_CRACK_REACH = 0.2;
const float CS_CRACK_DARK = 0.4;

vec3 cs_srgb_to_linear(vec3 c) {
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}

// uv_m: the surface in metres; flake_uv: in flake tiles, U along the grain; rnd: per object (or 0)
float cs_paint_lasts(vec2 uv_m, vec2 flake_uv, float board, vec3 rnd, bool is_metal, float w_board,
		out float cracks) {
	float za = texture(cs_wear_zones, uv_m / CS_PATCH_A + rnd.yz).r;
	vec2 b = uv_m / CS_PATCH_B;
	float c = cos(CS_PATCH_ROT), s = sin(CS_PATCH_ROT);
	float zb = texture(cs_wear_zones, vec2(b.x * c - b.y * s, b.x * s + b.y * c) + rnd.zx).r;
	float patches = mix(za, zb, 1.0 - CS_PATCH_MIX);
	vec3 fl = texture(cs_paint_flakes, flake_uv).rgb;
	cracks = fl.g;
	float d = CS_W_PATCH * patches + CS_W_FLAKE * (is_metal ? fl.b : fl.r) + w_board * board
			+ (CS_W_BOARD - w_board) * 0.5;
	return mix(0.04, 0.96, smoothstep(CS_D_LO, CS_D_HI, d));
}

// Width of the paint / bare edge: the material's softness, widened to about a pixel where the pattern is
// finer than the screen (a hard threshold would shimmer when the camera moves, with no AA on). Fragment only.
float cs_edge(float last, float softness) {
	return max(softness, 0.75 * fwidth(last));
}

// Darkening of the paint by its cracks, strongest just before it flakes off
float cs_crack(float last, float peel, float cracks) {
	float near = 1.0 - smoothstep(0.0, CS_CRACK_REACH, last - peel);
	return 1.0 - CS_CRACK_DARK * near * (1.0 - cracks);
}
