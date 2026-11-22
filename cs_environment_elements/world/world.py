"""World generator: the whole map in one go (panel "World" in the House tab).

Order: plan (world_layout) -> terrain (heights, splat, meshes, water, collider) ->
roads and bridges -> buildings and fences on every plot + the shops -> parks and
playgrounds -> tree library, forest, garden trees, rocks -> the hero cedar. Optionally
writes the heightmap, splatmap and a placement list for the game engine.

Everything lands in the "World" collection; rebuilding deletes it first.
"""

import json
import os
import random
import time

import bpy

from ..core import ui as cs_ui
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup

from . import world_layout as wl
from . import world_materials as wm
from . import world_nature as wn
from . import world_parks as wp
from . import world_roads as wr
from . import world_sites as ws
from . import world_terrain as wt

ROOT = "World"
SUBS = ("Terrain", "Roads", "Poor District", "Mid District", "Villas", "Shops", "Parks", "Trees",
        "Rocks", "Hero", "Library")

_last = {}          # the last build's terrain, kept for Export without a rebuild


class WORLD_Settings(PropertyGroup):
    seed: IntProperty(name="Seed", default=1, min=0, description="Changes the plots, buildings, trees and hills")
    house_density: FloatProperty(name="House Density", default=1.0, min=0.3, max=1.5,
                                 description="Fewer empty lots and smaller gaps between plots when higher")
    forest: FloatProperty(name="Forest (trees/ha)", default=55.0, min=0.0, max=120.0,
                          description="Trees per hectare outside the town")
    resolution: EnumProperty(name="Heightmap", default="1025", items=[
        ("513", "513 px", "2.7 m per pixel"), ("1025", "1025 px", "1.4 m per pixel"),
        ("2049", "2049 px", "0.7 m per pixel")])
    mesh_step: FloatProperty(name="Terrain Mesh Step (m)", default=4.0, min=1.0, max=10.0,
                             description="Grid spacing of the terrain mesh in Blender")
    buildings: BoolProperty(name="Buildings", default=True)
    fences: BoolProperty(name="Fences", default=True)
    trees: BoolProperty(name="Trees (TreeGen)", default=True)
    rocks: BoolProperty(name="Rocks", default=True)
    parks: BoolProperty(name="Parks & Playgrounds", default=True)
    hero: BoolProperty(name="Hero Cedar", default=True)
    playground_dir: StringProperty(name="Playground Models", subtype="DIR_PATH", default=wp.PLAYGROUND_DIR)
    export_dir: StringProperty(name="Export Folder", subtype="DIR_PATH", default="//world_export",
                               description="Heightmap, splatmap and placement list for the game engine")
    export_on_build: BoolProperty(name="Export After Build", default=True)


def _collections(context):
    from ..core.scene_utils import _delete_collection
    old = bpy.data.collections.get(ROOT)
    if old is not None and old.get("roomgen_world"):
        _delete_collection(old)
    root = bpy.data.collections.new(ROOT)
    root["roomgen_world"] = True
    context.scene.collection.children.link(root)
    subs = {}
    for name in SUBS:
        c = bpy.data.collections.new(f"{ROOT} {name}")
        root.children.link(c)
        subs[name] = c
    for name in ("Forest", "Town"):
        c = bpy.data.collections.new(f"{ROOT} Trees {name}")
        subs["Trees"].children.link(c)
        subs["Trees " + name] = c
    return root, subs


def _exclude(context, coll):
    def walk(lc):
        if lc.collection == coll:
            lc.exclude = True
            return True
        return any(walk(c) for c in lc.children)
    walk(context.view_layer.layer_collection)


