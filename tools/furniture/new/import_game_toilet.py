"""Imports the toilet the game uses (A_bath_toilet_vintage, from the village houses' bathrooms) into
a .blend:  blender --background --python "ref/3D Models/furniture/toilet/import_game_toilet.py"
Origin on the floor at the back-centre, front facing -Y (as in the Neighborhood scene)."""
import pathlib

import bpy
from mathutils import Vector

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[3] / "data" / "models" / "village" / "parts" / "houses" / "A_bath_toilet_vintage.gltf"
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(SRC))
for o in bpy.data.objects:
    if o.type == "MESH":
        o.name = "toilet"
        pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
        print("size", [round(max(p[i] for p in pts) - min(p[i] for p in pts), 3) for i in range(3)])
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "toilet.blend"))
