"""The valley's east side (6 villas, 11 houses, 2 rows of 3 shops, one of them Sam's Caffee) built from the add-on
(cs_environment_elements) on the user's plan, for review before it moves to Godot.

The plan: the user drew it on out/east_roads_sizes.png (-> out/east_roads_sizes-with-houses.png);
read_east_drawing.py read it, plan_east.py shrank it to the size the user asked (House 10's lot = 650 m2, roads 7 m
with 1.8 m sidewalks) -> out/east_plan.json + the surface map out/east_plan_surfaces.png (check out/east_plan.png).

  - roads: asphalt over the streets and parking, raised sidewalks with kerbs, a 3 m paved driveway per lot
    (east/surfaces.py)
  - buildings (east/buildings.py, user's fixes 2026-11-25): House (100-140 m2, 2 floors) on the house lots,
    Modern and Gable Villas (VILLA_STYLES) on the villa lots, each facade 4 m behind its gate; Shopping Row (3 shops of
    7 x 8 m) on each parking, Shops 1-3 facing the bridge road, the others their parking; Sam's Caffee is one of the
    shops (SHOP_SIGNS)
  - lot fences: Modern, straight sides (plan_east.py / east_lots.py), on the sidewalk's edge along straight streets;
    the gate where the driveway to the parking place comes in, the door in line with the front door, the mailbox
    beside it (east/fences.py)
  - the cul-de-sac by House 5 (user, 2026-11-25): the road stops square, a paved plaza, a placeholder basin where the
    fountain goes (collection "ES Fountain (placeholder)")
  - context (not for export): the terrain as a mesh, the game's valley_water.glb

Not here yet: street lamps, trees and yard things, parking bays, the terrain's own road masks (the game still
paints the old east roads), the export.
World coordinates are the game's (Godot x = X, y = Z, z = -Y).

Run:  blender -b --factory-startup --python make_east.py
Env:  CS_PROJECT (default C:/cybta/carpentry simulator), SEED (default 1), RENDER=0 skips the renders.
Writes out/east.blend and out/east_*.png beside this script, out/east_built.json (what was built: walls, sizes,
driveways, shop signs) and redraws out/east_plan.png with it (east_plan_render.py, run with Inkscape's Python: INKSCAPE_PY).
"""
import json
import math
import os
import subprocess
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out")
PROJECT = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
SEED = int(os.environ.get("SEED", "1"))
INKSCAPE_PY = os.environ.get("INKSCAPE_PY", r"C:/Program Files/Inkscape/bin/python.exe")
# villa lot -> MODERN / GABLE (user, 2026-11-25: both types; alternated, as no lots were named)
VILLA_STYLES = {"Villa 1": "MODERN", "Villa 2": "GABLE", "Villa 3": "MODERN", "Villa 4": "GABLE", "Villa 5": "MODERN",
                "Villa 6": "GABLE"}
# shop row -> its signs in the plan's numbering; None = one of the generator's names (user, 2026-11-25: Sam's Caffee
# is one of the shops, not a building of its own; here shop 1, nearest the bridge)
SHOP_SIGNS = {"Shops 1-3": ["Sam's Caffee", None, None]}
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

bpy.ops.wm.read_factory_settings(use_empty=True)
import cs_environment_elements as pkg                                   # noqa: E402
pkg.register()
from cs_environment_elements.core import neighborhood_materials as nm   # noqa: E402
from old_neighborhood import lots as lotmod, terrain as tr               # noqa: E402
from east import buildings as eb, fences as ef, ground as eg, surfaces as es   # noqa: E402

ctx = bpy.context
sc = ctx.scene
t0 = time.time()
plan = json.load(open(os.path.join(OUT, "east_plan.json")))
ter = eg.FlatGround(tr.Terrain(PROJECT), plan)     # the east side levelled (user, 2026-11-25: east/ground.py)
print(ter.report)

# ---------------------------------------------------------------- collections
top = lotmod.coll("East Side")
C = {k: lotmod.coll(n, top) for k, n in (
    ("houses", "ES Houses"), ("villas", "ES Villas"), ("shops", "ES Shops"), ("fences", "ES Fences"),
    ("ground", "ES Ground"), ("fountain", "ES Fountain (placeholder)"), ("outlines", "ES Lot Outlines"))}
ctxc = lotmod.coll("Context (game, not for export)")
C["outlines"].hide_viewport = C["outlines"].hide_render = True

# ---------------------------------------------------------------- context: terrain + water
allpts = np.array([p for L in plan["lots"] for p in L["outline"]] + [p for r in plan["roads"] for p in r])
lo, hi = allpts.min(0) - 45, allpts.max(0) + 45
tr.ground_mesh(ter, "terrain-preview", lo[0], lo[1], hi[0], hi[1], 1.0, nm.ensure("C_grass"), ctxc, nm.uv_scale)
water = os.path.join(PROJECT, "data", "models", "valley", "valley_water.glb")
if os.path.exists(water):
    tr.import_glb(water, ctxc)
