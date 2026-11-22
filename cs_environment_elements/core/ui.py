"""The one sidebar tab every section lives in, and the section switch at its top.

Each section's top-level panel calls `in_section(context, KEY)` from its poll, so only
the chosen section's panels show. Sub-panels follow their parent automatically.
"""

import bpy
from bpy.props import EnumProperty, PointerProperty
from bpy.types import Panel, PropertyGroup

CATEGORY = "CS Env"

SECTIONS = [
    ("NATURE", "Nature", "Trees, bushes and rocks", "OUTLINER_OB_FORCE_FIELD", 0),
    ("BUILDINGS", "Buildings", "Houses, villas, cottages, shopping rows, fences and their LODs", "HOME", 1),
    ("PROPS", "Props", "Outdoor props: playground, benches, street lamps, poles", "OUTLINER_OB_LIGHT", 2),
    ("INTERIOR", "Interior", "Furniture, old and new styles", "OUTLINER_OB_GROUP_INSTANCE", 3),
    ("WORLD", "World", "The whole map: terrain, roads, districts, parks and nature", "WORLD", 4),
]

# Shown for a section whose tools are not built yet.
_PLANNED = {}


def in_section(context, key):
    st = getattr(context.scene, "cs_env", None)
    return st is not None and st.section == key


class CSENV_Settings(PropertyGroup):
    section: EnumProperty(name="Section", description="Which group of generators to show",
                          items=SECTIONS, default="BUILDINGS")


class CSENV_PT_root(Panel):
    bl_label = "CS Environment"
    bl_idname = "CSENV_PT_root"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY

    def draw(self, context):
        st = context.scene.cs_env
        col = self.layout.column(align=True)
        col.scale_y = 1.2
        col.prop(st, "section", expand=True)
        lines = _PLANNED.get(st.section)
        if lines:
            box = self.layout.box()
            for i, line in enumerate(lines):
                box.label(text=line, icon="INFO" if i == 0 else "BLANK1")


classes = (CSENV_Settings, CSENV_PT_root)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.cs_env = PointerProperty(type=CSENV_Settings)


def unregister():
    del bpy.types.Scene.cs_env
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
