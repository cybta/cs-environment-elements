"""The workshop's computer desk with four cone feet (it used to float, 0.175 m off the floor).

    blender --background --python "ref/3D Models/furniture/desk-workshop/make_desk_feet.py"

Takes the original model (ref/3D Models/desk/desk.blend: two drawer units + counter-top), adds four
tapered cone feet that reach down to the floor, saves desk-workshop.blend here (textures/ beside it)
and exports data/models/desk/desk.glb. The model's origin and orientation are unchanged, so
data/layout.json (station position, props on the desk) still fits: the desk top stays at 0.825 m.
"""
import math
import pathlib
import shutil

import bmesh
import bpy
from mathutils import Vector

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[1] / "desk" / "desk.blend"
OUT = HERE.parents[3] / "data" / "models" / "desk" / "desk.glb"
TOP_Z, BOTTOM_Z = -0.225, -0.40        # underside of the drawer units / the floor (blender Z = up)
R_TOP, R_BOT = 0.034, 0.011
SPLAY = math.radians(7)                # feet lean outward a little
XS, YS = (-0.27, 0.29), (-0.27, 0.97)  # inset from the corners of the two drawer units


def cone(name, top, bottom, mat):
    axis = (bottom - top).normalized()
    a = axis.cross(Vector((0, 0, 1)))
    a = (a if a.length > 1e-6 else Vector((1, 0, 0))).normalized()
    b = axis.cross(a).normalized()
    top = top - axis * 0.004            # sink the top into the drawer unit
    bm = bmesh.new()
    rings = []
    for c, r in ((top, R_TOP), (bottom + axis * 0.002, R_BOT), (bottom, R_BOT * 0.8)):
        rings.append([bm.verts.new(c + (a * math.cos(t) + b * math.sin(t)) * r)
                      for t in (2 * math.pi * i / 32 for i in range(32))])
    for k in range(2):
        for i in range(32):
            j = (i + 1) % 32
            bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
    bm.faces.new(rings[2][::-1])
    bm.faces.new(rings[0])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for f in bm.faces:
        f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(o)
    return o


bpy.ops.wm.open_mainfile(filepath=str(SRC))
tex = HERE / "textures"
tex.mkdir(exist_ok=True)
for img in bpy.data.images:
    if img.filepath and img.name != "Render Result":
        src = pathlib.Path(bpy.path.abspath(img.filepath, library=img.library))
        if src.exists() and src.parent != tex:
            shutil.copy(src, tex / src.name)
        img.filepath = str(tex / src.name)   # absolute; Blender makes it relative on save
        img.reload()
mat = bpy.data.materials.new("desk_feet")
mat.use_nodes = True
b = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
b.inputs["Base Color"].default_value = (0.10, 0.06, 0.035, 1)
b.inputs["Roughness"].default_value = 0.55
feet = []
for x in XS:
    for y in YS:
        out = Vector((math.copysign(1, x - 0.01), math.copysign(1, y - 0.35), 0)).normalized()
        drop = TOP_Z - BOTTOM_Z
        top = Vector((x, y, TOP_Z))
        feet.append(cone(f"foot_{len(feet) + 1}", top, top + out * drop * math.tan(SPLAY) + Vector((0, 0, -drop)), mat))
bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "desk-workshop.blend"))
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_yup=True)
low = min((o.matrix_world @ Vector(v)).z for o in bpy.data.objects if o.type == "MESH" for v in o.bound_box)
print("desk done, lowest point z =", round(low, 3))