hz = ter.height(allpts)
print("terrain under the plan: %.2f - %.2f m" % (hz.min(), hz.max()))

# ---------------------------------------------------------------- buildings (first: the sidewalks are cut where
# their driveways actually come out)
half, walk = plan["road_width_m"] / 2, plan["sidewalk_width_m"]
asphalt_roads = [(np.array(r, float), half) for r in plan["roads"]]
street_roads = [(np.array(r, float), half + (walk if w else 0.0)) for r, w in zip(plan["roads"], plan["road_sidewalks"])]
square_ends = []                             # road ends cut square (the user's cul-de-sac): no asphalt past them
for i, j in plan.get("flat_ends", []):
    r = np.array(plan["roads"][i], float)
    e, before = (r[-1], r[-2]) if j == -1 else (r[0], r[1])
    square_ends.append((e, (e - before) / np.linalg.norm(e - before)))


def to_asphalt(start, front, into=0.3, reach=45.0):
    """Along `front` from `start` until `into` m onto the asphalt."""
    p0 = np.array(start, float)
    for t in np.arange(0.0, reach, 0.2):
        p = p0 + front * t
        if ef.road_dist(p, asphalt_roads) < -into and \
                not any(np.dot(p - e, d) > -into and np.linalg.norm(p - e) < 8.0 for e, d in square_ends):
            return p
    return None


def to_walk(start, front, reach=30.0):
    """Along `front` from `start` until just onto a street's sidewalk (or a road without one)."""
    p0 = np.array(start, float)
    for t in np.arange(0.0, reach, 0.1):
        p = p0 + front * t
        if ef.road_dist(p, street_roads) < -0.1:
            return p
    return None


infos = []
for L in plan["lots"]:
    coll = C["villas"] if L["kind"] == "villa" else C["houses"]
    info = eb.build_lot(ctx, L, ter, coll, SEED, VILLA_STYLES.get(L["name"]), to_asphalt)
    pl = info["placed"]
    if info["drive_start"] is not None:
        end = to_asphalt(info["drive_start"], pl.front)
        info["drive_end"] = end
        if end is None:
            print("%s: its front doesn't look onto a road; no driveway" % L["name"])
            info["drive_start"] = None
    info["door_end"] = to_walk(info["door_start"], pl.front) if info["door_start"] is not None else None
    infos.append(info)
    print("%-9s %-6s %4.1f x %4.1f m, %d m2, %d floor(s), facade %.1f m behind the fence%s%s%s  %.0fs" % (
        L["name"], info["style"], info["W"], info["D"], info["area"], info["floors"], info["gate_m"],
        "  (pulled %.1f m off where it was aimed, into its lot)" % info["moved"] if info["moved"] > 0.05 else "",
        "  (%.1f m sideways: its driveway on the plan's line)" % abs(info["lateral"]) if info["lateral"] else "",
        "  (%.1f m sideways to make room for its parking)" % info["pad_shift"] if info["pad_shift"] else "",
        time.time() - t0))
rows = []
for row in plan["shop_rows"]:
    w, d = plan["shop_size_m"]
    pad = next(p for p in plan["parking"] if p["for_shops"] == row["name"])
    info = eb.build_shops(ctx, row, pad, ter, C["shops"], SEED, w, d, SHOP_SIGNS.get(row["name"]))
    rows.append(info)
    print("%s: %4.1f x %4.1f m, facing the %s: %s  %.0fs" % (
        row["name"], info["W"], info["D"], row.get("faces", "parking"),
        ", ".join("%d %s" % (sh["number"], sh["sign"]) for sh in info["shops"]), time.time() - t0))

# ---------------------------------------------------------------- roads, parking, sidewalks, driveways
drives = [(i["name"], i["drive_start"], i["drive_end"]) for i in infos if i["drive_start"] is not None]
field = es.Field(plan, [[tuple(a), tuple(b)] for _, a, b in drives])
grid = es.Grid(plan, field, ter)
es.asphalt(grid, field, ter, C["ground"])
es.sidewalks(grid, field, ter, C["ground"])
for name, a, b in drives:
    es.driveway("%s-driveway" % name, a, b, ter, C["ground"])
for i in infos:                          # front door -> the fence's door -> the sidewalk (a villa: past its own path)
    if i["door_end"] is not None and np.linalg.norm(i["door_end"] - i["door_start"]) > 0.3:
        es.walk("%s-walk" % i["name"], i["door_start"], i["door_end"], ter, C["ground"])
for k, cd in enumerate(plan.get("cul_de_sacs", [])):     # where the user's fountain goes (a placeholder basin)
    es.fountain_spot("east-fountain-spot-%d" % (k + 1), cd["fountain"]["centre"], cd["fountain"]["r"], ter,
                     C["fountain"])
print("surfaces done %.1fs" % (time.time() - t0))

# ---------------------------------------------------------------- fences
for i, (L, info) in enumerate(zip(plan["lots"], infos)):
    f = ef.LotFence(i, L, plan["lots"], street_roads, info, SEED)
    f.build(ctx, ter, C["outlines"], C["fences"])
