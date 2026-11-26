"""Paint on the old wooden fence: a colour, and how much of it has peeled off.

Built to be cheap in a game, and the same in Blender and in Godot
(core/assets/old-fence/godot/ has the shader and how to set it up):

- fence.png               the planks, shared by every old fence (as before)
- fence_paint_mask.png    one grey texture laid out like fence.png: board-level wear (board edges first,
                          each plank its own age), made by tools/make_fence_paint_mask.py
- wear_zones.png, paint_flakes.png   (core/assets/neighborhood) the cottages' weather patches and
                          cracked flakes, read through the fence's second UV layer "WearUV" (metres,
                          U along the grain; glTF TEXCOORD_1, Godot UV2), see core/paint_nodes.py
- colour attribute "Paint" on every mesh of a fence (LODs too): RGB = the paint colour,
                          A = peeling (0 fresh .. 1 bare wood). glTF exports it as COLOR_0.
                          Written by core.paint, which the cottages share.

So every old fence in the game uses ONE material, whatever its colour: no texture per
colour, no extra draw calls. The shading:

    last   = paint_nodes.lasting(WearUV, mask)                 # how long the paint lasts here
    paint  = smoothstep(peel - SOFT, peel + SOFT, last)        # 1 where paint is left
    rim    = 1 - smoothstep(0, RIM, |last - peel|)             # dirty edge round each flake
    crack  = paint_nodes.crack(last, peel, flakes.G)           # cracks just before it flakes
    grain  = mix(1, clamp(luma(wood) * 2.5, 0, 1), 0.35)       # the wood shows through a little
    bare   = wood * PEELED_TINT                                # the timber cottages' old brown wood, painted or not
    albedo = mix(bare, colour * grain * (1 - 0.18 rim) * crack, paint)
    rough  = mix(0.88, 0.6, paint)

A fence without paint carries peel = 1 (bare wood), so it shares the material too.
"""

import os
import random

import bpy
from bpy.types import Operator

from . import fence_geom as fg

MAT = "C_fence_old_paint"
ATTR = "Paint"
SOFT = 0.03
RIM = 0.06
VERSION = 5
MASK_PATH = os.path.join(os.path.dirname(fg.TEX_PATH), "fence_paint_mask.png")
WOOD_ROUGH, PAINT_ROUGH = 0.88, 0.6
# fence.png times this (linear) = the timber cottages' wood (cottage_wood_diff.jpg mean colour): every bare
# fence board, under peeled paint or never painted, is the same old brown wood as the cottages (user, 2026-11-23:
# no pale, near-white wood)
PEELED_TINT = (0.40, 0.36, 0.284)

# Old outdoor paints, sRGB (what the colour picker shows)
PALETTE = (
    ("Faded Green", (0.33, 0.46, 0.34)),
    ("Bottle Green", (0.16, 0.29, 0.21)),
    ("Faded Blue", (0.34, 0.47, 0.6)),
    ("Sky Blue", (0.5, 0.66, 0.78)),
    ("Red Brown", (0.5, 0.23, 0.17)),
    ("Ochre", (0.74, 0.57, 0.27)),
    ("Off White", (0.84, 0.82, 0.76)),
)
DEFAULT_COLOR = PALETTE[0][1]


def rgba(g):
    """The fence settings' paint as the attribute value (sRGB colour, peel)."""
    return (*g.paint_color, g.peel if g.paint else 1.0)


# --------------------------------------------------------------------------
# Material
# --------------------------------------------------------------------------

