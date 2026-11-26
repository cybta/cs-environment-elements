"""Edit the paint of one generated cottage or fence after it is built, without rebuilding anything.

Select any part of a cottage or an old fence: the "Selected Paint" panel shows THAT object's own colours
and how much of each has peeled off (%): a cottage's walls (painted style), trim and roof, a fence's paint.
The values are the ones its root keeps (core/paint.store: root["paint"], root["paint_by_mat"]), read and
written straight through (the properties below have no storage of their own), so every cottage and fence
in a file is editable, old files too. A change repaints that object at once: its colour attribute on every
mesh, LODs included (core/paint.apply). "Peeling / Colours to Selected" give every selected cottage or fence
the active one's values.

(The generator panels above keep their own settings: they make new buildings and fences.)
"""

import bpy
from bpy.props import BoolProperty, FloatProperty, FloatVectorProperty, PointerProperty
from bpy.types import Operator, Panel, PropertyGroup

from ..core import paint
from ..core import ui as cs_ui

ROOF_MAT = "C_cottage_roof_paint"           # cottage_paint.ROOF_MAT
TRIM_MAT = "C_cottage_trim"                 # cottage_paint.TRIM_MAT
PART_MAT = {"wall": None, "roof": ROOF_MAT, "trim": TRIM_MAT}   # None: the root's own value
DEFAULT = [0.8, 0.8, 0.8, 1.0]


def root_of(ob):
    """The generated root (top parent) of `ob` if it carries paint, else None."""
    while ob is not None and ob.parent is not None:
        ob = ob.parent
    return ob if ob is not None and "paint" in ob else None


def kind(root):
    if root is None:
        return None
    if root.get("building_type") == "COTTAGE":
        return "COTTAGE"
    if any(c.get("roomgen_fence") for c in root.users_collection):
        return "FENCE"
    return None


def parts(root):
    """The parts of `root` that are paint: a painted cottage's walls, every cottage's trim and roof, a fence."""
    k = kind(root)
    if k == "FENCE":
        return ("wall",)
    if k == "COTTAGE":
        return (("wall",) if root.get("cottage_style") == "PAINTED" else ()) + ("trim", "roof")
    return ()


def read(root, part):
    got = paint.stored(root)
    if got is None:
        return list(DEFAULT)
    value, by = got
    mat = PART_MAT[part]
    return list(value if mat is None else by.get(mat, value))


def update(root, changes):
    """changes: {part: (rgb or None, peel or None)} -> stored and repainted in one go."""
    got = paint.stored(root)
    if got is None:
        return
    value, by = got
    for part, (rgb, peel) in changes.items():
        mat = PART_MAT[part]
        cur = list(value if mat is None else by.get(mat, value))
        if rgb is not None:
            cur[:3] = [float(c) for c in rgb]
        if peel is not None:
            cur[3] = min(max(float(peel), 0.0), 1.0)
        if mat is None:
            value = cur
        else:
            by[mat] = cur
    paint.apply(root, value, by)


def _peel(part):
    def get(self):
        return read(self.id_data, part)[3] * 100.0

    def set(self, v):
        update(self.id_data, {part: (None, v / 100.0)})
    return get, set


def _colour(part):
    def get(self):
        return read(self.id_data, part)[:3]

    def set(self, v):
        update(self.id_data, {part: (v, None)})
    return get, set


_WP, _WC, _TP, _TC, _RP, _RC = _peel("wall"), _colour("wall"), _peel("trim"), _colour("trim"), \
    _peel("roof"), _colour("roof")


def _pct(name, gs, what):
    return FloatProperty(name=name, description=f"How much of the {what} has peeled off", subtype="PERCENTAGE",
                         min=0.0, max=100.0, precision=0, get=gs[0], set=gs[1])


def _rgb(name, gs, what):
    return FloatVectorProperty(name=name, description=f"The {what} colour", subtype="COLOR_GAMMA", size=3,
                               min=0.0, max=1.0, get=gs[0], set=gs[1])


class CSENV_PaintEdit(PropertyGroup):
    """A generated object's paint, read from and written to its root (no storage of its own)."""
    wall_peel: _pct("Peeled", _WP, "paint")
    wall_color: _rgb("Colour", _WC, "paint")
    trim_peel: _pct("Peeled", _TP, "white trim's paint")
    trim_color: _rgb("Colour", _TC, "trim's paint")
    roof_peel: _pct("Peeled", _RP, "roof paint")
    roof_color: _rgb("Colour", _RC, "roof paint")


def selected_roots(context):
    return {r for r in (root_of(o) for o in context.selected_objects) if kind(r)}


class CSENV_OT_paint_to_selected(Operator):
    bl_idname = "csenv.paint_to_selected"
    bl_label = "Paint to Selected"
    bl_description = ("Give every selected cottage or fence the active one's peeling and / or colours, part by "
                      "part (walls, trim, roof)")
    bl_options = {"REGISTER", "UNDO"}

    peel: BoolProperty(name="Peeling", default=True)
    colour: BoolProperty(name="Colours", default=False)

    def execute(self, context):
        src = root_of(context.active_object)
        k = kind(src)
        if k is None:
            self.report({"WARNING"}, "The active object is not a generated cottage or fence")
            return {"CANCELLED"}
        done = 0
        for r in selected_roots(context) - {src}:
            if kind(r) != k:
                continue
            common = [p for p in parts(src) if p in parts(r)]
            changes = {}
            for p in common:
                v = read(src, p)
                changes[p] = (v[:3] if self.colour else None, v[3] if self.peel else None)
            update(r, changes)
            done += 1
        self.report({"INFO"}, f"{done} other {k.lower()}(s) repainted")
        return {"FINISHED"}


class CSENV_PT_selected_paint(Panel):
    bl_label = "Selected Paint"
    bl_idname = "CSENV_PT_selected_paint"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = cs_ui.CATEGORY

    @classmethod
    def poll(cls, context):
        return kind(root_of(context.active_object)) is not None

    def draw(self, context):
        root = root_of(context.active_object)
        p = root.cs_paint
        layout = self.layout
        layout.label(text=root.name, icon="HOME" if kind(root) == "COTTAGE" else "MOD_LATTICE")
        titles = {"wall": "Paint" if kind(root) == "FENCE" else "Walls", "trim": "Trim", "roof": "Roof"}
        for part in parts(root):
            col = layout.column(align=True)
            col.label(text=titles[part])
            row = col.row(align=True)
            row.prop(p, f"{part}_color", text="")
            row.prop(p, f"{part}_peel", slider=True)
        n = len(selected_roots(context))
        if n > 1:
            col = layout.column(align=True)
            col.label(text=f"{n} selected", icon="RESTRICT_SELECT_OFF")
            row = col.row(align=True)
            op = row.operator("csenv.paint_to_selected", text="Peeling to Selected")
            op.peel, op.colour = True, False
            op = row.operator("csenv.paint_to_selected", text="Colours to Selected")
            op.peel, op.colour = False, True
        if kind(root) == "COTTAGE":                 # cottage_fix: posts flush with the deck / rim (flicker)
            row = layout.row(align=True)
            row.operator("csenv.fix_porch", icon="MODIFIER").everything = False
            row.operator("csenv.fix_porch", text="All").everything = True


classes = (CSENV_PaintEdit, CSENV_OT_paint_to_selected, CSENV_PT_selected_paint)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Object.cs_paint = PointerProperty(type=CSENV_PaintEdit)


def unregister():
    del bpy.types.Object.cs_paint
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
