"""The old neighbourhood's site plan as data, for agreeing on the layout before anything is built.

Run with Blender's own Python (needs numpy, not bpy):
    "<Blender>/4.4/python/bin/python.exe" plan_old_neighborhood.py [scale]
then draw it (system Python + Pillow):
    python draw_old_neighborhood_plan.py
Writes out/old_neighborhood_plan.json (and the drawing writes out/old_neighborhood_plan.png).
House spots use a typical cottage (6 x 5.5 m walls, 1.5 m veranda + steps toward the road).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np                                     # noqa: E402
from old_neighborhood import frontage, layout          # noqa: E402

SCALE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.6
SEED = int(os.environ.get("SEED", "1"))
PLAY_W, PLAY_D = 22.0, 13.0
# a typical cottage, local to its origin (front = -Y): walls, veranda, gravel bed reach
WALL_W, WALL_D, VERANDA, STEPS = 6.0, 5.5, 1.5, 0.9
HW, FRONT_EXT, BACK_EXT = WALL_W / 2 + 0.8, WALL_D / 2 + VERANDA + STEPS + 0.3, WALL_D / 2 + 0.8

net = layout.Network(os.path.join(HERE, "poor_quarter_layout.json"), scale=SCALE)
hero = net.shrink(net.data["hero_cottage"])
play = {}
found = layout.find_playground(net, [], PLAY_W, PLAY_D, road_gap=layout.FRONT + 13.0)
if found:
    play["centre"], play["rect"] = found
else:
    print("playground: no room in the loop")
live = frontage.frontage_lots(net, hero=hero, blocked=[play["rect"]] if play else [])


def box(L, u, v, x0, y0, x1, y1):
    """A house-local box -> world corners (house at lot (u, v), turned like the lot)."""
    return [L.world(u + x, v + y).tolist() for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


out_lots = []
for L in live:
    house = None if L.hero else layout.place_house(L, HW, HW, FRONT_EXT, BACK_EXT, 2.5)   # may drop the drive
    rec = dict(idx=L.idx, hero=L.hero, infill=L.infill, corners=L.corners().tolist(), skip=sorted(L.skip),
               end=L.end.tolist(), drive=None if L.infill else L.path.tolist())
    if house:
        u, v, beside = house
        rec["house"] = dict(walls=box(L, u, v, -WALL_W / 2, -WALL_D / 2, WALL_W / 2, WALL_D / 2),
                            veranda=box(L, u, v, -WALL_W / 2, -WALL_D / 2 - VERANDA, WALL_W / 2, -WALL_D / 2),
                            door=L.world(u + 1.5, v - WALL_D / 2 - VERANDA - STEPS).tolist())
    out_lots.append(rec)

total_fence = 0.0
for L in live:
    c = L.corners()
    for i in range(4):
        if i + 1 not in L.skip and not L.hero:
            total_fence += float(np.linalg.norm(c[(i + 1) % 4] - c[i]))
data = dict(scale=SCALE, front=layout.FRONT, road_half=layout.ROAD_HALF, drive_half=layout.DRIVE_HALF,
            roads=[[a.tolist(), b.tolist()] for a, b in net.roads],
            drives=[[a.tolist(), b.tolist()] for a, b in net.drives],
            lots=out_lots, hero=list(map(float, hero)),
            playground=[list(map(float, p)) for p in play["rect"]] if play else None,
            fence_m=round(total_fence))
os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
path = os.path.join(HERE, "out", "old_neighborhood_plan.json")
json.dump(data, open(path, "w"))
n_shared = sum(len(L.skip) for L in live)
print("plan: %d lots (%d infill), %d shared fence sides, %d m of fence -> %s"
      % (len(live), sum(L.infill for L in live), n_shared, total_fence, path))
