"""Properties, operators and the TreeGen N-panel."""

import os
import random

import bpy

from ..core import ui as cs_ui
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty,
                       StringProperty)

from . import core, impostor
from .species import SPECIES, TREE_BUDGET, budget, start_values


# ----------------------------------------------------------------------------
# Property update callbacks. They only act on settings that belong to a tree
# object; the scene's copy just holds values for the next Generate.
# ----------------------------------------------------------------------------
def _tree_of(settings):
    owner = settings.id_data
    if core.is_locked() or not isinstance(owner, bpy.types.Object) or not settings.is_tree:
        return None
    return owner


def _on_structure(self, context):
    obj = _tree_of(self)
    if obj is not None:
        core.regrow(obj, context)


def _on_modifier(self, context):
    obj = _tree_of(self)
    if obj is not None:
        core.sync_modifier(obj)


def _on_budget(self, context):
    obj = _tree_of(self)
    if obj is not None:
        core.solve_budget(obj, context)


def _on_species(self, context):
    if core.is_locked():
        return
    with core.locked():
        for name, value in start_values(self.species, self.hero).items():
            setattr(self, name, value)
        self.tri_min, self.tri_max = budget(self.species, self.hero)
    _on_structure(self, context)


def _on_hero(self, context):
    """Hero on/off: the budget changes; a species with hero sizes (the cedar) also
    switches between its hero and ordinary sizes."""
    if core.is_locked():
        return
    resize = "hero_size" in SPECIES[self.species]
    with core.locked():
        self.tri_min, self.tri_max = budget(self.species, self.hero)
        if resize:
            for name, value in start_values(self.species, self.hero).items():
                setattr(self, name, value)
    (_on_structure if resize else _on_budget)(self, context)


