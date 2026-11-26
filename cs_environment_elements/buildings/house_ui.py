"""House Generator panel and operators: Generate (a new building, named
<type>-<style>-<n>), Rebuild (the selected one, keeping its name and place), New Layout
and the area presets. The settings and the builder itself live in house.py."""

import random

import bpy
from bpy.props import FloatProperty, IntProperty
from bpy.types import Operator, Panel

from ..core import naming
from ..core import ui as cs_ui
from . import cottage_layout as cl
from . import cottage_paint
from . import fence
from . import podium
from . import quay
from . import shop_ui
from . import villa_layout as vl
from .house import NOT_BUILDINGS, _build


def name_prefix(s):
    """'house', 'villa-modern', 'villa-gable', 'cottage-timber', 'cottage-painted', 'shop-row'."""
    t = s.building_type
    if t.startswith("VILLA"):
        return naming.slug("villa", t[6:])
    if t == "COTTAGE":
        return naming.slug("cottage", s.cottage_style)
    return {"SHOPS": "shop-row"}.get(t, "house")


def selected_building(context):
    """The root empty of the generated building the active object belongs to, or None."""
    ob = context.active_object
    while ob is not None and ob.parent is not None:
        ob = ob.parent
    if ob is None or "building_type" not in ob or not any(c.get("roomgen") for c in ob.users_collection):
        return None
    return ob


def _run(op, context, name, keep=None):
    """Build as `name`; `keep` = the old root's matrix to put the new one back in place."""
    s = context.scene.house_gen
    plan = _build(context, s, op.report, name=name, site=True)
    if plan is None:
        return {"CANCELLED"}
    root = bpy.data.objects.get(name)
    if root is not None:
        if keep is not None:
            root.matrix_world = keep
        for ob in context.selected_objects:
            ob.select_set(False)
        root.select_set(True)
        context.view_layer.objects.active = root
    msg = f"{name}: {plan.W:.2f} x {plan.D:.2f} m, {len(plan.floors)} floor(s)"
    if plan.warnings:
        op.report({"WARNING"}, msg + " — " + "; ".join(dict.fromkeys(plan.warnings)))
    else:
        op.report({"INFO"}, msg)
    print(plan.summary())
    return {"FINISHED"}


class HOUSEGEN_OT_generate(Operator):
    bl_idname = "house_gen.generate"
    bl_label = "Generate"
    bl_description = "Build a new building with a random floor plan at the 3D cursor, named <type>-<n>"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.house_gen
        if s.building_type == "FENCE":
            return bpy.ops.fence_gen.generate()
        if s.building_type == "QUAY":
            return bpy.ops.quay_gen.generate()
        return _run(self, context, naming.next_name(name_prefix(s)))


class HOUSEGEN_OT_rebuild(Operator):
    bl_idname = "house_gen.rebuild"
    bl_label = "Rebuild Selected"
    bl_description = ("Rebuild the selected building with the settings shown, where it stands. It keeps its "
                      "name unless its type changed (then it takes the next name for the new type)")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.scene.house_gen.building_type not in NOT_BUILDINGS and selected_building(context) is not None

    def execute(self, context):
        from ..core.scene_utils import _delete_collection
        root = selected_building(context)
        keep, old_name = root.matrix_world.copy(), root.name
        name = naming.keep_or_next(old_name, name_prefix(context.scene.house_gen))
        if name != old_name:                          # another type: drop the old building
            for coll in [c for c in root.users_collection if c.get("roomgen")]:
                _delete_collection(coll)
        return _run(self, context, name, keep)


class HOUSEGEN_OT_randomize(Operator):
    bl_idname = "house_gen.randomize"
    bl_label = "New Layout"
    bl_description = "Pick a new random seed and rebuild the selected building (or build a new one)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.house_gen
        s.seed = random.randint(0, 99999)
        if s.building_type not in NOT_BUILDINGS and selected_building(context) is not None:
            return bpy.ops.house_gen.rebuild()
        return bpy.ops.house_gen.generate()


