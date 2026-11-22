// Peeling paint (cottage siding, corrugated roofs): the same maths as the Blender materials
// built by cs_environment_elements/core/paint.py (C_cottage_lap_paint, C_cottage_planks_paint_v,
// C_cottage_roof_paint). One ShaderMaterial per surface type serves every building:
// the colour and the peeling come from the mesh's vertex colour (glTF COLOR_0):
//   COLOR.rgb = paint colour, COLOR.a = peeling (0 fresh .. 1 bare)
// Opaque, no alpha test: the GPU keeps its early depth test.
shader_type spatial;
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D under_tex : source_color, filter_linear_mipmap_anisotropic, repeat_enable;  // <set>_diff
uniform sampler2D paint_data : hint_default_white, filter_linear_mipmap, repeat_enable;      // <set>_paint (R last, G fade, B dirt)
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic, repeat_enable; // <set>_nor (OpenGL)
uniform sampler2D rough_tex : hint_roughness_r, filter_linear_mipmap, repeat_enable;        // <set>_rough
// The mesh UVs are in metres; these match the Blender material's Mapping node.
uniform float uv_scale = 0.694444;      // repeats per metre: siding 1/1.44, roof 0.5
uniform bool rotate_90 = false;         // upright planks (C_cottage_planks_paint_v)
uniform float chalk_mul = 0.55;         // the faded colour: (sqrt(c) * chalk_mul + chalk_add)^2
uniform float chalk_add = 0.4;          //   siding 0.55 / 0.4, roof 0.6 / 0.35
uniform float paint_roughness : hint_range(0.0, 1.0) = 0.68;   // siding 0.68, roof 0.55
uniform float dirt_gain = 1.0;          // siding 1.0, roof 1.15
uniform float edge_softness : hint_range(0.0, 0.2) = 0.03;
uniform float rim_width : hint_range(0.0, 0.3) = 0.06;
// Detiling: each building gets its own shift (from where it stands) and the wear is read a
// second time, turned and smaller, so the texture never shows the same chips twice in a row.
uniform float detile_strength : hint_range(0.0, 1.0) = 0.35;
uniform float detile_scale = 0.41;
uniform float detile_angle = 0.645772;   // 37 degrees
uniform float detile_shift = 7.0;
// Wear zones: wear_zones.png stretched over zone_size metres, so the damage gathers in one or
// two areas of a building. zone_strength: siding 0.5, roof 0.7.
uniform sampler2D wear_zones : hint_default_white, filter_linear, repeat_enable;   // wear_zones.png
uniform float zone_size = 16.0;
uniform float zone_strength : hint_range(0.0, 1.0) = 0.5;
// Roofs: rust streaks (paint_data alpha), shown mostly inside the wear zones. Siding: 0.
uniform float rust_amount : hint_range(0.0, 1.0) = 0.0;
uniform vec3 rust_colour : source_color = vec3(0.46, 0.25, 0.12);
uniform bool vertex_color_is_srgb = false;   // tick if the paint looks washed out

vec3 cs_srgb_to_linear(vec3 c) {
	return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}

vec3 cs_hash3(vec2 p) {
	vec3 q = vec3(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)), dot(p, vec2(419.2, 371.9)));
	return fract(sin(q) * 43758.5453);
}

void fragment() {
	vec3 rnd = cs_hash3(NODE_POSITION_WORLD.xz);          // per building (LODs share it)
	vec2 uv = UV * uv_scale;
	if (rotate_90) {
		uv = vec2(-uv.y, uv.x);
	}
	uv.x += rnd.x * detile_shift;                         // along the boards
	float c = cos(detile_angle), s = sin(detile_angle);
	vec2 uv2 = mat2(vec2(c, s), vec2(-s, c)) * (uv * detile_scale) + rnd.yz * 5.0;

	vec3 under = texture(under_tex, uv).rgb;
	vec4 data = texture(paint_data, uv);
	float last = clamp(data.r + detile_strength * (texture(paint_data, uv2).r - 0.5), 0.04, 0.96);
	vec3 colour = vertex_color_is_srgb ? cs_srgb_to_linear(COLOR.rgb) : COLOR.rgb;
	float z = texture(wear_zones, UV / zone_size + rnd.yz).r;
	// worse inside a zone, better outside; still fresh at 0 and bare at 1
	float peel = clamp(COLOR.a + COLOR.a * (1.0 - COLOR.a) * zone_strength * (z - 0.5) * 4.0, 0.0, 1.0);

	float paint = smoothstep(peel - edge_softness, peel + edge_softness, last);   // 1 where paint is left
	float rim = 1.0 - smoothstep(0.0, rim_width, abs(last - peel));             // dirty edge round each flake
	vec3 chalk_s = sqrt(colour) * chalk_mul + chalk_add;
	vec3 faded = mix(colour, chalk_s * chalk_s, data.g);
	vec3 coat = faded * data.b * dirt_gain * (1.0 - 0.18 * rim);

	vec3 albedo = mix(under, coat, paint);
	float roughness = mix(texture(rough_tex, uv).r, paint_roughness, paint);
	float rust = rust_amount * min(data.a * (0.3 + 1.7 * smoothstep(0.35, 0.9, z)), 1.0) * (1.0 - 0.7 * paint);
	ALBEDO = mix(albedo, rust_colour, rust);
	ROUGHNESS = mix(roughness, 0.85, rust);
	vec3 n = texture(normal_tex, uv).rgb;
	if (rotate_90) {
		n.xy = vec2(n.y, 1.0 - n.x);    // the texture is turned: turn its normals back into the mesh's frame
	}
	NORMAL_MAP = n;
}