class TreeGenSettings(bpy.types.PropertyGroup):
    is_tree: BoolProperty(default=False)
    budget_trim: FloatProperty(default=1.0)
    leaf_trim: FloatProperty(default=1.0)
    tri_count: IntProperty(default=0)
    tri_lod1: IntProperty(default=0)
    tri_lod2: IntProperty(default=0)

    species: EnumProperty(
        name="Species",
        items=[(key, spec["label"], spec["description"]) for key, spec in SPECIES.items()],
        default="CEDAR", update=_on_species)
    hero: BoolProperty(
        name="Hero Tree",
        description="A landmark tree seen up close: LOD 0 gets 25,000 to 50,000 triangles instead "
                    "of 500 to 3,000, and the LOD 3 impostor four crossed planes (8 views) instead of two",
        default=False, update=_on_hero)
    count: IntProperty(
        name="Variations", description="How many trees to generate, each with its own seed",
        default=1, min=1, max=4)

    height: FloatProperty(
        name="Tree Height", description="Total height of the tree",
        default=SPECIES["CEDAR"]["height"], min=0.2, soft_max=40.0, unit="LENGTH", update=_on_structure)
    bole: FloatProperty(
        name="Bare Trunk Length", description="Height from the ground to the first branches",
        default=SPECIES["CEDAR"]["bole"], min=0.0, soft_max=15.0, unit="LENGTH", update=_on_structure)
    canopy: FloatProperty(
        name="Canopy Diameter", description="Maximum horizontal spread of the crown",
        default=SPECIES["CEDAR"]["canopy"], min=0.2, soft_max=40.0, unit="LENGTH", update=_on_structure)
    trunk_radius: FloatProperty(
        name="Trunk Base Radius", description="Radius of the trunk at ground level",
        default=SPECIES["CEDAR"]["trunk_radius"], min=0.02, soft_max=3.0, unit="LENGTH",
        update=_on_structure)
    density: FloatProperty(
        name="Branch Density", description="Multiplier on the number of branches",
        default=1.0, min=0.3, max=2.5, update=_on_structure)
    leaf_scale: FloatProperty(
        name="Leaf Scale", description="Size multiplier for the foliage cards",
        default=1.0, min=0.1, soft_max=3.0, update=_on_modifier)
    flowers: IntProperty(
        name="Flowers", description="Number of flowers on a bush. 0 gives a plain leafy bush",
        default=12, min=0, soft_max=60, update=_on_structure)
    seed: IntProperty(
        name="Random Seed", default=1, min=0, update=_on_structure)

    strands: IntProperty(
        name="Trunk Strands",
        description="Root-to-limb strands wound round the trunk: each starts as a root, runs up "
                    "the trunk as a flute and leaves as a main limb. 0 gives a plain round trunk",
        default=6, min=0, max=12, update=_on_structure)
    fluting: FloatProperty(
        name="Fluting", description="How far the strands stand out from the trunk",
        default=0.6, min=0.0, max=1.0, subtype="FACTOR", update=_on_structure)
    root_length: FloatProperty(
        name="Root Length", description="Multiplier on the surface roots. 0 removes them",
        default=1.0, min=0.0, soft_max=3.0, update=_on_structure)
    twist: FloatProperty(
        name="Twist", description="How far the tree turns about its trunk from ground to crown",
        default=SPECIES["CEDAR"]["twist"], soft_min=-6.2832, soft_max=6.2832, subtype="ANGLE",
        update=_on_structure)
    lean: FloatProperty(
        name="Lean", description="Slope of the trunk at the top. Foliage stays level",
        default=SPECIES["CEDAR"]["lean"], min=0.0, max=1.0472, subtype="ANGLE", update=_on_structure)
    lean_dir: FloatProperty(
        name="Lean Direction", description="Compass direction the tree leans towards",
        default=0.0, soft_min=-3.14159, soft_max=3.14159, subtype="ANGLE", update=_on_structure)
    gnarl: FloatProperty(
        name="Gnarl", description="How much the trunk, strands, limbs and roots wander",
        default=0.5, min=0.0, max=1.0, subtype="FACTOR", update=_on_structure)
    limb_droop: FloatProperty(
        name="Limb Droop", description="How much the lower limbs sag towards their tips",
        default=0.5, min=0.0, soft_max=2.0, update=_on_structure)

    flare: FloatProperty(
        name="Branch Flare", description="How much limbs and branches swell where they leave "
                                         "the trunk, so they blend in instead of poking out",
        default=0.6, min=0.0, max=1.5, subtype="FACTOR", update=_on_structure)

    preview_lod: EnumProperty(
        name="Preview",
        description="Which game LOD to show in the viewport. Export always writes all three",
        items=[("0", "LOD 0", "Hero detail: full twigs and dense foliage"),
               ("1", "LOD 1", "Mid detail: fewer twigs, fewer and larger foliage cards"),
               ("2", "LOD 2", "Far detail: trunk and main limbs, a few large cards")],
        default="0", update=_on_modifier)

    tri_min: IntProperty(
        name="Min", description="Lowest acceptable LOD 0 triangle count",
        default=TREE_BUDGET[0], min=0, soft_max=200000, update=_on_budget)
    tri_max: IntProperty(
        name="Max", description="Highest acceptable LOD 0 triangle count",
        default=TREE_BUDGET[1], min=0, soft_max=200000, update=_on_budget)

    # Export settings (only the scene's copy is used).
    export_dir: StringProperty(
        name="Folder", description="Where the FBX files and leaf textures are written",
        default="//treegen_export/", subtype="DIR_PATH")
    export_layout: EnumProperty(
        name="Files",
        items=[("PER_TREE", "One FBX per Tree",
                "Tree_LOD0, Tree_LOD1, ... in one file. Unity builds the LOD Group from these names"),
               ("PER_LOD", "One FBX per LOD",
                "Tree_LOD0.fbx, Tree_LOD1.fbx, ..., e.g. for importing LOD levels one by one in Unreal")],
        default="PER_TREE")
    impostor_size: EnumProperty(
        name="Impostor",
        description="Size of each view in the LOD 3 texture. An ordinary tree has two views side by "
                    "side, a hero tree four in a 2 x 2 grid",
        items=[("256", "256 px per view", "Small: 512 x 256 for a tree, 512 x 512 for a hero tree"),
               ("512", "512 px per view", "1024 x 512 for a tree, 1024 x 1024 for a hero tree"),
               ("1024", "1024 px per view", "2048 x 1024 for a tree, 2048 x 2048 for a hero tree")],
        default="512")


def active_settings(context):
    """The selected tree's settings, or the scene's settings for the next new tree."""
    obj = context.active_object
    if core.is_tree(obj):
        return obj.treegen, obj
    return context.scene.treegen, None


