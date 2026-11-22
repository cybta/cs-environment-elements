"""Quays section of the generator panel: settings, Generate / Rebuild Selected, panel.

A quay is one mesh named quay-old-<n>, its origin at the shore end of the stem on the
water line, the stem running along its local +Y (rotate it to face the water). The
geometry is built by quay_build.
"""

import random

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator, PropertyGroup

from . import quay_build as qb

PREFIX = "quay-old"
COLLECTION = "Quays"


class QUAYGEN_Settings(PropertyGroup):
    shape: EnumProperty(name="Shape", default="STRAIGHT", items=[
        ("STRAIGHT", "Straight", "One straight jetty out from the shore"),
        ("T", "T Shape", "A jetty with a head across its far end, reaching out left and right"),
    ])
    length: FloatProperty(name="Length (m)", default=8.0, min=1.5, max=60.0, step=50,
                          description="How far the stem runs out from the shore")
    width: FloatProperty(name="Width (m)", default=2.4, min=1.0, max=6.0, step=10,
                         description="Width of the deck (the stem and the head of a T alike)")
    left: FloatProperty(name="Left Arm (m)", default=3.0, min=0.0, max=30.0, step=50,
                        description="How far the head reaches past the stem on the left")
    right: FloatProperty(name="Right Arm (m)", default=3.0, min=0.0, max=30.0, step=50,
                         description="How far the head reaches past the stem on the right")
    deck_height: FloatProperty(name="Deck Height (m)", default=0.8, min=0.2, max=3.0, step=5,
                               description="Deck top above the water line (the origin)")
    water_depth: FloatProperty(name="Water Depth (m)", default=1.5, min=0.2, max=8.0, step=10,
                               description="The piles reach this far below the water line (and a bit more)")

    plank_width: FloatProperty(name="Board Width (m)", default=0.16, min=0.08, max=0.3, step=1)
    gap: FloatProperty(name="Board Gap (m)", default=0.012, min=0.0, max=0.05, step=0.1)
    missing: FloatProperty(name="Missing Boards", default=0.02, min=0.0, max=0.3, subtype="FACTOR",
                           description="Share of deck boards gone")
    wear: FloatProperty(name="Wear", default=0.4, min=0.0, max=1.0, subtype="FACTOR",
                        description="How much the boards sag and the piles lean")

    pile_spacing: FloatProperty(name="Pile Spacing (m)", default=2.0, min=1.0, max=4.0, step=10,
                                description="Most distance between two piles along an edge")
    pile_radius: FloatProperty(name="Pile Radius (m)", default=0.1, min=0.05, max=0.25, step=1)
    posts: BoolProperty(name="Posts", default=True,
                        description="The piles along the outside edges rise above the deck as posts")
    post_height: FloatProperty(name="Post Height (m)", default=0.6, min=0.1, max=1.5, step=5,
                               description="About how far the posts stand above the deck")

    tyres: IntProperty(name="Tyres", default=2, min=0, max=20, description="Old tyres hung on the posts as fenders")
    ladder: BoolProperty(name="Ladder", default=True, description="A steel ladder down into the water")
    ladder_side: EnumProperty(name="Ladder Side", default="RIGHT", items=[
        ("LEFT", "Left", "On the stem's left edge"), ("RIGHT", "Right", "On the stem's right edge")])
    ladder_pos: FloatProperty(name="Ladder Position", default=0.7, min=0.0, max=1.0, subtype="FACTOR",
                              description="Where along the stem (0 = shore end); it sits between two piles")
    seed: IntProperty(name="Seed", default=1, min=0, description="Which boards, sag and lean")


def _settings(context):
    return context.scene.house_gen.quay


def selected_quay(context):
    ob = context.active_object
    return ob if ob is not None and ob.get("quay_gen") else None


def _make(context, op, name, keep=None):
    g = _settings(context)
    me, info = qb.build_mesh(g, random.Random(g.seed), name)
    ob = bpy.data.objects.get(name)
    if ob is not None and ob.get("quay_gen"):
        old = ob.data
        ob.data = me
        if old.users == 0:
            bpy.data.meshes.remove(old)
    else:
        from ..core import library
        ob = bpy.data.objects.new(name, me)
        library.target_collection(context, COLLECTION).objects.link(ob)
        ob.location = context.scene.cursor.location
    ob["quay_gen"] = True
    me.name = name
    if keep is not None:
        ob.matrix_world = keep
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob
    op.report({"INFO"}, f"{name}: {info}")
    return {"FINISHED"}


class QUAYGEN_OT_generate(Operator):
    bl_idname = "quay_gen.generate"
    bl_label = "Generate Quay"
    bl_description = "Build a new quay at the 3D cursor (origin = shore end on the water line), named quay-old-<n>"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        from ..core import naming
        return _make(context, self, naming.next_name(PREFIX))


class QUAYGEN_OT_rebuild(Operator):
    bl_idname = "quay_gen.rebuild"
    bl_label = "Rebuild Selected"
    bl_description = "Rebuild the selected quay with the settings shown, where it stands, keeping its name"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return selected_quay(context) is not None

    def execute(self, context):
        ob = selected_quay(context)
        return _make(context, self, ob.name, ob.matrix_world.copy())


class QUAYGEN_OT_randomize(Operator):
    bl_idname = "quay_gen.randomize"
    bl_label = "New Boards"
    bl_description = "Pick a new seed and rebuild the selected quay (or build a new one)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        _settings(context).seed = random.randint(0, 99999)
        if selected_quay(context) is not None:
            return bpy.ops.quay_gen.rebuild()
        return bpy.ops.quay_gen.generate()


def draw(layout, context):
    g = _settings(context)
    layout.row(align=True).prop(g, "shape", expand=True)
    box = layout.box()
    box.label(text="Size", icon="FULLSCREEN_ENTER")
    c = box.column(align=True)
    c.prop(g, "length", text="Stem Length (m)" if g.shape == "T" else "Length (m)")
    c.prop(g, "width")
    if g.shape == "T":
        c = box.column(align=True)
        c.prop(g, "left")
        c.prop(g, "right")
    c = box.column(align=True)
    c.prop(g, "deck_height")
    c.prop(g, "water_depth")

    box = layout.box()
    box.label(text="Deck & Piles")
    c = box.column(align=True)
    for p in ("plank_width", "gap", "missing", "wear"):
        c.prop(g, p, slider=p in ("missing", "wear"))
    c = box.column(align=True)
    c.prop(g, "pile_spacing")
    c.prop(g, "pile_radius")
    row = box.row(align=True)
    row.prop(g, "posts")
    sub = row.row(align=True)
    sub.enabled = g.posts
    sub.prop(g, "post_height", text="Height")

    box = layout.box()
    box.prop(g, "tyres")
    box.prop(g, "ladder")
    if g.ladder:
        box.row(align=True).prop(g, "ladder_side", expand=True)
        box.prop(g, "ladder_pos", slider=True)

    row = layout.row(align=True)
    row.prop(g, "seed")
    row.operator("quay_gen.randomize", text="", icon="FILE_REFRESH")
    layout.separator()
    big = layout.row()
    big.scale_y = 1.6
    big.operator("quay_gen.generate", icon="ADD")
    if selected_quay(context) is not None:
        layout.operator("quay_gen.rebuild", icon="FILE_REFRESH")


classes = (QUAYGEN_Settings, QUAYGEN_OT_generate, QUAYGEN_OT_rebuild, QUAYGEN_OT_randomize)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
