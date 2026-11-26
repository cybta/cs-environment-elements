"""The old (poor) neighbourhood of the valley map, built from the add-on (cs_environment_elements) on the
USER'S DRAWN PLAN, for review before it moves to Godot.

The plan: the user drew lots (fences), houses and organic dirt roads on the roads-only sheet
(out/old_neighborhood_Edit.png, drawn on draw_old_neighborhood_roads.py's sheet: the map's roads at 60 %);
read_old_neighborhood_drawing.py reads it into out/old_neighborhood_drawn.json (check out/old_neighborhood_drawn.png).

  - roads: the drawn dirt as the road surface (organic edges, driveways into the lots), the old road to the bridge
  - 20 lots: an old cottage each (painted or timber, random paint and wear) on the drawn footprint, the veranda
    toward the drawn door side; the old picket fence along the drawn outline, pushed toward the road so a
    street is ~6.5 m fence to fence (the dirt may run into the lots); a shared side
    is built once (by the lower-numbered lot); a gate where the driveway comes in, a wicket door + path beside it
  - yards: sitting corner, clothesline + laundry, firewood shed, wheelbarrows, crates, blocks, gravel heaps,
    hose + watering can, wheelie bins out by the gate, a small tree and bushes, sometimes a rock
  - street: old electric poles at the road edge (every other one with a lamp), sagging wires, a service cable to
    each cottage; Jagged rocks (Nature > Rocks) and Gravel & Rubble (Props) along the roads; a few trees
  - the park and the empty space (user's labels) stay grass for now
  - context (not for export): the terrain as a mesh, the game's valley_water.glb

World coordinates are the game's (Godot x = X, y = Z, z = -Y).

Run:  blender -b --factory-startup --python make_old_neighborhood.py
Env:  CS_PROJECT (default C:/cybta/carpentry simulator), SEED (default 1), RENDER=0 skips the renders,
      TREES=0 skips the trees and bushes.
Writes out/old_neighborhood.blend and out/old_neighborhood_*.png beside this script.
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out")
PROJECT = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
SEED = int(os.environ.get("SEED", "1"))
SCALE = 0.6                       # the sheet's road layout (draw_old_neighborhood_roads.py)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

bpy.ops.wm.read_factory_settings(use_empty=True)
import cs_environment_elements as pkg                                   # noqa: E402
pkg.register()
from cs_environment_elements.core import neighborhood_materials as nm   # noqa: E402
from old_neighborhood import layout, lots as lotmod, terrain as tr       # noqa: E402
from old_neighborhood.drawn import DrawnLot, Plan                       # noqa: E402
from old_neighborhood.drawn_lots import DrawnLotBuilder                 # noqa: E402
from old_neighborhood.drawn_street import DrawnStreet                   # noqa: E402

ctx = bpy.context
sc = ctx.scene
t0 = time.time()

# ---------------------------------------------------------------- the drawn plan
ter = tr.Terrain(PROJECT)
net = layout.Network(os.path.join(HERE, "poor_quarter_layout.json"), scale=SCALE)
plan = Plan(json.load(open(os.path.join(OUT, "old_neighborhood_drawn.json"))),
            json.load(open(os.path.join(OUT, "old_neighborhood_roads.json"))),
            os.path.join(OUT, "old_neighborhood_Edit.png"))
plan.push_fences()
json.dump({n: L["outline"] for n, L in plan.lots.items()},
          open(os.path.join(OUT, "old_neighborhood_fences.json"), "w"))      # the fence lines as built
lots = [DrawnLot(n, plan.lots[n], plan.houses[n]) for n in sorted(plan.lots)]
print("plan: %d lots, %.1fs" % (len(lots), time.time() - t0))

# ---------------------------------------------------------------- collections
top = lotmod.coll("Old Neighborhood")
C = {k: lotmod.coll(n, top) for k, n in (
    ("cottages", "ON Cottages"), ("fences", "ON Fences"), ("yards", "ON Yards"), ("street", "ON Street"),
    ("ground", "ON Ground"), ("rocks", "ON Rocks"), ("trees", "ON Trees"), ("outlines", "ON Lot Outlines"))}
ctxc = lotmod.coll("Context (game, not for export)")
C["outlines"].hide_viewport = C["outlines"].hide_render = True

# ---------------------------------------------------------------- context: terrain + water
allpts = np.vstack([L.poly for L in lots] + [np.array([a, b]) for a, b in net.roads])
lo, hi = allpts.min(0) - 45, allpts.max(0) + 45
tr.ground_mesh(ter, "terrain-preview", lo[0], lo[1], hi[0], hi[1], 1.0, nm.ensure("C_grass"), ctxc, nm.uv_scale)
water = os.path.join(PROJECT, "data", "models", "valley", "valley_water.glb")
if os.path.exists(water):
    tr.import_glb(water, ctxc)

# ---------------------------------------------------------------- the drawn roads
plan.road_mesh(ter, "dirt-roads", nm.ensure("C_world_dirt"), C["ground"], nm.uv_scale(nm.ensure("C_world_dirt")),
               mask=plan.dirt)
plan.road_mesh(ter, "road-to-bridge", nm.ensure("C_world_gravel"), C["ground"],
               nm.uv_scale(nm.ensure("C_world_gravel")), mask=plan.bridge & ~plan.dirt, lift=0.04)
print("roads done %.1fs" % (time.time() - t0))

# ---------------------------------------------------------------- poles, lots, wires, rocks, gravel, trees
st = DrawnStreet(ctx, ter, net, lots, C, SEED, plan)
st.poles_and_wires(nudges=[
    ((-295.7, -70.4), (-2.0, 0.0)),          # the last feeder pole from the bridge: 2 m back (user, 2026-11-23)
])
infos = []
for L in lots:
    b = DrawnLotBuilder(ctx, ter, L, SEED, C, plan, poles=[p["pos"] for p in st.poles])
    infos.append(b.build())
    print("lot %2d: %s, %d m2%s" % (L.idx, infos[-1]["name"], plan.lots[L.idx]["area_m2"],
                                    ", skips sides %s (shared)" % sorted(L.skip) if L.skip else ""))
print("lots done %.1fs" % (time.time() - t0))
st.service_drops(infos)
st.gravel()
st.jagged_rocks(infos)
if os.environ.get("TREES", "1") != "0":
    st.open_trees()
print("street done %.1fs" % (time.time() - t0))

# ---------------------------------------------------------------- light, cameras, save, render
sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
sun.data.energy = 3.2
sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(40), 0, math.radians(35))
sc.collection.objects.link(sun)
world = bpy.data.worlds.new("Sky")
sc.world = world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.42, 0.52, 0.66, 1)
bg.inputs["Strength"].default_value = 0.8
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_end = 3000
tgt = bpy.data.objects.new("CamTarget", None)
sc.collection.objects.link(tgt)
con = cam.constraints.new("TRACK_TO")
con.target, con.track_axis, con.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"

lp = np.vstack([L.poly for L in lots])
mid = (lp.min(0) + lp.max(0)) / 2
zmid = ter.z(*mid)
E = float(max(lp.max(0) - lp.min(0)))


def lot_shot(n, back=22.0, up=11.0):
    L = next(L for L in lots if L.idx == n)
    look = L.poly.mean(0)
    eye = L.j - L.d * back + L.u * 6
    return (eye[0], eye[1], ter.z(*eye) + up), (look[0], look[1], ter.z(*look) + 1.5)


L9 = next(L for L in lots if L.idx == 9)
road_eye = L9.j - L9.d * 3.0 - L9.u * 25
road_look = L9.j - L9.d * 3.0 + L9.u * 30
SHOTS = [
    ("old_neighborhood_top.png", "ORTHO", (mid[0], mid[1], zmid + 300), (mid[0], mid[1], zmid), E + 16),
    ("old_neighborhood_aerial.png", "PERSP", (mid[0] + 0.55 * E, mid[1] - 0.75 * E, zmid + 0.45 * E),
     (mid[0], mid[1], zmid), 30),
    ("old_neighborhood_shared.png", "PERSP", *lot_shot(9), 26),
    ("old_neighborhood_street.png", "PERSP", (road_eye[0], road_eye[1], ter.z(*road_eye) + 1.7),
     (road_look[0], road_look[1], ter.z(*road_look) + 1.4), 24),
]


def aim(shot):
    _, kind, eye, look, lens = shot
    cam.location, tgt.location = eye, look
    cam.data.type = kind
    if kind == "ORTHO":
        cam.data.ortho_scale = lens
    else:
        cam.data.lens = lens


aim(SHOTS[1])
os.makedirs(OUT, exist_ok=True)
path = os.path.join(OUT, "old_neighborhood.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
print("saved", path, "%.0fs" % (time.time() - t0))

if os.environ.get("RENDER", "1") != "0":
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 40
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
    for shot in SHOTS:
        aim(shot)
        sc.render.resolution_y = 1920 if shot[1] == "ORTHO" else 1080
        sc.render.filepath = os.path.join(OUT, shot[0])
        bpy.ops.render.render(write_still=True)
        print("rendered", shot[0], "%.0fs" % (time.time() - t0))
print("SCENE DONE")