def selected_trees(context):
    trees = [obj for obj in context.selected_objects if core.is_tree(obj)]
    if core.is_tree(context.active_object) and context.active_object not in trees:
        trees.append(context.active_object)
    return trees


# ----------------------------------------------------------------------------
# Operators
# ----------------------------------------------------------------------------
class TREEGEN_OT_generate(bpy.types.Operator):
    bl_idname = "treegen.generate"
    bl_label = "Generate"
    bl_description = "Generate 1 to 4 trees or bushes from the settings shown, spaced out along X at the 3D cursor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings, _ = active_settings(context)
        values = {name: getattr(settings, name) for name in core.COPIED_PROPS}
        count = context.scene.treegen.count
        rng = random.Random(values["seed"])
        seeds = [values["seed"]] + [rng.randrange(1, 1000000) for _ in range(count - 1)]
        spacing = values["canopy"] * 1.15
        origin = context.scene.cursor.location

        trees = []
        for i, seed in enumerate(seeds):
            location = origin.copy()
            location.x += (i - (count - 1) / 2) * spacing
            trees.append(core.create_tree(context, dict(values, seed=seed), location))

        for obj in context.selected_objects:
            obj.select_set(False)
        for obj in trees:
            obj.select_set(True)
        context.view_layer.objects.active = trees[0]
        self.report({"INFO"}, "Generated %d tree(s)" % count)
        return {"FINISHED"}


class TREEGEN_OT_random_seed(bpy.types.Operator):
    bl_idname = "treegen.random_seed"
    bl_label = "Randomize Seed"
    bl_description = "Pick a new random seed"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        settings, _ = active_settings(context)
        settings.seed = random.randrange(1, 1000000)
        return {"FINISHED"}


class TREEGEN_OT_export(bpy.types.Operator):
    bl_idname = "treegen.export_fbx"
    bl_label = "Export LODs (FBX)"
    bl_description = ("Write LOD 0, 1 and 2 of each selected tree as FBX, centred at the origin, with "
                      "foliage as real geometry, plus the leaf textures. Trees also get LOD 3: two "
                      "crossed planes with a texture rendered from the tree")

    @classmethod
    def poll(cls, context):
        return bool(selected_trees(context))

    def execute(self, context):
        folder = context.scene.treegen.export_dir
        if not folder:
            self.report({"ERROR"}, "Pick an export folder first")
            return {"CANCELLED"}
        if folder.startswith("//") and not bpy.data.filepath:
            self.report({"ERROR"}, "Save the .blend file first, or pick an absolute export folder")
            return {"CANCELLED"}
        folder = os.path.normpath(bpy.path.abspath(folder))
        trees = selected_trees(context)
        written = core.export_trees(context, trees, folder,
                                    context.scene.treegen.export_layout == "PER_LOD")
        self.report({"INFO"}, "Exported %d tree(s), %d files, to %s" % (len(trees), len(written), folder))
        return {"FINISHED"}


class TREEGEN_OT_bake(bpy.types.Operator):
    bl_idname = "treegen.bake_lods"
    bl_label = "Bake LODs into Scene"
    bl_description = ("Add the LODs of each selected tree (0-2, and the LOD 3 impostor) to the scene "
                      "as ordinary meshes, to inspect or hand-edit before exporting yourself")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(selected_trees(context))

    def execute(self, context):
        trees = selected_trees(context)
        for obj in trees:
            core.bake_lods(obj, context)
        self.report({"INFO"}, "Baked the LODs of %d tree(s)" % len(trees))
        return {"FINISHED"}


