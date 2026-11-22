// Old wooden fence boards, rails, posts and gate leaves (LOD0, LOD1): opaque, no alpha test,
// so the GPU keeps its early depth test. Material name in the glTF: C_fence_old_paint.
shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

#include "fence_old_paint.gdshaderinc"

void fragment() {
	vec3 albedo;
	float rough;
	float alpha;
	fence_paint(UV, COLOR, albedo, rough, alpha);
	ALBEDO = albedo;
	ROUGHNESS = rough;
}
