// Old wooden fence LOD2/LOD3 cards: one quad per run with the planks and their gaps cut
// out of fence.png's alpha (alpha scissor). Material name in the glTF: C_fence_old_paint_card.
shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

#include "fence_old_paint.gdshaderinc"

void fragment() {
	vec3 albedo;
	float rough;
	float alpha;
	fence_paint(UV, UV2, COLOR, albedo, rough, alpha);
	ALBEDO = albedo;
	ROUGHNESS = rough;
	ALPHA = alpha;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
}
