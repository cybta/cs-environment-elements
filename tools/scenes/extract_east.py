"""Dump the valley map's east side (mid-range houses, villas, shops) roads + driveways to east_layout.json.

Same as extract_poor_quarter.py, for everything east of the river crossing: opens the terrain .blend READ-ONLY
(never saved) and runs the bake's own centre-line code (carpentry simulator/blender_src/terrain/
valley_road_centerlines.py), so the sheet the user draws lots on shows exactly the roads the terrain is painted with.

Run:  blender -b "<Desktop>/heightmap-terrain/HeightmapTerrain.blend" --python extract_east.py
Env:  CS_PROJECT = the carpentry simulator folder (default C:/cybta/carpentry simulator)

Coordinates are Blender world metres (Godot x = X, Godot z = -Y).
"""
import json
import os

import bpy  # noqa: F401  (the exec'd code uses it)
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
SRC = os.path.join(PROJECT, "blender_src", "terrain", "valley_road_centerlines.py")

ns = {"__name__": "centerlines"}
exec(open(SRC).read(), ns)

segs = ns["road_centerlines"]("CS-roads")
_, drives0 = ns["split_driveways"](segs, ns["DRIVE_MAX"])
drive_set = set(drives0)
is_drive = [(a, b) in drive_set for a, b in segs]
segs, _ = ns["shrink_area"](segs, **ns["POOR_SHRINK"])
segs, _ = ns["shrink_area"](segs, **ns["EAST_SHRINK"])

anchor = np.array(ns["EAST_SHRINK"]["anchor"])     # the river crossing: the east side is everything past it
roads, drives = [], []
for (a, b), d in zip(segs, is_drive):
    if min(a[0], b[0]) >= anchor[0] - 1.0:
        (drives if d else roads).append([[round(float(a[0]), 3), round(float(a[1]), 3)],
                                         [round(float(b[0]), 3), round(float(b[1]), 3)]])

out = {
    "note": "valley east side, Blender world metres (Godot x = X, z = -Y); from extract_east.py",
    "road_width": ns["ROAD_WIDTH"], "drive_width": ns["DRIVE_WIDTH"],
    "center": list(ns["EAST_SHRINK"]["center"]), "anchor": anchor.tolist(),
    "roads": roads, "drives": drives,
}
path = os.path.join(HERE, "east_layout.json")
with open(path, "w") as f:
    json.dump(out, f, indent=1)
print("EAST: %d road + %d driveway segments -> %s" % (len(roads), len(drives), path))
