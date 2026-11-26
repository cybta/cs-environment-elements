"""Measure the footprints the add-on's house / villa / shop generators make, for the lot drawing sheets.

    blender -b --factory-startup --python measure_building_sizes.py

Builds each panel preset (house 100 / 130 / 200 m2, modern villa 200 / 240 / 320, gable villa 170 / 200 / 260,
shopping row of 3 and 4 shops) in an empty scene (nothing saved) and writes east_type_sizes.json beside this
script: walls = the building's walls (width along the street x depth), overall = everything it brings (sidewalk,
the villas' driveway + paving in front, the shops' street sidewalk), height, floors. draw_east_roads.py draws them.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..")))

import bpy  # noqa: E402
from mathutils import Vector
import cs_environment_elements as pkg
pkg.register()
from cs_environment_elements.buildings.house import _build
s = bpy.context.scene.house_gen
CASES = [("HOUSE", 100, 1, 3, 2, None), ("HOUSE", 130, 2, 3, 2, None), ("HOUSE", 200, 2, 4, 3, None),
         ("VILLA_MODERN", 200, 2, 3, 2, None), ("VILLA_MODERN", 240, 2, 4, 3, None), ("VILLA_MODERN", 320, 2, 5, 4, None),
         ("VILLA_GABLE", 170, 2, 2, 2, None), ("VILLA_GABLE", 200, 2, 3, 2, None), ("VILLA_GABLE", 260, 2, 4, 3, None),
         ("SHOPS", 0, 2, 0, 0, 3), ("SHOPS", 0, 2, 0, 0, 4)]
out = []
for i, (t, area, fl, bd, ba, n) in enumerate(CASES):
    s.building_type = t
    if t == "SHOPS":
        s.shop.count = n
    else:
        s.total_area, s.bedrooms, s.bathrooms = area, bd, ba
        if t == "HOUSE":
            s.floors = fl
        s.open_plan = True
    name = "m%d" % i
    plan = _build(bpy.context, s, print, name=name, site=True)
    root = bpy.data.objects[name]
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in root.children_recursive:
        if o.type != "MESH" or o.get("lod", 0) or not o.data.vertices:
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, w)); hi = Vector(map(max, hi, w))
    rec = dict(type=t, area=area, shops=n, walls=[round(plan.W, 1), round(plan.D, 1)],
               overall=[round(hi.x - lo.x, 1), round(hi.y - lo.y, 1)], height=round(hi.z - lo.z, 1),
               floors=len(plan.floors))
    print("SIZE", json.dumps(rec))
    out.append(rec)
json.dump(out, open(os.path.join(HERE, "east_type_sizes.json"), "w"), indent=1)
