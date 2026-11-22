"""Paint on the old wooden fence: a colour, and how much of it has peeled off.

Built to be cheap in a game, and the same in Blender and in Godot
(core/assets/old-fence/godot/ has the shader and how to set it up):

- fence.png               the planks, shared by every old fence (as before)
- fence_paint_mask.png    one grey texture laid out like fence.png: how long the paint lasts
                          at each spot (board edges first, patches along the grain), made by
                          tools/make_fence_paint_mask.py; also shared by every fence
- colour attribute "Paint" on every mesh of a fence (LODs too): RGB = the paint colour,
                          A = peeling (0 fresh .. 1 bare wood). glTF exports it as COLOR_0.
                          Written by core.paint, which the cottages share.

So every old fence in the game uses ONE material, whatever its colour: no texture per
colour, no extra draw calls, one more texture read per pixel. The shading:

    paint  = smoothstep(peel - SOFT, peel + SOFT, mask)        # 1 where paint is left
    grain  = mix(1, clamp(luma(wood) * 2.5, 0, 1), 0.35)       # the wood shows through a little
    albedo = mix(wood, colour * grain, paint)
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
VERSION = 1
MASK_PATH = os.path.join(os.path.dirname(fg.TEX_PATH), "fence_paint_mask.png")
WOOD_ROUGH, PAINT_ROUGH = 0.88, 0.6

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
    mat = bpy.data.materials.get(MAT)
    if mat is not None and mat.get("paint_version") == VERSION:
        return mat
    mat = mat or bpy.data.materials.new(MAT)
    mat["paint_version"] = VERSION
    mat.use_nodes = True
    mat.diffuse_color = (0.42, 0.37, 0.31, 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new

    def node(kind, x, y, **props):
        n = N(kind)
        n.location = (x, y)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def math(op, x, y, a=None, b=None, c=None):
        n = node("ShaderNodeMath", x, y, operation=op)
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L(v, n.inputs[i])
        return n.outputs[0]

    out = node("ShaderNodeOutputMaterial", 900, 0)
    bsdf = node("ShaderNodeBsdfPrincipled", 600, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])
    wood = node("ShaderNodeTexImage", -900, 250, name="Wood", label="Wood (fence.png)", extension="EXTEND")
    wood.image = _img(fg.TEX_PATH, False)
    mask = node("ShaderNodeTexImage", -900, -150, name="PaintMask", label="Peel mask", extension="EXTEND")
    mask.image = _img(MASK_PATH, True)
    attr = node("ShaderNodeVertexColor", -900, -450, layer_name=ATTR, label="Paint (RGB colour, A peeling)")

    peel = attr.outputs["Alpha"]
    lo = math("SUBTRACT", -600, -350, peel, SOFT)
    hi = math("ADD", -600, -500, peel, SOFT)
    rng = node("ShaderNodeMapRange", -350, -250, interpolation_type="SMOOTHSTEP", label="Paint left")
    L(mask.outputs["Color"], rng.inputs["Value"])
    L(lo, rng.inputs["From Min"])
    L(hi, rng.inputs["From Max"])
    paint = rng.outputs["Result"]

    luma = node("ShaderNodeRGBToBW", -600, 100)
    L(wood.outputs["Color"], luma.inputs["Color"])
    g = math("MULTIPLY", -400, 100, luma.outputs["Val"], 2.5)
    g = math("MINIMUM", -250, 100, g, 1.0)
    grain = math("MULTIPLY_ADD", -100, 100, g, 0.35, 0.65)      # mix(1, g, 0.35)

    def mix_rgb(blend, x, y, fac, a, b):
        m = node("ShaderNodeMix", x, y, data_type="RGBA", blend_type=blend)
        sock = {s.identifier: s for s in m.inputs}
        for key, v in (("Factor_Float", fac), ("A_Color", a), ("B_Color", b)):
            if isinstance(v, (int, float)):
                sock[key].default_value = v
            else:
                L(v, sock[key])
        return next(s for s in m.outputs if s.identifier == "Result_Color")

    coat = mix_rgb("MULTIPLY", 100, 0, 1.0, attr.outputs["Color"], grain)
    albedo = mix_rgb("MIX", 350, 150, paint, wood.outputs["Color"], coat)
    L(albedo, bsdf.inputs["Base Color"])
    rough = node("ShaderNodeMapRange", 350, -250)
    L(paint, rough.inputs["Value"])
    rough.inputs["To Min"].default_value = WOOD_ROUGH
    rough.inputs["To Max"].default_value = PAINT_ROUGH
    L(rough.outputs["Result"], bsdf.inputs["Roughness"])
    bump = node("ShaderNodeBump", 350, -500)                   # cracks and grain (as the bare wood)
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
