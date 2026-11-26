# Peeling paint in Godot 4 (cottage siding and roofs)

The painted cottage's siding and every cottage's corrugated roof use **one material per
surface type**, whatever the colour. The paint colour and how much has peeled off travel
on the mesh as its vertex colour (glTF `COLOR_0`): RGB = colour, A = peeling (0 fresh,
1 bare). On a cottage the roof faces carry the roof paint, everything else the siding
paint. (The old fences work the same way: see `../old-fence/godot/`.)

## Files

`peel_paint.gdshader` and `paint_lasting.gdshaderinc` (this folder, keep them side by side) plus,
from `../neighborhood/`, per surface:

| Blender material | Textures | Uniforms |
|---|---|---|
| `C_cottage_lap_paint` (lap siding) | `cottage_lap_diff.jpg`, `cottage_lap_paint.png`, `cottage_lap_nor.jpg`, `cottage_lap_rough.jpg` | `uv_scale` 0.694444, `zone_strength` 0.5, `under_tint` (1.69, 1.56, 1.43) |
| `C_cottage_planks_paint_v` (upright boards: gables, front doors, plank siding) | `cottage_planks_diff.jpg`, `_paint.png`, `_nor.jpg`, `_rough.jpg` | `uv_scale` 0.694444, `rotate_90` on, `zone_strength` 0.5, `under_tint` (1.03, 0.97, 0.92) |
| `C_cottage_trim` (white trim: window frames, casings, corner boards, bargeboards, veranda posts, rails, balusters) | `cottage_wood_diff.jpg`, `cottage_planks_paint.png`, `cottage_wood_nor.jpg`, `cottage_wood_rough.jpg` | `uv_scale` 0.694444, `rotate_90` on, `paint_roughness` 0.62, `zone_strength` 0.5 |
| `C_cottage_roof_paint` (corrugated roof) | `cottage_roof_diff.jpg`, `_paint.png`, `_nor.jpg`, `_rough.jpg` | `uv_scale` 0.5, `chalk_mul` 0.6, `chalk_add` 0.35, `paint_roughness` 0.55, `dirt_gain` 1.15, `zone_strength` 0.7, `rust_amount` 1.0, `metal` on, `under_tint` (0.6, 0.56, 0.5) |

Texture slots: `under_tex` = `_diff`, `paint_data` = `_paint`, `normal_tex` = `_nor`,
`rough_tex` = `_rough`, and on all three `cs_wear_zones` = `wear_zones.png` (256 px) and
`cs_paint_flakes` = `paint_flakes.png` (2048 px, data: cracked flakes), both shared.
The roof's `_paint.png` carries the rust streaks in its alpha: keep its alpha on import.

## Setup

1. Import the textures with **VRAM Compressed** and mipmaps (Godot's defaults for 3D
   textures). The `_paint.png` files hold data, not colours; the shader samples them
   without `source_color`, so they are read as-is. Tick **High Quality** (BC7) for
   `paint_flakes.png`: its three channels are independent data, and the default BC1 moves
   about 6 % of its texels across the peel threshold (blocky flake edges); BC7 about 1 %
   (measured in 4.7.2). 2048 px BC7 with mipmaps is about 5.6 MB, shared by every cottage and fence.
2. Make three ShaderMaterials with `peel_paint.gdshader`, one per row above.
3. Export the cottage from Blender as glTF with the default settings (the vertex colour
   is included). In Godot's *Advanced Import Settings* → *Materials*, point
   `C_cottage_lap_paint`, `C_cottage_planks_paint_v` and `C_cottage_roof_paint` at them.

If the paint looks washed out, tick `vertex_color_is_srgb`.

Mesh import: the defaults are fine (the cottages' metre UVs stay within a few metres, so
Godot's 16-bit mesh compression keeps them to about 0.1 mm). Blender's glTF exporter writes
the paint twice (`COLOR_0` and `COLOR_1`, "Export All Vertex Colors"): untick that to drop
the unused copy. The paint edge widens to about a pixel where the pattern is finer than the
screen (`cs_edge`, `fwidth`), so it does not shimmer with anti-aliasing off.

## Cost

Eight texture reads: a PBR material's four, the flakes, and the tiny wear-zones map three times
(two reads at sizes that never line up decide where the weather took the paint, so nothing repeats;
one gathers the damage in one or two areas per building). Each building also gets its own shift
from where it stands. About 60 ALU ops; opaque, no alpha test.
Memory does not grow with the number of colours: three texture sets in total, where the
old way needed one baked colour map per colour (4 siding colours x 2 patterns + 3 roofs).
