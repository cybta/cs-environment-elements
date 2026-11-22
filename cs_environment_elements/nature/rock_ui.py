"""Rock Generator: settings, operators and its panel in the TreeGen tab.

Like the trees, the scene holds the settings for the next Generate and every rock
object keeps its own copy: change a slider with a rock selected and it regrows.
Export uses the tree panel's folder and file layout.
"""

import os
import random

import bpy

from ..core import ui as cs_ui
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

from . import rocks
from .rocks import SURFACES, TYPES


def _owner_rock(settings):
    obj = settings.id_data
    if settings.lock or not isinstance(obj, bpy.types.Object) or not settings.is_rock:
        return None
    return obj


def _on_shape(self, context):
    obj = _owner_rock(self)
    if obj is not None:
        rocks.regrow(obj)


def _on_type(self, context):
    if self.lock:
        return
    spec = TYPES[self.rock_type]
    self.lock = True
    for k in ("size", "elongation", "flatness", "roughness", "facets", "strata", "surface"):
        setattr(self, k, spec[k])
    self.lock = False
    _on_shape(self, context)


class TreeGenRockSettings(bpy.types.PropertyGroup):
    is_rock: BoolProperty(default=False)
    lock: BoolProperty(default=False)
    tri_lod0: IntProperty(default=0)
    tri_lod1: IntProperty(default=0)
    tri_lod2: IntProperty(default=0)

    rock_type: EnumProperty(
        name="Type", items=[(k, v["label"], v["description"]) for k, v in TYPES.items()],
        default="BOULDER", update=_on_type)
    count: IntProperty(name="Variations", description="How many rocks to generate, each with its own seed",
                       default=1, min=1, max=4)
    size: FloatProperty(name="Size", description="Width of the rock (length = size x elongation)",
                        default=TYPES["BOULDER"]["size"], min=0.05, soft_max=12.0, unit="LENGTH", update=_on_shape)
    elongation: FloatProperty(name="Elongation", description="Length over width",
                              default=TYPES["BOULDER"]["elongation"], min=0.5, max=3.0, update=_on_shape)
    flatness: FloatProperty(name="Height", description="Height over width",
                            default=TYPES["BOULDER"]["flatness"], min=0.15, max=2.5, update=_on_shape)
    roughness: FloatProperty(name="Roughness", description="How lumpy the surface is",
                             default=TYPES["BOULDER"]["roughness"], min=0.0, max=0.6, subtype="FACTOR",
                             update=_on_shape)
    facets: IntProperty(name="Facets", description="Broken flat faces cut into the rock",
                        default=TYPES["BOULDER"]["facets"], min=0, max=24, update=_on_shape)
    strata: FloatProperty(name="Strata", description="Stepped layers, as in sedimentary rock. 0 = none",
                          default=0.0, min=0.0, max=1.0, subtype="FACTOR", update=_on_shape)
    surface: EnumProperty(name="Surface", items=[(k, v["label"], v["description"]) for k, v in SURFACES.items()],
                          default=TYPES["BOULDER"]["surface"], update=_on_shape)
    moss: FloatProperty(name="Moss", description="How much of the upward faces is covered in moss",
                        default=0.35, min=0.0, max=1.0, subtype="FACTOR", update=_on_shape)
    seed: IntProperty(name="Random Seed", default=1, min=0, update=_on_shape)
    detail: IntProperty(name="Detail", description="Icosphere subdivisions of LOD 0 (LOD 1 and 2 use one and "
                        "two fewer). 3 = 320, 4 = 1280, 5 = 5120 triangles",
                        default=4, min=3, max=6, update=_on_shape)
    preview_lod: EnumProperty(name="Preview", items=[(str(i), "LOD %d" % i, "") for i in range(3)],
                              default="0", update=_on_shape)


def active_rock_settings(context):
    obj = context.active_object
    if rocks.is_rock(obj):
        return obj.treegen_rock, obj
    return context.scene.treegen_rock, None


def selected_rocks(context):
    out = [o for o in context.selected_objects if rocks.is_rock(o)]
    if rocks.is_rock(context.active_object) and context.active_object not in out:
        out.append(context.active_object)
    return out