def build(context, cfg, log=print):
    t0 = time.time()
    rng = random.Random(cfg.seed)
    scene = context.scene
    scene.cursor.location = (0, 0, 0)
    context.view_layer.active_layer_collection = context.view_layer.layer_collection
    root, C = _collections(context)
    stats = {}

    L = wl.make_layout(cfg.seed, cfg.house_density)
    T = wt.Terrain(L, int(cfg.resolution), cfg.mesh_step).compute()
    splat = T.splat()
    img = wt.splat_image(splat)
    wt.build_meshes(T, C["Terrain"], wm.terrain(img), wm.water())
    wt.build_collider(C["Terrain"])
    log(f"terrain {time.time() - t0:.1f}s")

    street = wr.build(L, T, C["Roads"], rng, C["Library"])
    stats["lamps"] = len(street["lamps"])
    log(f"roads {time.time() - t0:.1f}s")

    sites = None
    if cfg.buildings:
        colls = {"POOR": C["Poor District"], "MID": C["Mid District"], "VILLA": C["Villas"], "SHOPS": C["Shops"]}
        sites = ws.Sites(context, L, T, colls, C["Library"], rng, fences=cfg.fences)
        for i, plot in enumerate(L.plots):
            sites.plot(plot, i)
        for z in L.zones:
            if z.kind == "SHOPS":
                sites.shops(z)
        sites.finish(C["Roads"])
        stats["buildings"] = len(sites.buildings)
        log(f"buildings {time.time() - t0:.1f}s")

    tree_spots = [t for p in L.plots for t in p.trees]
    props = None
    if cfg.parks:
        folder = bpy.path.abspath(cfg.playground_dir) if cfg.playground_dir else wp.PLAYGROUND_DIR
        props = wp.build(L, T, C["Parks"], C["Library"], rng, tree_spots, folder)
        stats["props"] = len(props.placed)
        if props.missing:
            log("playground models not found: " + ", ".join(props.missing))

    if cfg.trees:
        lib = wn.build_library(context, C["Library"], rng, log)
        stats["trees"] = wn.scatter(L, T, lib, C["Trees Forest"], C["Trees Town"], rng, cfg.forest, tree_spots)
        log(f"trees {time.time() - t0:.1f}s")
    if cfg.rocks:
        stats["rocks"] = wn.rocks(L, T, C["Rocks"], C["Library"], rng)
    if cfg.hero:
        wn.hero_cedar(context, L, T, C["Hero"], cfg.seed + 1)

    _exclude(context, C["Library"])
    root["seed"] = cfg.seed
    _last.update(layout=L, terrain=T, splat=splat)
    if cfg.export_on_build:
        stats["exported"] = export(context, cfg)
    stats["seconds"] = round(time.time() - t0, 1)
    return stats


# --------------------------------------------------------------------------
# Export for the game engine
# --------------------------------------------------------------------------

def _xf(ob):
    m = ob.matrix_world
    loc, rot, scale = m.to_translation(), m.to_euler(), m.to_scale()
    return {"name": ob.name, "pos": [round(v, 3) for v in loc], "rot_deg": [round(v * 57.29578, 2) for v in rot],
            "scale": [round(v, 3) for v in scale]}


