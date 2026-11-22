"""A small cottage garden, built only from the add-on (cs_environment_elements):

  - an old painted cottage in a 22 x 19 m plot behind an old wooden fence (door + gate on
    the street side), a gravel path to the front door
  - a gravel road in front, an old electric pole with the street lamp on the verge, a
    wheelie bin by the gate
  - the garden: firewood shed, clothesline with laundry + basket + wash tub, slat table,
    plank bench, stool and the old wingback armchair round it, wheelbarrows, shovel, fork,
    hose, watering can, crates, concrete blocks, a gravel heap
  - a few trees and bushes from the tree generator

Run headless:  blender -b --factory-startup --python make_cottage_garden.py
Writes out/cottage_garden.blend and out/cottage_garden*.png beside this script
(RENDER=0 skips the renders).
"""
import math, os, random, sys

import bpy, bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out")
sys.path.insert(0, ROOT)

bpy.ops.wm.read_factory_settings(use_empty=True)
import cs_environment_elements as pkg                                   # noqa: E402
pkg.register()
from cs_environment_elements.buildings import fence_build as fb, house  # noqa: E402
from cs_environment_elements.buildings.fence_paint import PALETTE, quiet as fence_quiet  # noqa: E402
from cs_environment_elements.core import library, naming                # noqa: E402
from cs_environment_elements.core import neighborhood_materials as nm   # noqa: E402
from cs_environment_elements.core.materials import _uv_metric           # noqa: E402
from cs_environment_elements.core.paint import quiet as paint_quiet     # noqa: E402
from cs_environment_elements.interior import CATALOG as INTERIOR        # noqa: E402
from cs_environment_elements.nature import core as tree_core            # noqa: E402
from cs_environment_elements.props import CATALOG as PROPS              # noqa: E402

ctx = bpy.context
sc = ctx.scene
rng = random.Random(7)

PLOT = (-11.0, -7.4, 11.0, 12.0)            # x0, y0 (street side), x1, y1
ROAD_Y, ROAD_W = -10.4, 4.2
GATE_X = 7.0


def collection(name):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if c.name not in sc.collection.children:
        sc.collection.children.link(c)
    return c


def place(cat, kind, piece, at, rot=0.0, style=None, extra=False, coll="Garden"):
    item = next(it for st in ("OLD", "NEW", "ANY") for it in cat.items(kind, style or st) if it.key == piece)
    target = collection(coll)
    ob = library.place(item, cat.folder, target, Vector(at), rot)
    if extra and item.extra:
        att = library.place(item.extra, cat.folder, target, Vector(at), rot)
        ctx.view_layer.update()
        att.parent = ob
        att.matrix_parent_inverse = ob.matrix_world.inverted()
    return ob