# ----------------------------------------------------------------------------
# Panel
# ----------------------------------------------------------------------------
class TREEGEN_PT_panel(bpy.types.Panel):
    bl_label = "Tree Generator"
    bl_idname = "TREEGEN_PT_panel"
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
        settings, tree = active_settings(context)
        scene_settings = context.scene.treegen

        if tree is not None:
            layout.label(text="Editing: %s" % tree.name, icon="OUTLINER_OB_MESH")
        else:
            layout.label(text="New tree settings", icon="ADD")

        col = layout.column()
        col.prop(settings, "species")
        if not SPECIES[settings.species].get("bush"):
            col.prop(settings, "hero")
        col.prop(scene_settings, "count", slider=True)
        row = layout.row()
        row.scale_y = 1.4
        row.operator("treegen.generate", icon="OUTLINER_OB_FORCE_FIELD")

        if SPECIES[settings.species].get("bush"):
            self.draw_bush(layout, settings)
        else:
            self.draw_tree(layout, settings, tree)
        self.draw_output(layout, settings, scene_settings, tree)

    def draw_bush(self, layout, settings):
        box = layout.box()
        box.label(text="Bush")
        col = box.column(align=True)
        col.prop(settings, "height", text="Height")
        col.prop(settings, "canopy", text="Width")
        col.separator()
        col.prop(settings, "density", text="Leaf Density")
        col.prop(settings, "leaf_scale")
        col.prop(settings, "flowers")
        row = col.row(align=True)
        row.prop(settings, "seed")
        row.operator("treegen.random_seed", text="", icon="FILE_REFRESH")

    def draw_tree(self, layout, settings, tree):
        box = layout.box()
        box.label(text="Dimensions")
        col = box.column(align=True)
        col.prop(settings, "height")
        col.prop(settings, "bole")
        col.prop(settings, "canopy")
        col.prop(settings, "trunk_radius")

        box = layout.box()
        box.label(text="Structure")
        col = box.column(align=True)
        col.prop(settings, "density")
        col.prop(settings, "leaf_scale")
        row = col.row(align=True)
        row.prop(settings, "seed")
        row.operator("treegen.random_seed", text="", icon="FILE_REFRESH")

        box = layout.box()
        box.label(text="Trunk & Limbs")
        col = box.column(align=True)
        if settings.species == "CEDAR":
            col.prop(settings, "strands")
            sub = col.column(align=True)
            sub.active = settings.strands > 0
            sub.prop(settings, "fluting")
            col.prop(settings, "root_length")
            col.separator()
        col.prop(settings, "twist")
        col.prop(settings, "lean")
        sub = col.column(align=True)
        sub.active = settings.lean > 0.0
        sub.prop(settings, "lean_dir")
        col.separator()
        col.prop(settings, "gnarl")
        col.prop(settings, "limb_droop")
        col.prop(settings, "flare")
        if tree is not None:
            hint = box.column(align=True)
            hint.scale_y = 0.8
            hint.label(text="Edit Mode moves the skeleton by hand.", icon="INFO")
            hint.label(text="Sliders above regrow it and drop those edits.", icon="BLANK1")

    def draw_output(self, layout, settings, scene_settings, tree):
        box = layout.box()
        box.label(text="Game LODs")
        row = box.row()
        row.prop(settings, "preview_lod", expand=True)
        col = box.column(align=True)
        col.label(text="LOD 0 Triangle Budget")
        col.prop(settings, "tri_min")
        col.prop(settings, "tri_max")
        if tree is not None:
            inside = settings.tri_min <= settings.tri_count <= max(settings.tri_max, settings.tri_min)
            col = box.column(align=True)
            col.label(text="LOD 0: {:,} triangles".format(settings.tri_count),
                      icon="CHECKMARK" if inside else "ERROR")
            col.label(text="LOD 1: {:,} triangles".format(settings.tri_lod1), icon="BLANK1")
            col.label(text="LOD 2: {:,} triangles".format(settings.tri_lod2), icon="BLANK1")
            if core.has_impostor(tree):
                col.label(text="LOD 3: %d triangles (impostor, made on export)"
                          % impostor.triangles(core.impostor_planes(tree)), icon="BLANK1")
            if not inside:
                col.label(text="Budget is outside what this tree can reach")

        box = layout.box()
        box.label(text="Export to Game Engine")
        col = box.column()
        col.prop(scene_settings, "export_dir")
        col.prop(scene_settings, "export_layout")
        col.prop(scene_settings, "impostor_size")
        row = box.row()
        row.scale_y = 1.3
        row.operator("treegen.export_fbx", icon="EXPORT")
        box.operator("treegen.bake_lods", icon="MESH_DATA")


CLASSES = (TreeGenSettings, TREEGEN_OT_generate, TREEGEN_OT_random_seed, TREEGEN_OT_export,
           TREEGEN_OT_bake, TREEGEN_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.treegen = PointerProperty(type=TreeGenSettings)
    bpy.types.Object.treegen = PointerProperty(type=TreeGenSettings)


def unregister():
    del bpy.types.Object.treegen
    del bpy.types.Scene.treegen
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
