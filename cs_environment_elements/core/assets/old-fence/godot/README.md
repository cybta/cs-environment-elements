# Old fence paint in Godot 4

Every old wooden fence from the add-on uses **one** material, whatever its paint colour.
The colour and the peeling travel on the mesh as its vertex colour (glTF `COLOR_0`):
RGB = paint colour, A = peeling (0 fresh, 1 bare wood). No texture per colour, no extra
draw calls. Where the paint has gone comes from the same weather patches and cracked flakes as
the cottages (`../../godot/paint_lasting.gdshaderinc`), read through the fence's second UV
(`UV2`, the Blender layer "WearUV": the fence in metres, so patches run across boards).

## Files

Copy these into the Godot project (same folder is easiest):

| File | What |
|---|---|
| `../fence.png` | the planks (shared) |
| `../fence_paint_mask.png` | board-level wear: board edges, each plank's age (shared, grey) |
| `../../neighborhood/wear_zones.png`, `../../neighborhood/paint_flakes.png` | weather patches, cracked flakes (shared with the cottages) |
| `../../godot/paint_lasting.gdshaderinc` | the shared paint maths: copy it into the same folder |
| `fence_old_paint.gdshaderinc` | the paint maths, included by both shaders |
| `fence_old_paint.gdshader` | boards, posts, rails, gate leaves (LOD0, LOD1): opaque |
| `fence_old_paint_card.gdshader` | LOD2/LOD3 cards: alpha scissor for the gaps |

## Setup

1. **Textures** (Import dock): `fence.png`, `fence_paint_mask.png` and the two shared maps →
   Compress Mode *VRAM Compressed*, Mipmaps *on*; `paint_flakes.png` also *High Quality*
   (BC7, see `../../godot/README.md`). The mask is grey, so it compresses to a single channel.
2. **Two ShaderMaterials** (`.tres`):
   - `fence_old_paint.tres` → shader `fence_old_paint.gdshader`
   - `fence_old_paint_card.tres` → shader `fence_old_paint_card.gdshader`

   In both, set `wood_tex` = `fence.png`, `paint_mask` = `fence_paint_mask.png`,
   `cs_wear_zones` = `wear_zones.png` and `cs_paint_flakes` = `paint_flakes.png`.
3. **Export from Blender** as glTF (.glb). The default settings already include the
   vertex colour (Data → Mesh → *Vertex Color: Material*) and both UV layers (UVMap →
   `UV`, WearUV → `UV2`; keep *Light Baking* off *Static Lightmaps* on import, or Godot
   replaces `UV2` with a lightmap unwrap). WearUV is measured from each fence's first
   board, so it stays within about +-30 m and Godot's default mesh compression keeps it to
   ~0.8 mm steps (finer than the flakes): no need for *Force Disable Compression*.
   Untick "Export All Vertex Colors" to drop the duplicate `COLOR_1`. Exporting the LODs too gives
   `<fence>_LOD1/2/3` meshes, ready for Godot's visibility ranges.
4. **Import in Godot**: open the .glb's *Advanced Import Settings* → *Materials*, and
   point the materials at your files ("Use External"):
   - `C_fence_old_paint` → `fence_old_paint.tres`
   - `C_fence_old_paint_card` → `fence_old_paint_card.tres`
   - `C_fence_iron` (hinges, latches) can stay as imported.

If the paint looks washed out (too light), tick `vertex_color_is_srgb` on both materials.

## Changing the paint in the game

The colour is per vertex, so to repaint one fence at run time either give that
MeshInstance3D a material override with other defaults, or rewrite its vertex colours
(e.g. with `MeshDataTool`). The peeling amount (alpha) can be animated the same way.

## Cost

- Opaque boards: 5 texture reads (planks, mask, flakes, the wear map twice), about 40 ALU ops;
  early depth test kept.
- Cards: the same plus the alpha test, only at LOD2/LOD3 where they are few pixels.
- Memory: the mask is 1024 x 1024, one channel (about 0.5 MB compressed with mipmaps);
  the flakes (2048 px) and the wear map are shared with the cottages.