def _img(path, non_color):
    if not os.path.exists(path):
        return None
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def material():
    """C_fence_old_paint: the planks with the paint mixed on from the "Paint" attribute."""
    from ..core import neighborhood_materials as nm
    from ..core import paint_nodes as pn

    mat = bpy.data.materials.get(MAT)
    if mat is not None and mat.get("paint_version") == VERSION:
        return mat
    mat = mat or bpy.data.materials.new(MAT)
    mat["paint_version"] = VERSION
    mat.use_nodes = True
    mat.diffuse_color = (0.42, 0.37, 0.31, 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    g = pn.Graph(nt)
    L, math = g.link, g.math

    out = g.node("ShaderNodeOutputMaterial", 900, 0)
    bsdf = g.node("ShaderNodeBsdfPrincipled", 600, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    uv = g.node("ShaderNodeUVMap", -1300, 250, uv_map="UVMap")
    wood = g.image(-900, 250, _img(fg.TEX_PATH, False), uv.outputs["UV"], "Wood")
    wood.extension = "EXTEND"
    mask = g.image(-900, -150, _img(MASK_PATH, True), uv.outputs["UV"], "PaintMask")
    mask.extension = "EXTEND"
    wear = g.node("ShaderNodeUVMap", -2200, -900, uv_map=fg.WEAR_UV, label="WearUV (metres, U along the grain)")
    flake_uv = g.node("ShaderNodeVectorMath", -2000, -1200, operation="SCALE")
    L(wear.outputs["UV"], flake_uv.inputs[0])
    flake_uv.inputs["Scale"].default_value = 1.0 / pn.FLAKE_SIZE
    last, cracks = pn.lasting(g, lambda f: nm._image(f, True), wear.outputs["UV"], flake_uv.outputs["Vector"],
                              mask.outputs["Color"], None, w_board=pn.W_BOARD_FENCE, x=-2000, y=-900)
    attr = g.node("ShaderNodeVertexColor", -900, -450, layer_name=ATTR, label="Paint (RGB colour, A peeling)")
    peel = attr.outputs["Alpha"]
    paint = g.smooth(-350, -250, last, math("SUBTRACT", -600, -350, peel, SOFT),
                     math("ADD", -600, -500, peel, SOFT), label="Paint left")
    rim = g.smooth(-350, -600, math("ABSOLUTE", -500, -600, math("SUBTRACT", -650, -650, last, peel)),
                   0.0, RIM, 1.0, 0.0, "Flake rim")
    darken = math("MULTIPLY", 0, -600, math("MULTIPLY_ADD", -150, -600, rim, -0.18, 1.0),
                  pn.crack(g, last, peel, cracks, x=-500, y=-850))

    luma = g.node("ShaderNodeRGBToBW", -600, 100)
    L(wood.outputs["Color"], luma.inputs["Color"])
    gr = math("MINIMUM", -250, 100, math("MULTIPLY", -400, 100, luma.outputs["Val"], 2.5), 1.0)
    grain = math("MULTIPLY_ADD", -100, 100, gr, 0.35, 0.65)      # mix(1, g, 0.35)
    coat = g.mix("RGBA", "MULTIPLY", 100, 0, 1.0, attr.outputs["Color"], math("MULTIPLY", 0, 100, grain, darken))
    tinted = g.node("ShaderNodeVectorMath", 100, 350, operation="MULTIPLY", label="Old brown wood")
    L(wood.outputs["Color"], tinted.inputs[0])
    tinted.inputs[1].default_value = PEELED_TINT
    albedo = g.mix("RGBA", "MIX", 450, 150, paint, tinted.outputs["Vector"], coat)
    L(albedo, bsdf.inputs["Base Color"])
    L(g.smooth(350, -250, paint, 0.0, 1.0, WOOD_ROUGH, PAINT_ROUGH), bsdf.inputs["Roughness"])
    bump = g.node("ShaderNodeBump", 350, -500)                   # cracks and grain (as the bare wood)
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.003
    L(wood.outputs["Color"], bump.inputs["Height"])
    L(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# --------------------------------------------------------------------------
# Per-fence paint (the colour attribute)
# --------------------------------------------------------------------------

def apply(root, value):
    """Paint a whole fence: LOD0 objects, gate leaves and the LOD meshes (core.paint)."""
    from ..core import paint
    paint.apply(root, value)


def painted_roots(context):
    """Old fences the selection belongs to (not cottages, which carry paint too)."""
    from .lod import roots
    return [r for r in roots(context) if "paint" in r and any(c.get("roomgen_fence") for c in r.users_collection)]


def quiet():
    """Set paint settings from code (the World builder) without repainting the selection
    (one switch for fences and cottages: core.paint.quiet)."""
    from ..core import paint
    return paint.quiet()


def on_change(self, context):
    """Panel paint settings changed: repaint the selected old fence(s) at once (no rebuild)."""
    from ..core import paint
    if context is None or paint.is_quiet():
        return
    for root in painted_roots(context):
        apply(root, rgba(self))


class FENCEGEN_OT_random_paint(Operator):
    bl_idname = "fence_gen.random_paint"
    bl_label = "Random Paint"
    bl_description = "Pick an old paint colour and a peeling amount (repaints the selected fence)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        g = context.scene.house_gen.fence
        g.paint = True
        g.paint_color = random.choice(PALETTE)[1]
        g.peel = round(random.uniform(0.3, 0.85), 2)
        return {"FINISHED"}


def draw(layout, g):
    box = layout.box()
    row = box.row(align=True)
    row.prop(g, "paint", text="Paint", icon="BRUSH_DATA")
    row.operator("fence_gen.random_paint", text="", icon="FILE_REFRESH")
    col = box.column(align=True)
    col.enabled = g.paint
    col.prop(g, "paint_color", text="")
    col.prop(g, "peel", slider=True)
