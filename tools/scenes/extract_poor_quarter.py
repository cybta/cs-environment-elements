"""Dump the valley map's poor-quarter roads + driveways to poor_quarter_layout.json (beside this script).

Opens the terrain .blend READ-ONLY (never saved) and runs the bake's own centre-line code
(carpentry simulator/blender_src/terrain/valley_road_centerlines.py), so the neighbourhood scene sits
on exactly the roads the Godot terrain is painted with.

Run:  blender -b "<Desktop>/heightmap-terrain/HeightmapTerrain.blend" --python extract_poor_quarter.py
Env:  CS_PROJECT = the carpentry simulator folder (default C:/cybta/carpentry simulator)

Coordinates are Blender world metres (Godot x = X, Godot z = -Y). Heights are not sampled here; the
scene script reads them from valley_height.exr.
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

centre = np.array(ns["POOR_SHRINK"]["center"])
anchor = np.array(ns["POOR_SHRINK"]["anchor"])
REACH = 140.0                                   # the quarter is ~150 x 90 m; its approach road runs east


def keep(a, b):
    a, b = np.array(a, float), np.array(b, float)
    if max(np.linalg.norm(a - centre), np.linalg.norm(b - centre)) < REACH:
        return True
    # the approach road to the river crossing (between the quarter and the anchor)
    return a[0] < anchor[0] + 1 and b[0] < anchor[0] + 1 and min(a[0], b[0]) > centre[0] and \
        abs(a[1] - centre[1]) < 120 and abs(b[1] - centre[1]) < 120


roads, drives = [], []
for (a, b), d in zip(segs, is_drive):
    if keep(a, b):
        (drives if d else roads).append([[round(float(a[0]), 3), round(float(a[1]), 3)],
                                         [round(float(b[0]), 3), round(float(b[1]), 3)]])

out = {
    "note": "valley poor quarter, Blender world metres (Godot x = X, z = -Y); from extract_poor_quarter.py",
    "road_width": ns["ROAD_WIDTH"], "drive_width": ns["DRIVE_WIDTH"],
    "center": centre.tolist(), "anchor": anchor.tolist(),
    "roads": roads, "drives": drives,
    "hero_cottage": [-373.7, -18.1],             # Cottage_70m2, already in valley.tscn: leave its lot alone
}
path = os.path.join(HERE, "poor_quarter_layout.json")
with open(path, "w") as f:
    json.dump(out, f, indent=1)
print("POOR QUARTER: %d road + %d driveway segments -> %s" % (len(roads), len(drives), path))
