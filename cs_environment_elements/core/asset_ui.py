"""Panel, settings and Add operator for a section that places bundled models (props,
interior). A section describes its pieces in a Catalog; `Catalog.register()` builds its
settings (Scene.<prop>) and its panel, and the shared operator does the placing.

Every kind of piece can have an Old and a New style with the same controls; a kind
with only "ANY" pieces (e.g. the workshop) has no style switch.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import library, naming
from . import ui as cs_ui

STYLES = [("OLD", "Old", "Old, worn pieces"), ("NEW", "New", "New, modern pieces")]
_CATALOGS = {}        # section key -> Catalog
_ENUM_CACHE = {}      # keeps dynamic enum strings alive (Blender requires it)


class Catalog:
    """`kinds`: [(key, label, icon, {"OLD"/"NEW"/"ANY": [library.Item, ...]}), ...]"""

    def __init__(self, section, label, prop, folder, collection, kinds):
        self.section, self.label, self.prop = section, label, prop
        self.folder, self.collection, self.kinds = folder, collection, kinds
        self.classes = ()

    def kind(self, key):
        return next(k for k in self.kinds if k[0] == key)

    def styled(self, kind_key):
        return "ANY" not in self.kind(kind_key)[3]

    def items(self, kind_key, style):
        styles = self.kind(kind_key)[3]
        return styles.get("ANY") or styles.get(style, [])

    def every(self, style):
        return [it for k in self.kinds for it in self.items(k[0], style)]

    def find(self, kind_key, style, piece):
        return next((it for it in self.items(kind_key, style) if it.key == piece), None)

    # -- registration -----------------------------------------------------
    def register(self):
        _CATALOGS[self.section] = self
        self.classes = (_settings_class(self), _panel_class(self))
        for cls in self.classes:
            bpy.utils.register_class(cls)
        setattr(bpy.types.Scene, self.prop, PointerProperty(type=self.classes[0]))

    def unregister(self):
        delattr(bpy.types.Scene, self.prop)
        for cls in reversed(self.classes):
            bpy.utils.unregister_class(cls)
        _CATALOGS.pop(self.section, None)


def _settings_class(cat):
    def piece_items(self, context):
        key = (cat.section, self.kind, self.style)
        if key not in _ENUM_CACHE:
            _ENUM_CACHE[key] = [(it.key, it.label, it.note or it.label) for it in cat.items(self.kind, self.style)] \
                or [("NONE", "(none yet)", "")]
        return _ENUM_CACHE[key]

    def reset_piece(self, context):
        items = cat.items(self.kind, self.style)
        if items:
            self.piece = items[0].key

    kinds = [(k, label, f"{label}", icon, i) for i, (k, label, icon, _s) in enumerate(cat.kinds)]
    ann = {
        "kind": EnumProperty(name="Type", items=kinds, update=reset_piece),
        "style": EnumProperty(name="Style", items=STYLES, default="OLD", update=reset_piece),
        "piece": EnumProperty(name="Piece", items=piece_items),
        "rotation": FloatProperty(name="Rotation", subtype="ANGLE", default=0.0,
                                  description="Turn the piece round the cursor"),
        "extra": BoolProperty(name="Attachment", default=False,
                              description="Add the piece's optional attachment too (parented to it)"),
        "gap": FloatProperty(name="Gap", default=0.5, min=0.0, soft_max=3.0, unit="LENGTH",
                             description="Space between pieces when adding a whole style"),
    }
    return type(f"CSENV_{cat.section}_Settings", (PropertyGroup,), {"__annotations__": ann})


def _panel_class(cat):
    def poll(cls, context):
        return cs_ui.in_section(context, cat.section)

    def draw(self, context):
        st = getattr(context.scene, cat.prop)
        layout = self.layout
        layout.prop(st, "kind")
        if cat.styled(st.kind):
            layout.row(align=True).prop(st, "style", expand=True)
        items = cat.items(st.kind, st.style)
        if not items:
            label = cat.kind(st.kind)[1].lower()
            layout.box().label(text=f"No {st.style.lower()} {label} pieces yet", icon="INFO")
        else:
            layout.prop(st, "piece")
            item = cat.find(st.kind, st.style, st.piece)
            if item and item.note:
                layout.label(text=item.note, icon="INFO")
            if item and item.extra:
                layout.prop(st, "extra", text=item.extra.label)
            layout.prop(st, "rotation")
            big = layout.row()
            big.scale_y = 1.5
            text = f"Add {naming.next_name(item.name)}" if item else "Add at Cursor"
            op = big.operator("cs_env.add_asset", text=text, icon="ADD")
            op.section, op.every = cat.section, False
        box = layout.box()
        style = st.style if cat.styled(st.kind) else "OLD"
        n = len(cat.every(style))
        box.label(text=f"Every {style.lower()} piece in a row ({n})")
        row = box.row(align=True)
        row.prop(st, "gap")
        sub = row.row()
        sub.enabled = n > 0
        op = sub.operator("cs_env.add_asset", text="Add All", icon="MOD_ARRAY")
        op.section, op.every = cat.section, True

    attrs = {"bl_label": cat.label, "bl_idname": f"CSENV_PT_{cat.section.lower()}",
             "bl_space_type": "VIEW_3D", "bl_region_type": "UI", "bl_category": cs_ui.CATEGORY,
             "poll": classmethod(poll), "draw": draw}
    return type(f"CSENV_PT_{cat.section.lower()}", (Panel,), attrs)


def _attach(context, child, parent):
    """Parent a placed attachment to its piece, keeping where it stands."""
    context.view_layer.update()
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    child.name = f"{parent.name}_{child.name}"


class CSENV_OT_add_asset(Operator):
    bl_idname = "cs_env.add_asset"
    bl_label = "Add Piece"
    bl_description = "Place the chosen piece at the 3D cursor (copies share one mesh)"
    bl_options = {"REGISTER", "UNDO"}

    section: StringProperty(options={"HIDDEN"})
    every: BoolProperty(name="Whole Style", default=False, options={"HIDDEN"},
                        description="Place every piece of the chosen style in a row")

    def execute(self, context):
        cat = _CATALOGS.get(self.section)
        if cat is None:
            return {"CANCELLED"}
        st = getattr(context.scene, cat.prop)
        if self.every:
            style = st.style if cat.styled(st.kind) else "OLD"
            items = cat.every(style)
        else:
            item = cat.find(st.kind, st.style, st.piece)
            items = [item] if item else []
        if not items:
            self.report({"WARNING"}, "Nothing to add for this choice")
            return {"CANCELLED"}
        coll = library.target_collection(context, cat.collection)
        cursor = context.scene.cursor.location.copy()
        placed, x, failed = [], 0.0, []
        for item in items:
            try:
                ob = library.place(item, cat.folder, coll, cursor, st.rotation)
                if item.extra and st.extra:
                    _attach(context, library.place(item.extra, cat.folder, coll, cursor, st.rotation), ob)
            except (OSError, LookupError) as err:
                failed.append(f"{item.label}: {err}")
                continue
            if self.every:      # line them up along X from the cursor, all standing on it
                context.view_layer.update()     # (wall and ceiling pieces too: it's a preview row)
                lo, hi = library.bounds(ob)
                ob.location.x += cursor.x + x - lo.x
                ob.location.z += cursor.z - lo.z
                x += hi.x - lo.x + st.gap
            placed.append(ob)
        for ob in context.selected_objects:
            ob.select_set(False)
        for ob in placed:
            ob.select_set(True)
        if placed:
            context.view_layer.objects.active = placed[-1]
        if failed:
            self.report({"WARNING"}, "; ".join(failed))
        else:
            self.report({"INFO"}, f"Added {len(placed)} piece(s)")
        return {"FINISHED"} if placed else {"CANCELLED"}


classes = (CSENV_OT_add_asset,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