class HOUSEGEN_OT_preset(Operator):
    bl_idname = "house_gen.preset"
    bl_label = "House Preset"
    bl_description = "Fill in a typical house programme"
    bl_options = {"REGISTER", "UNDO"}

    area: FloatProperty()
    floors: IntProperty()
    bedrooms: IntProperty()
    bathrooms: IntProperty()

    def execute(self, context):
        s = context.scene.house_gen
        s.total_area, s.bedrooms, s.bathrooms = self.area, self.bedrooms, self.bathrooms
        if s.building_type == "HOUSE":
            s.floors = self.floors
        s.open_plan = True
        return {"FINISHED"}


class HOUSEGEN_PT_panel(Panel):
    bl_label = "House Generator"
    bl_idname = "HOUSEGEN_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = cs_ui.CATEGORY

    @classmethod
    def poll(cls, context):
        return cs_ui.in_section(context, "BUILDINGS")

    def draw(self, context):
        s = context.scene.house_gen
        layout = self.layout
        villa = s.building_type.startswith("VILLA")
        cottage = s.building_type == "COTTAGE"
        shops = s.building_type == "SHOPS"
        layout.prop(s, "section")
        if villa:
            layout.row(align=True).prop(s, "villa_style", expand=True)
        elif cottage:
            layout.row(align=True).prop(s, "cottage_style", expand=True)
        if s.building_type == "FENCE":
            fence.draw(layout, context)
            return
        if s.building_type == "QUAY":
            quay.draw(layout, context)
            return

        presets = {
            "HOUSE": (("100 m² · 1F", 100, 1, 3, 2), ("130 m² · 2F", 130, 2, 3, 2), ("200 m² · 2F", 200, 2, 4, 3)),
            "VILLA_MODERN": (("200 m² · 3 bed", 200, 2, 3, 2), ("240 m² · 4 bed", 240, 2, 4, 3),
                             ("320 m² · 5 bed", 320, 2, 5, 4)),
            "VILLA_GABLE": (("170 m² · 2 bed", 170, 2, 2, 2), ("200 m² · 3 bed", 200, 2, 3, 2),
                            ("260 m² · 4 bed", 260, 2, 4, 3)),
            "VILLA_MEDITERRANEAN": (("380 m² · 3 bed", 380, 2, 3, 2), ("420 m² · 3 bed", 420, 2, 3, 2),
                                    ("520 m² · 3 bed", 520, 2, 3, 2)),
            "COTTAGE": (("6x6 · 2 bed", 60, 2, 2, 0), ("6x8 · 3 bed", 80, 2, 3, 1),
                        ("7x8 · 3 bed", 95, 2, 3, 1)),
        }.get(s.building_type, ())
        row = layout.row(align=True)
        for label, a, fl, bd, ba in presets:
            op = row.operator("house_gen.preset", text=label)
            op.area, op.floors, op.bedrooms, op.bathrooms = a, fl, bd, ba

        col = layout.column(align=True)
        if shops:
            shop_ui.draw(layout, s)
        else:
            col.prop(s, "total_area")
        if not (villa or cottage or shops):
            col.prop(s, "floors")
        if not shops:
            col.prop(s, "bedrooms")
            col.prop(s, "bathrooms")
        if shops:
            pass
        elif cottage:
            if s.total_area < cl.MIN_AREA:
                layout.label(text=f"Smallest a cottage goes: {cl.MIN_AREA:.0f} m²", icon="ERROR")
            else:
                layout.label(text="Ground floor + attic; veranda is extra", icon="INFO")
        elif villa:
            low = vl.MIN_AREA[s.building_type[6:]]
            if s.total_area < low:
                layout.label(text=f"Smallest this villa goes: {low:.0f} m²", icon="ERROR")
            else:
                if s.building_type == "VILLA_MEDITERRANEAN":
                    layout.label(text="Courtyard house: 3 bed, 2.5 bath; courtyard is extra", icon="INFO")
                else:
                    layout.label(text="Two floors; carport and balcony are extra", icon="INFO")
        else:
            layout.prop(s, "open_plan")
            per = s.total_area / max(1, s.floors)
            layout.label(text=f"≈ {per:.0f} m² per floor", icon="INFO")

        row = layout.row(align=True)
        row.prop(s, "seed")
        row.operator("house_gen.randomize", text="", icon="FILE_REFRESH")

        box = layout.box()
        box.label(text="Construction")
        c = box.column(align=True)
        c.prop(s, "ceiling_height")
        c.prop(s, "slab")
        c.prop(s, "ext_wall")
        c.prop(s, "int_wall")
        c.prop(s, "ground_lift")
        if not villa:
            r = box.row(align=True)
            r.prop(s, "sidewalk", toggle=True, text="Gravel Bed" if cottage else "Sidewalk")
            sub = r.row(align=True)
            sub.enabled = s.sidewalk
            sub.prop(s, "sidewalk_width")
        box.prop(s, "add_inserts")
        r = box.row(align=True)
        r.prop(s, "add_labels", toggle=True)
        r.prop(s, "add_lights", toggle=True)
        sub = box.row()
        sub.enabled = s.add_lights
        sub.prop(s, "light_power")

        if s.building_type in podium.TYPES:
            podium.draw(layout, s)

        rbox = layout.box()
        rc = rbox.column(align=True)
        if shops:
            shop_ui.draw_details(rbox, s)
        elif cottage:
            rbox.label(text="Cottage")
            rbox.prop(s, "cottage_chimney", toggle=True)
        elif villa:
            rbox.label(text="Villa")
            if s.building_type == "VILLA_GABLE":
                rbox.prop(s, "villa_pitch")
            r = rbox.row(align=True)
            r.prop(s, "villa_site", toggle=True)
            r.prop(s, "villa_pool", toggle=True)
            if s.villa_pool:
                pc = rbox.column(align=True)
                pc.prop(s, "pool_length")
                pc.prop(s, "pool_width")
        else:
            rbox.prop(s, "roof_type")
        if villa or cottage or shops:
            pass
        elif s.roof_type == "PARAPET":
            rc.prop(s, "parapet_height")
        elif s.roof_type in ("GABLE", "HIP", "SHED"):
            rc.prop(s, "roof_pitch")
            rc.prop(s, "roof_overhang")
            rc.prop(s, "roof_thickness")
            if s.roof_type != "HIP":
                rbox.prop(s, "ridge_dir", text="High Side" if s.roof_type == "SHED" else "Ridge")

        mbox = layout.box()
        mbox.prop(s, "material_style")
        mcol = mbox.column(align=True)
        if s.material_style == "NEIGHBORHOOD" and cottage:
            cottage_paint.draw(mbox, s)
            mbox.prop(s, "bath_tiles")
        elif s.material_style == "NEIGHBORHOOD":
            mcol.prop(s, "facade")
            if s.building_type in ("VILLA_GABLE", "VILLA_MEDITERRANEAN") or (
                    not (villa or shops) and s.roof_type in ("GABLE", "HIP", "SHED")):
                mcol.prop(s, "roof_color")
            if villa or s.building_type == "HOUSE":
                mcol.prop(s, "inner_walls")
            mbox.prop(s, "bath_tiles")
        elif s.material_style == "TEXTURE_SETS":
            mcol.prop(s, "wall_material")
            mcol.prop(s, "floor_material")
            mcol.prop(s, "ceiling_material")
            mcol.prop(s, "tex_size")

        layout.separator()
        big = layout.row()
        big.scale_y = 1.6
        big.operator("house_gen.generate", text=f"Generate {naming.next_name(name_prefix(s))}", icon="HOME")
        root = selected_building(context)
        if root is not None:
            new = naming.keep_or_next(root.name, name_prefix(s))
            text = f"Rebuild {root.name}" + (f"  →  {new}" if new != root.name else "")
            layout.operator("house_gen.rebuild", text=text, icon="FILE_REFRESH")


classes = (
    HOUSEGEN_OT_generate,
    HOUSEGEN_OT_rebuild,
    HOUSEGEN_OT_randomize,
    HOUSEGEN_OT_preset,
    HOUSEGEN_PT_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
