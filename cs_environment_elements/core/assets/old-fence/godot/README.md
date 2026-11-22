# Old fence paint in Godot 4

Every old wooden fence from the add-on uses **one** material, whatever its paint colour.
The colour and the peeling travel on the mesh as its vertex colour (glTF `COLOR_0`):
RGB = paint colour, A = peeling (0 fresh, 1 bare wood). No texture per colour, no extra
draw calls; the shader reads one more small texture than plain wood.

## Files

Copy these into the Godot project (same folder is easiest):

| File | What |
|---|---|
| `../fence.png` | the planks (shared) |
| `../fence_paint_mask.png` | the peel mask (shared, grey) |
| `fence_old_paint.gdshaderinc` | the paint maths, included by both shaders |
| `fence_old_paint.gdshader` | boards, posts, rails, gate leaves (LOD0, LOD1): opaque |
| `fence_old_paint_card.gdshader` | LOD2/LOD3 cards: alpha scissor for the gaps |

## Setup

1. **Textures** (Import dock): both `fence.png` and `fence_paint_mask.png` →
   Compress Mode *VRAM Compressed*, Mipmaps *on*. The mask is grey, so it compresses to a
   single channel.
2. **Two ShaderMaterials** (`.tres`):
   - `fence_old_paint.tres` → shader `fence_old_paint.gdshader`
   - `fence_old_paint_card.tres` → shader `fence_old_paint_card.gdshader`

   In both, set `wood_tex` = `fence.png` and `paint_mask` = `fence_paint_mask.png`.
3. **Export from Blender** as glTF (.glb). The default settings already include the
   vertex colour (Data → Mesh → *Vertex Color: Material*). Exporting the LODs too gives
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

- Opaque boards: 2 texture reads (planks, mask), about 15 ALU ops; early depth test kept.
- Cards: the same plus the alpha test, only at LOD2/LOD3 where they are few pixels.
- Memory: the mask is 1024 x 1024, one channel (about 0.5 MB compressed with mipmaps).