def export(context, cfg):
    folder = bpy.path.abspath(cfg.export_dir)
    if not folder or folder.startswith("//"):
        folder = os.path.join(os.path.expanduser("~"), "world_export")
    T = _last.get("terrain")
    if T is None:
        return []
    files = wt.export_maps(T, folder, _last.get("splat"))
    world = bpy.data.collections.get(ROOT)
    data = {"buildings": [], "fences": [], "trees": [], "rocks": [], "props": [], "lamps": [], "poles": [],
            "hero_tree": None}
    if world is not None:
        for ob in world.all_objects:
            if ob.type == "EMPTY" and ob.get("building_type"):
                d = _xf(ob)
                d["type"] = ob["building_type"]
                d["district"] = ob.get("world_district", "")
                data["buildings"].append(d)
            elif ob.type == "EMPTY" and ob.get("lod_cards") is not None and ob.parent is None:
                data["fences"].append(_xf(ob))
            elif ob.instance_type == "COLLECTION" and ob.get("tree_variant"):
                d = _xf(ob)
                d["variant"] = ob["tree_variant"]
                data["trees"].append(d)
            elif ob.name.startswith("Rock_") and (ob.type == "MESH" or ob.get("rock_variant")):
                d = _xf(ob)
                d["variant"] = ob.get("rock_variant") or ob.data.name
                data["rocks"].append(d)
            elif ob.name.startswith("Lamp_"):
                data["lamps"].append(_xf(ob))
            elif ob.name.startswith("Pole_"):
                data["poles"].append(_xf(ob))
            elif ob.get("world_part") == "hero_tree":
                data["hero_tree"] = _xf(ob)
            elif ob.parent is None and ob.type == "MESH" and any(ob.name.startswith(k) for k in (
                    "SwingSet", "PlaygroundSlide", "SeesawBase", "MerryGoRoundBase", "PlaygroundBench", "PlaygroundBin")):
                d = _xf(ob)
                d["model"] = ob.name.split(".")[0]
                data["props"].append(d)
    path = os.path.join(folder, "placements.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    return files + ["placements.json"]


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

class WORLD_OT_build(Operator):
    bl_idname = "world_gen.build"
    bl_label = "Build World"
    bl_description = ("Build the whole map: terrain with a mountain rim, river and lake, old and new roads, "
                      "cottages, houses, villas and shops with fences, parks with the old playgrounds, the "
                      "forest and the hero cedar on its mountain (takes a few minutes)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.house_gen
        keep = {k: getattr(s, k) for k in s.bl_rna.properties.keys()
                if k not in ("rna_type", "name", "section", "villa_style", "shop", "fence")}
        keep_sub = {sub: {k: getattr(getattr(s, sub), k) for k in getattr(s, sub).bl_rna.properties.keys()
                          if k not in ("rna_type", "name")} for sub in ("shop", "fence")}
        try:
            stats = build(context, context.scene.world_gen)
        finally:
            for k, v in keep.items():
                try:
                    setattr(s, k, v)
                except (AttributeError, TypeError):
                    pass
            for sub, vals in keep_sub.items():
                for k, v in vals.items():
                    try:
                        setattr(getattr(s, sub), k, v)
                    except (AttributeError, TypeError):
                        pass
        self.report({"INFO"}, "World: " + ", ".join(f"{k} {v if not isinstance(v, list) else len(v)}"
                                                    for k, v in stats.items()))
        return {"FINISHED"}


class WORLD_OT_export(Operator):
    bl_idname = "world_gen.export"
    bl_label = "Export Map Data"
    bl_description = "Write heightmap.png/.r16, splatmap.png, terrain.json and placements.json"

    @classmethod
    def poll(cls, context):
        return "terrain" in _last

    def execute(self, context):
        files = export(context, context.scene.world_gen)
        self.report({"INFO"}, f"Wrote {len(files)} files to {bpy.path.abspath(context.scene.world_gen.export_dir)}")
        return {"FINISHED"}


class WORLD_PT_panel(Panel):
    bl_label = "World"
    bl_idname = "WORLD_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = cs_ui.CATEGORY

    @classmethod
    def poll(cls, context):
        return cs_ui.in_section(context, "WORLD")
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        c = context.scene.world_gen
        col = self.layout.column(align=True)
        for k in ("seed", "house_density", "forest"):
            col.prop(c, k)
        col = self.layout.column(align=True)
        col.prop(c, "resolution")
        col.prop(c, "mesh_step")
        box = self.layout.box()
        grid = box.grid_flow(columns=2, align=True)
        for k in ("buildings", "fences", "parks", "trees", "rocks", "hero"):
            grid.prop(c, k)
        box.prop(c, "playground_dir")
        if c.trees and wn.treegen() is None:
            box.label(text="TreeGen add-on not installed: no trees", icon="ERROR")
        box = self.layout.box()
        box.prop(c, "export_dir")
        row = box.row(align=True)
        row.prop(c, "export_on_build")
        row.operator("world_gen.export", text="", icon="EXPORT")
        row = self.layout.row()
        row.scale_y = 1.6
        row.operator("world_gen.build", icon="WORLD")


classes = (WORLD_Settings, WORLD_OT_build, WORLD_OT_export, WORLD_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.world_gen = bpy.props.PointerProperty(type=WORLD_Settings)


def unregister():
    del bpy.types.Scene.world_gen
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
