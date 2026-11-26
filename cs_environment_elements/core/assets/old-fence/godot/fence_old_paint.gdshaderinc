// Old wooden fence with peeling paint — shared by fence_old_paint.gdshader (boards, LOD0/LOD1)
// and fence_old_paint_card.gdshader (LOD2/LOD3 cards). Same maths as the Blender material
// C_fence_old_paint (cs_environment_elements/buildings/fence_paint.py + core/paint_nodes.py).
//
// Per fence, from the mesh's vertex colour (glTF COLOR_0, the Blender attribute "Paint"):
//   COLOR.rgb = paint colour, COLOR.a = peeling (0 fresh .. 1 bare wood)
// So one material serves every old fence, whatever its colour.
// UV2 (glTF TEXCOORD_1, the Blender UV layer "WearUV") is the fence in metres, U along the grain:
// the weather patches and the flakes (paint_lasting.gdshaderinc, copied from core/assets/godot/
// into the same folder) run on it, across neighbouring boards.

#include "paint_lasting.gdshaderinc"

uniform sampler2D wood_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;   // fence.png
uniform sampler2D paint_mask : hint_default_white, filter_linear_mipmap, repeat_enable;      // fence_paint_mask.png
uniform float edge_softness : hint_range(0.0, 0.2) = 0.03;   // width of the paint/wood boundary
uniform float rim_width : hint_range(0.0, 0.3) = 0.06;       // dirty edge round each flake
uniform float wood_roughness : hint_range(0.0, 1.0) = 0.88;
// Bare wood (under peeled paint, or never painted) times this: the timber cottages' old brown wood.
uniform vec3 peeled_wood_tint = vec3(0.40, 0.36, 0.284);
uniform float paint_roughness : hint_range(0.0, 1.0) = 0.6;
// Leave off for meshes exported by Blender's glTF exporter (COLOR_0 is linear). Turn on if
// the paint looks washed out (vertex colours that arrive as sRGB).
uniform bool vertex_color_is_srgb = false;

void fence_paint(vec2 uv, vec2 wear_uv, vec4 vcol, out vec3 albedo, out float rough, out float alpha) {
	vec4 wood = texture(wood_tex, uv);
	float cracks;
	float last = cs_paint_lasts(wear_uv, wear_uv / CS_FLAKE_SIZE, texture(paint_mask, uv).r, vec3(0.0),
			false, CS_W_BOARD_FENCE, cracks);
	vec3 colour = vertex_color_is_srgb ? cs_srgb_to_linear(vcol.rgb) : vcol.rgb;
	float peel = vcol.a;
	float soft = cs_edge(last, edge_softness);                                    // at least ~1 pixel: no shimmer
	float paint = smoothstep(peel - soft, peel + soft, last);                      // 1 where paint is left
	float rim = 1.0 - smoothstep(0.0, rim_width, abs(last - peel));
	float luma = dot(wood.rgb, vec3(0.2126, 0.7152, 0.0722));
	float grain = mix(1.0, clamp(luma * 2.5, 0.0, 1.0), 0.35);                      // wood shows through a little
	vec3 bare = wood.rgb * peeled_wood_tint;
	albedo = mix(bare, colour * grain * (1.0 - 0.18 * rim) * cs_crack(last, peel, cracks), paint);
	rough = mix(wood_roughness, paint_roughness, paint);
	alpha = wood.a;
}
