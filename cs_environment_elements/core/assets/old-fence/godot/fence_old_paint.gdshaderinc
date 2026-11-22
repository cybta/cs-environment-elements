// Old wooden fence with peeling paint — shared by fence_old_paint.gdshader (boards, LOD0/LOD1)
// and fence_old_paint_card.gdshader (LOD2/LOD3 cards). Same maths as the Blender material
// C_fence_old_paint (cs_environment_elements/buildings/fence_paint.py).
//
// Per fence, from the mesh's vertex colour (glTF COLOR_0, the Blender attribute "Paint"):
//   COLOR.rgb = paint colour, COLOR.a = peeling (0 fresh .. 1 bare wood)
// So one material serves every old fence, whatever its colour.

uniform sampler2D wood_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;   // fence.png
uniform sampler2D paint_mask : hint_default_white, filter_linear_mipmap, repeat_enable;      // fence_paint_mask.png
uniform float edge_softness : hint_range(0.0, 0.2) = 0.03;   // width of the paint/wood boundary
uniform float wood_roughness : hint_range(0.0, 1.0) = 0.88;
uniform float paint_roughness : hint_range(0.0, 1.0) = 0.6;
// Leave off for meshes exported by Blender's glTF exporter (COLOR_0 is linear). Turn on if
// the paint looks washed out (vertex colours that arrive as sRGB).
uniform bool vertex_color_is_srgb = false;

vec3 cs_srgb_to_linear(vec3 c) {
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}

void fence_paint(vec2 uv, vec4 vcol, out vec3 albedo, out float rough, out float alpha) {
	vec4 wood = texture(wood_tex, uv);
	float mask = texture(paint_mask, uv).r;
	vec3 colour = vertex_color_is_srgb ? cs_srgb_to_linear(vcol.rgb) : vcol.rgb;
	float paint = smoothstep(vcol.a - edge_softness, vcol.a + edge_softness, mask);  // 1 where paint is left
	float luma = dot(wood.rgb, vec3(0.2126, 0.7152, 0.0722));
	float grain = mix(1.0, clamp(luma * 2.5, 0.0, 1.0), 0.35);                      // wood shows through a little
	albedo = mix(wood.rgb, colour * grain, paint);
	rough = mix(wood_roughness, paint_roughness, paint);
	alpha = wood.a;
}
