"""LODs panel (under the generator panel): auto-build on Generate, rebuild for the selection
or for everything, and a preview switch that shows one level across the scene."""

import time

import bpy

from ..core import ui as cs_ui
from bpy.props import BoolProperty, EnumProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import lod

LEVEL_ITEMS = [(str(i), f"LOD{i}", d) for i, d in enumerate((
    "Full detail: separate parts, interiors, doors that open",
    "One mesh: interior and hidden faces gone, glass opaque",
    "Small parts gone (frames, balusters, hardware); fence boards become cards",
    "Only the big shapes: walls, roof, big trims; fences as cards"))]


def _preview_changed(self, context):
    for root in lod.roots(context, everything=True):
        if any("lod" in o for o in root.children_recursive):
            lod.show(root, int(self.preview))
    from ..world import world_nature            # the world's tree library follows the same switch
    world_nature.show_all(int(self.preview))


class LODGEN_Settings(PropertyGroup):
    auto: BoolProperty(name="Build LODs on Generate", default=True,
                       description="Make LOD1-3 every time a building or fence is generated")
    preview: EnumProperty(name="Show", items=LEVEL_ITEMS, default="0", update=_preview_changed,
                          description="Which level the viewport and renders show, for every generated object")


def after_build(context, root):
    """Called by the generators once a building or fence is (re)built."""
    st = context.scene.roomgen_lod
    if not st.auto or root is None:
        return
    root["lod_preview"] = int(st.preview)
    lod.build(root)


class LODGEN_OT_build(Operator):
    bl_idname = "lod_gen.build"
    bl_label = "Build LODs"
    bl_description = "Build (or rebuild) LOD1-3 for the selected generated buildings and fences, or all of them"
    bl_options = {"REGISTER", "UNDO"}

    everything: BoolProperty(name="All", default=False)

    def execute(self, context):
        roots = lod.roots(context, self.everything)
        if not roots:
            self.report({"WARNING"}, "Select a generated building or fence (or use All)")
            return {"CANCELLED"}
        t0 = time.time()
        prev = int(context.scene.roomgen_lod.preview)
        for r in roots:
            r["lod_preview"] = prev
            lod.build(r)
        r = roots[0]
        msg = " / ".join(f"{r.get(f'lod{i}_tris', 0)}" for i in range(4))
        self.report({"INFO"}, f"LODs for {len(roots)} object(s) in {time.time() - t0:.1f}s; "
                              f"{r.name}: {msg} tris")
        return {"FINISHED"}


class LODGEN_OT_clear(Operator):
    bl_idname = "lod_gen.clear"
    bl_label = "Remove LODs"
    bl_description = "Delete LOD1-3 of the selected generated buildings and fences (LOD0 stays)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        for r in lod.roots(context):
            lod.clear(r)
            lod.show(r, 0)
        return {"FINISHED"}


class LODGEN_PT_panel(Panel):
    bl_label = "LODs"
    bl_idname = "LODGEN_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = cs_ui.CATEGORY
    bl_parent_id = "HOUSEGEN_PT_panel"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        st = context.scene.roomgen_lod
        layout = self.layout
        layout.prop(st, "auto")
        row = layout.row(align=True)
        row.operator("lod_gen.build", text="Build Selected", icon="MOD_DECIM").everything = False
        row.operator("lod_gen.build", text="Build All").everything = True
        layout.operator("lod_gen.clear", icon="TRASH")
        layout.label(text="Show")
        layout.row(align=True).prop(st, "preview", expand=True)
        roots = lod.roots(context)
        if roots and "lod0_tris" in roots[0]:
            r = roots[0]
            box = layout.box()
            box.label(text=r.name, icon="MESH_DATA")
            col = box.column(align=True)
            for i in range(4):
                t = r.get(f"lod{i}_tris")
                if t is not None:
                    col.label(text=f"LOD{i}:  {t:,} tris")


classes = (LODGEN_Settings, LODGEN_OT_build, LODGEN_OT_clear, LODGEN_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.roomgen_lod = PointerProperty(type=LODGEN_Settings)


def unregister():
    del bpy.types.Scene.roomgen_lod
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