class TREEGEN_OT_rock_generate(bpy.types.Operator):
    bl_idname = "treegen.rock_generate"
    bl_label = "Generate Rocks"
    bl_description = "Generate 1 to 4 rocks from the settings shown, in a row along X at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings, _ = active_rock_settings(context)
        values = rocks.params_of(settings)
        values["preview_lod"] = settings.preview_lod
        count = context.scene.treegen_rock.count
        rng = random.Random(values["seed"])
        seeds = [values["seed"]] + [rng.randrange(1, 1000000) for _ in range(count - 1)]
        spacing = values["size"] * values["elongation"] * 1.4
        made = []
        for i, seed in enumerate(seeds):
            loc = context.scene.cursor.location.copy()
            loc.x += (i - (count - 1) / 2) * spacing
            made.append(rocks.create_rock(context, dict(values, seed=seed), loc))
        for o in context.selected_objects:
            o.select_set(False)
        for o in made:
            o.select_set(True)
        context.view_layer.objects.active = made[0]
        self.report({"INFO"}, "Generated %d rock(s)" % count)
        return {"FINISHED"}


class TREEGEN_OT_rock_seed(bpy.types.Operator):
    bl_idname = "treegen.rock_seed"
    bl_label = "Randomize Seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings, _ = active_rock_settings(context)
        settings.seed = random.randrange(1, 1000000)
        return {"FINISHED"}


class TREEGEN_OT_rock_export(bpy.types.Operator):
    bl_idname = "treegen.rock_export_fbx"
    bl_label = "Export Rock LODs (FBX)"
    bl_description = "Write LOD 0, 1 and 2 of each selected rock as FBX, centred at the origin, plus the rock textures"

    @classmethod
    def poll(cls, context):
        return bool(selected_rocks(context))

    def execute(self, context):
        folder = context.scene.treegen.export_dir
        if not folder or (folder.startswith("//") and not bpy.data.filepath):
            self.report({"ERROR"}, "Save the .blend file first, or pick an absolute export folder")
            return {"CANCELLED"}
        folder = os.path.normpath(bpy.path.abspath(folder))
        done = selected_rocks(context)
        written = rocks.export_rocks(context, done, folder, context.scene.treegen.export_layout == "PER_LOD")
        self.report({"INFO"}, "Exported %d rock(s), %d files, to %s" % (len(done), len(written), folder))
        return {"FINISHED"}


class TREEGEN_OT_rock_bake(bpy.types.Operator):
    bl_idname = "treegen.rock_bake_lods"
    bl_label = "Bake Rock LODs into Scene"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(selected_rocks(context))

    def execute(self, context):
        for obj in selected_rocks(context):
            rocks.bake_lods(obj, context)
        return {"FINISHED"}


class TREEGEN_PT_rocks(bpy.types.Panel):
    bl_label = "Rock Generator"
    bl_idname = "TREEGEN_PT_rocks"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = cs_ui.CATEGORY

    @classmethod
    def poll(cls, context):
        return cs_ui.in_section(context, "NATURE")

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        s, rock = active_rock_settings(context)
        layout.label(text=("Editing: %s" % rock.name) if rock else "New rock settings",
                     icon="OUTLINER_OB_MESH" if rock else "ADD")
        col = layout.column()
        col.prop(s, "rock_type")
        col.prop(context.scene.treegen_rock, "count", slider=True)
        row = layout.row()
        row.scale_y = 1.4
        row.operator("treegen.rock_generate", icon="MESH_ICOSPHERE")

        box = layout.box()
        box.label(text="Shape")
        col = box.column(align=True)
        for k in ("size", "elongation", "flatness"):
            col.prop(s, k)
        col.separator()
        for k in ("roughness", "facets", "strata", "surface", "moss"):
            col.prop(s, k)
        row = col.row(align=True)
        row.prop(s, "seed")
        row.operator("treegen.rock_seed", text="", icon="FILE_REFRESH")

        box = layout.box()
        box.label(text="Game LODs")
        box.row().prop(s, "preview_lod", expand=True)
        box.prop(s, "detail")
        if rock is not None:
            col = box.column(align=True)
            for i in range(3):
                col.label(text="LOD {}: {:,} triangles".format(i, getattr(s, "tri_lod%d" % i)), icon="BLANK1")
        row = box.row()
        row.scale_y = 1.3
        row.operator("treegen.rock_export_fbx", icon="EXPORT")
        box.operator("treegen.rock_bake_lods", icon="MESH_DATA")
        box.label(text="Folder and file layout: see Export in the tree panel", icon="INFO")


CLASSES = (TreeGenRockSettings, TREEGEN_OT_rock_generate, TREEGEN_OT_rock_seed, TREEGEN_OT_rock_export,
           TREEGEN_OT_rock_bake, TREEGEN_PT_rocks)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.treegen_rock = PointerProperty(type=TreeGenRockSettings)
    bpy.types.Object.treegen_rock = PointerProperty(type=TreeGenRockSettings)


def unregister():
    del bpy.types.Object.treegen_rock
    del bpy.types.Scene.treegen_rock
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