def ground_box(name, x0, y0, x1, y1, z0, z1, mat_name):
    """A flat slab with metric UVs in a neighborhood material (grass, gravel, dirt)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(nm.ensure(mat_name))
    _uv_metric(me, nm.uv_scale)
    ob = bpy.data.objects.new(name, me)
    collection("Ground").objects.link(ob)
    return ob


# ---------------------------------------------------------------- ground and road
ground_box("Grass", -30, -25, 30, 30, -0.1, 0.0, "C_grass")
ground_box("Road", -30, ROAD_Y - ROAD_W / 2, 30, ROAD_Y + ROAD_W / 2, -0.02, 0.025, "C_world_gravel")
for s in (-1, 1):
    ground_box("Verge", -30, ROAD_Y + s * ROAD_W / 2 - 0.45, 30, ROAD_Y + s * ROAD_W / 2 + 0.45, -0.02, 0.012,
               "C_world_dirt")

# ---------------------------------------------------------------- the cottage
s = sc.house_gen
s.building_type = "COTTAGE"
s.cottage_style = "PAINTED"
s.add_labels, s.add_lights, s.add_inserts = False, False, True
s.seed = 4127
s.total_area, s.bedrooms, s.bathrooms = 64.0, 2, 0
with paint_quiet():
    for k in ("cottage_roof", "cottage_paint", "cottage_siding"):
        setattr(s, k, "RANDOM")
    s.cottage_peel, s.cottage_roof_peel = 0.35, 0.4
s.cottage_chimney = True
s.house_name = "cottage-1"
sc.cursor.location = (0, 0, 0)
plan = house._build(ctx, s, lambda *a: None, name="cottage-1", site=True)
root = bpy.data.objects["cottage-1"]
ctx.view_layer.update()
lo, hi = library.bounds(root)
root.location += Vector((-4.0 - (lo.x + hi.x) / 2, -2.4 - lo.y, 0.0))     # front 5 m behind the fence
ctx.view_layer.update()
ent = next((o for o in plan.floors[0].openings if o.kind == "ENTRANCE"), None)
if ent is not None:
    m = (ent.s0 + ent.s1) / 2
    local = Vector((m - plan.W / 2, ent.coord - plan.D / 2, 0)) if ent.axis == "X" else \
        Vector((ent.coord - plan.W / 2, m - plan.D / 2, 0))
    door_x = (root.matrix_world @ local).x
else:
    door_x = -4.0
lo, hi = library.bounds(root)
ground_box("Path", door_x - 0.6, PLOT[1], door_x + 0.6, lo.y + 0.3, -0.02, 0.03, "C_world_gravel")
ground_box("Drive", GATE_X - 1.6, PLOT[1], GATE_X + 1.6, PLOT[1] + 4.0, -0.02, 0.02, "C_world_gravel")

# ---------------------------------------------------------------- the fence round the plot
x0, y0, x1, y1 = PLOT
me = bpy.data.meshes.new("Plot")
me.from_pydata([(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)], [(0, 1), (1, 2), (2, 3), (3, 0)], [])
outline = bpy.data.objects.new("Plot Outline", me)
collection("Plot Outline").objects.link(outline)
g = s.fence
g.style, g.seed, g.flip, g.skip_sides = "OLD", 31, False, ""
g.height, g.uneven, g.gap = 1.5, 0.04, 0.06
with fence_quiet():
    g.paint, g.paint_color, g.peel = True, PALETTE[0][1], 0.55
g.outline = outline
g.door, g.door_side, g.door_pos, g.door_width = True, 1, (door_x - x0) / (x1 - x0), 1.0
g.gate, g.gate_side, g.gate_pos, g.gate_width, g.gate_leaves = True, 1, (GATE_X - x0) / (x1 - x0), 3.2, 2
fb.build(ctx, g, outline, fb.outline_chains(outline, ctx, sync_edit=False), name=naming.next_name("fence-old"))
plot_coll = collection("Plot Outline"); plot_coll.hide_viewport = plot_coll.hide_render = True

# ---------------------------------------------------------------- outside: pole, bin
place(PROPS, "POLES", "pole_old_2arm", (-8.5, y0 - 0.9, 0), rot=math.pi / 2, extra=True, coll="Street")   # lamp over the road
place(PROPS, "BINS", "wheelie_bin_green", (GATE_X + 2.4, y0 - 0.55, 0), coll="Street")
place(PROPS, "BINS", "wheelie_bin_black", (GATE_X + 3.1, y0 - 0.6, 0), rot=0.1, coll="Street")

# ---------------------------------------------------------------- the garden
place(PROPS, "YARD", "woodshed_old", (6.0, y1 - 1.1, 0))                                # against the back fence
place(PROPS, "YARD", "clothesline_laundry", (6.0, 3.6, 0))
place(PROPS, "YARD", "laundry_basket", (4.6, 2.5, 0), rot=0.4)
place(PROPS, "YARD", "wash_tub", (7.8, 2.4, 0), rot=-0.3)
# sitting corner in the front garden, left of the drive
place(PROPS, "YARD", "yard_table_old", (2.6, -4.4, 0), rot=0.05)
place(PROPS, "YARD", "yard_bench_old", (2.6, -3.4, 0), rot=math.pi + 0.05)
place(PROPS, "YARD", "yard_stool_old", (3.8, -5.0, 0))
place(INTERIOR, "SOFA", "old_armchair", (1.1, -4.7, 0), rot=-math.pi / 2 + 0.25, coll="Garden")
# work things round the shed and the house
place(PROPS, "GARDEN", "wheelbarrow", (2.9, y1 - 2.4, 0), rot=0.7)
place(PROPS, "GARDEN", "garden_shovel", (3.9, y1 - 0.6, 0), rot=0.2)
place(PROPS, "GARDEN", "garden_fork", (4.2, y1 - 0.55, 0), rot=-0.15)
place(PROPS, "GARDEN", "garden_hose", (0.4, -1.6, 0), rot=0.5)
place(PROPS, "GARDEN", "watering_can", (1.2, -2.0, 0), rot=2.2)
place(PROPS, "GARDEN", "wooden_crate", (-9.6, y1 - 0.9, 0), rot=0.1)
place(PROPS, "GARDEN", "wooden_crate", (-9.55, y1 - 0.92, 0.302), rot=-0.05)
place(PROPS, "GARDEN", "wooden_crate", (-8.9, y1 - 0.95, 0), rot=0.25)
for k in range(3):
    place(PROPS, "GARDEN", "concrete_block", (-7.8 + k * 0.42, y1 - 0.8, 0), rot=1.57 + k * 0.08)
place(PROPS, "GARDEN", "concrete_block", (-7.4, y1 - 0.8, 0.19), rot=1.5)
place(PROPS, "RUBBLE", "gravel_pile_small", (-6.2, y1 - 2.6, 0), rot=0.6)

# ---------------------------------------------------------------- trees
trees = collection("Trees")
ts = sc.treegen
for k, (species, x, y) in enumerate((("OAK", -8.0, 7.0), ("MAPLE_AUTUMN", 15.0, 4.0), ("PINE", 1.5, 15.5),
                                      ("PINE", -14.5, 10.0), ("BUSH", -9.8, -6.4), ("BUSH", -0.6, -6.6),
                                      ("BUSH", 9.8, 9.5), ("MAPLE", -17.0, -1.0))):
    ts.species = species
    values = {n: getattr(ts, n) for n in tree_core.COPIED_PROPS}
    values["seed"] = 200 + k
    ob = tree_core.create_tree(ctx, values, Vector((x, y, 0)))
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    trees.objects.link(ob)
    ob.rotation_euler.z = rng.uniform(0, math.tau)

# ---------------------------------------------------------------- light, camera, save, render
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.0; sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(42), 0, math.radians(30)); sc.collection.objects.link(sun)
world = bpy.data.worlds.new("Sky"); sc.world = world; world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.42, 0.52, 0.66, 1); bg.inputs["Strength"].default_value = 0.8
sc.view_settings.view_transform = "AgX"; sc.view_settings.look = "AgX - Medium High Contrast"
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera")); sc.collection.objects.link(cam); sc.camera = cam
tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"

SHOTS = [("cottage_garden.png", (14.0, -24.0, 11.0), (1.0, 2.0, 0.5), 28),
         ("cottage_garden_yard.png", (12.5, -9.0, 3.2), (4.5, -1.0, 0.8), 30),
         ("cottage_garden_back.png", (1.8, 2.0, 2.4), (6.0, 10.5, 0.9), 28)]
cam.location, tgt.location, cam.data.lens = SHOTS[0][1], SHOTS[0][2], SHOTS[0][3]
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "cottage_garden.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc.render.engine = "CYCLES"; sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    for fname, at, look, lens in SHOTS:
        cam.location, tgt.location, cam.data.lens = at, look, lens
        sc.render.filepath = os.path.join(OUT, fname)
        bpy.ops.render.render(write_still=True)
print("SCENE DONE")