print("fences done %.1fs" % (time.time() - t0))

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

lp = np.array([p for L in plan["lots"] for p in L["outline"]])
mid = (lp.min(0) + lp.max(0)) / 2
zmid = ter.z(*mid)
E = float(max(lp.max(0) - lp.min(0)))
cafe_row = next(r for r in rows if any(sh["sign"] == "Sam's Caffee" for sh in r["shops"]))
cp = np.array(next(sh["door"] for sh in cafe_row["shops"] if sh["sign"] == "Sam's Caffee"))
cf = cafe_row["placed"].front
cafe_eye = cp + cf * 16 + np.array([-cf[1], cf[0]]) * 6           # across the street (or the parking)
street = next(i for i, L in zip(infos, plan["lots"]) if L["name"] == "House 9")["placed"]
st_eye = street.pos + street.front * 12 - np.array([-street.front[1], street.front[0]]) * 30
st_look = street.pos + street.front * 12 + np.array([-street.front[1], street.front[0]]) * 30
SHOTS = [
    ("east_top.png", "ORTHO", (mid[0], mid[1], zmid + 300), (mid[0], mid[1], zmid), E + 20),
    ("east_aerial.png", "PERSP", (mid[0] + 0.5 * E, mid[1] - 0.8 * E, zmid + 0.45 * E), (mid[0], mid[1], zmid), 30),
    ("east_cafe.png", "PERSP", (cafe_eye[0], cafe_eye[1], ter.z(*cafe_eye) + 1.7),
     (cp[0], cp[1], ter.z(*cp) + 3.0), 26),
    ("east_street.png", "PERSP", (st_eye[0], st_eye[1], ter.z(*st_eye) + 1.7),
     (st_look[0], st_look[1], ter.z(*st_look) + 1.4), 24),
]
for k, cd in enumerate(plan.get("cul_de_sacs", [])):     # the cul-de-sac from above (as the user's screenshot) and
    fc, dd = np.array(cd["fountain"]["centre"]), np.array(cd["dir"])    # down the street at its fountain
    top_c = fc - dd * 14
    eye = fc - dd * 34
    SHOTS += [("east_culdesac_top%s.png" % ("" if k == 0 else k + 1), "ORTHO", (top_c[0], top_c[1], zmid + 200),
               (top_c[0], top_c[1], zmid), 70),
              ("east_fountain%s.png" % ("" if k == 0 else k + 1), "PERSP", (eye[0], eye[1], ter.z(*eye) + 1.7),
               (fc[0], fc[1], ter.z(*fc) + 0.8), 24)]


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
path = os.path.join(OUT, "east.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
print("saved", path, "%.0fs" % (time.time() - t0))

# ---------------------------------------------------------------- what was built, and the plan redrawn with it
built = dict(note="written by make_east.py from east_plan.json: the buildings as built (walls = outer wall faces)",
             gate_gap_m=eb.GATE_GAP, ground=ter.record(), lots=[], shop_rows=[])
for L, i in zip(plan["lots"], infos):
    built["lots"].append(dict(name=L["name"], kind=L["kind"], style=i["style"], width_m=round(i["W"], 1),
                              depth_m=round(i["D"], 1), floors=i["floors"], area_m2=i["area"], walls=i["walls"],
                              front_dir=[round(float(v), 4) for v in i["placed"].front], gate_m=round(i["gate_m"], 2),
                              driveway=[[round(float(v), 2) for v in p] for p in (i["drive_start"], i["drive_end"])]
                              if i["drive_start"] is not None else None,
                              walk=[[round(float(v), 2) for v in p] for p in (i["door_start"], i["door_end"])]
                              if i["door_end"] is not None else None))
for row, i in zip(plan["shop_rows"], rows):
    built["shop_rows"].append(dict(name=row["name"], faces=row.get("faces", "parking"), length_m=round(i["W"], 1),
                                   depth_m=round(i["D"], 1), walls=i["walls"],
                                   front_dir=[round(float(v), 4) for v in i["placed"].front], shops=i["shops"]))
json.dump(built, open(os.path.join(OUT, "east_built.json"), "w"), indent=1)
if os.path.exists(INKSCAPE_PY):
    r = subprocess.run([INKSCAPE_PY, os.path.join(HERE, "east_plan_render.py")], capture_output=True, text=True)
    print("east_plan.png redrawn as built" if r.returncode == 0 else "east_plan.png NOT redrawn:\n" + r.stderr)
else:
    print("no Inkscape Python at %s: run east_plan_render.py with a Python that has numpy + Pillow" % INKSCAPE_PY)

if os.environ.get("RENDER", "1") != "0":
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 40
    sc.cycles.use_denoising = True
    for shot in SHOTS:
        aim(shot)
        sc.render.resolution_x, sc.render.resolution_y = (1920, 1920) if shot[1] == "ORTHO" else (1920, 1080)
        sc.render.filepath = os.path.join(OUT, shot[0])
        bpy.ops.render.render(write_still=True)
        print("rendered", shot[0], "%.0fs" % (time.time() - t0))
print("SCENE DONE")
