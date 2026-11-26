"""Paint on the cottages: the painted cottage's siding, every cottage's corrugated roof and white trim.

All are peeling-paint materials (core/paint.py): the colour and how much has peeled
off travel on the mesh (colour attribute "Paint"), so every cottage in the game shares
the same four materials (lap siding, upright planks, roof, white trim) whatever its colours.
On one cottage the roof faces carry the roof paint, the trim faces (window frames, casings,
corner boards, bargeboards, veranda posts, rails, balusters) old white paint peeling a little
more than the walls, and everything else the siding paint.

Colours: a named one (Cream, Green... / Red, Green, Grey sheet), "Random" (picked from the
house seed, as before) or "Custom" (the colour picker). Changing the paint settings
repaints the selected cottage at once; no rebuild.
"""

import random

import bpy
from bpy.types import Operator

from ..core import neighborhood_materials as nm
from ..core import paint

ROOF_MAT = "C_cottage_roof_paint"
TRIM_MAT = "C_cottage_trim"
TRIM_SRGB = (0.9, 0.89, 0.85)      # old white paint
TRIM_EXTRA_PEEL = 0.02             # trim paint (edges, end grain) gives up a little before the walls'


def colours(s):
    """((siding r, g, b, peel), (roof r, g, b, peel), (trim r, g, b, peel)) for the settings `s` (house_gen).
    The white trim peels with the walls' Peeling (on a timber cottage that slider is the trim's alone)."""
    siding = nm.siding_paint_colour(s.cottage_paint, s.seed, s.cottage_paint_color)
    roof = nm.roof_paint_colour(s.cottage_roof, s.seed, s.cottage_roof_color)
    painted = s.cottage_style == "PAINTED"
    trim = (*TRIM_SRGB, min(1.0, s.cottage_peel + TRIM_EXTRA_PEEL))
    return (*siding, s.cottage_peel if painted else 1.0), (*roof, s.cottage_roof_peel), trim


def apply(root, s):
    """Paint a cottage (all its meshes; the LOD builder copies it to the LODs)."""
    siding, roof, trim = colours(s)
    paint.apply(root, siding, {ROOF_MAT: roof, TRIM_MAT: trim})


def _selected_cottage(context):
    from .house_ui import selected_building
    root = selected_building(context)
    if root is None or root.get("building_type") != "COTTAGE":
        return None
    return root


def on_change(self, context):
    """Panel paint settings changed: repaint the selected cottage (same style only)."""
    if context is None or paint.is_quiet() or self.building_type != "COTTAGE" \
            or self.material_style != "NEIGHBORHOOD":
        return
    root = _selected_cottage(context)
    if root is not None and root.get("cottage_style") == self.cottage_style:
        apply(root, self)


class HOUSEGEN_OT_random_cottage_paint(Operator):
    bl_idname = "house_gen.random_cottage_paint"
    bl_label = "Random Paint"
    bl_description = "Pick a siding colour, a roof colour and how much each has peeled (repaints the selected cottage)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.house_gen
        with paint.quiet():
            s.cottage_paint = random.choice(nm.COTTAGE_PAINTS)[0]
            s.cottage_roof = random.choice(nm.COTTAGE_ROOFS)[0]
            s.cottage_peel = round(random.uniform(0.1, 0.6), 2)
        s.cottage_roof_peel = round(random.uniform(0.1, 0.7), 2)   # the last one repaints
        return {"FINISHED"}


def draw(layout, s):
    """The cottage's paint settings (material box, Neighborhood materials)."""
    head = layout.row(align=True)
    head.label(text="Paint", icon="BRUSH_DATA")
    head.operator("house_gen.random_cottage_paint", text="", icon="FILE_REFRESH")
    col = layout.column(align=True)
    col.prop(s, "cottage_roof")
    if s.cottage_roof == "CUSTOM":
        col.prop(s, "cottage_roof_color", text="")
    col.prop(s, "cottage_roof_peel", slider=True)
    if s.cottage_style == "PAINTED":
        col = layout.column(align=True)
        col.prop(s, "cottage_paint")
        if s.cottage_paint == "CUSTOM":
            col.prop(s, "cottage_paint_color", text="")
        col.prop(s, "cottage_peel", slider=True)
        layout.prop(s, "cottage_siding")
    else:
        layout.prop(s, "cottage_peel", text="Trim Peeling", slider=True)


classes = (HOUSEGEN_OT_random_cottage_paint,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
