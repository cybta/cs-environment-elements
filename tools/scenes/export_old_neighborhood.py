"""Export the old neighbourhood to the game: data/models/valley/old_neighborhood.glb (game world coordinates).

    blender -b --factory-startup out/old_neighborhood.blend --python export_old_neighborhood.py [-- <glb>]

Exports the "Old Neighborhood" collection (cottages, fences, yards, street, ground), not the lot outlines, the
context (terrain preview, water), trees, bushes or rocks (LEAVE_OUT). Fences get LOD1-3 first if they have none
(cottages have theirs); cottage LOD2/3 are baked to one material each (lod_bake, pictures in out/bake).
Nothing is saved back into the .blend. In Godot, OldNeighborhood (scripts/world/old_neighborhood.gd)
loads the glb: LOD switching, paint shaders, collision.
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..")))
import cs_environment_elements as pkg     # noqa: E402
pkg.register()
from cs_environment_elements.buildings import lod   # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = args[0] if args else r"C:/cybta/carpentry simulator/data/models/valley/old_neighborhood.glb"

top = bpy.data.collections["Old Neighborhood"]
skip = {"ON Lot Outlines"}
# objects left out by name: the user will place their own trees (2026-11-25), bushes and rocks (2026-11-26)
LEAVE_OUT = ("tree-", "bush-", "rock-")
for c in top.children_recursive:
    c.hide_viewport = c.hide_render = c.name in skip
vl = bpy.context.view_layer


def layer_coll(lc, name):
    if lc.collection.name == name:
        return lc
    for ch in lc.children:
        got = layer_coll(ch, name)
        if got:
            return got


for name in skip:
    lc = layer_coll(vl.layer_collection, name)
    if lc:
        lc.exclude = True

built = 0
for ob in list(top.all_objects):
    if ob.parent is None and ob.type == "EMPTY" and "lod_cards" in ob and not any(
            o.get("lod", 0) > 0 for o in ob.children_recursive):
        lod.build(ob)
        built += 1
print("fence LODs built:", built)

# trees / bushes are geometry nodes whose leaves are instances: glTF only writes realised geometry, so make them
# real meshes first (in memory; the .blend isn't saved)
trees = [o for o in bpy.data.collections["ON Trees"].all_objects if o.type == "MESH" and o.modifiers
         and not o.name.startswith(LEAVE_OUT)]
for ng in {m.node_group for o in trees for m in o.modifiers if m.type == "NODES" and m.node_group}:
    out = next(n for n in ng.nodes if n.bl_idname == "NodeGroupOutput")
    link = next((l for l in ng.links if l.to_node == out), None)
    if link is None or link.from_node.bl_idname == "GeometryNodeRealizeInstances":
        continue
    real = ng.nodes.new("GeometryNodeRealizeInstances")      # the leaf cards are instances: make them geometry
    ng.links.new(link.from_socket, real.inputs[0])
    ng.links.new(real.outputs[0], link.to_socket)
dg = bpy.context.evaluated_depsgraph_get()
for o in trees:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    o.modifiers.clear()
    o.data = me
print("trees made real:", len(trees), "tris", sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in trees))
# cottages built before cottage.JOIST_SET_BACK: deck edge + rim joists flush with the porch posts (flicker); the
# add-on's "Fix Porch Posts" (cottage_fix) repairs them in the .blend; this catches any not yet fixed (in memory)
from cs_environment_elements.buildings.cottage_fix import set_back_veranda   # noqa: E402

set_back = sum(set_back_veranda(r) for r in bpy.data.collections["ON Cottages"].all_objects if r.parent is None)
print("veranda decks + rims set back from the posts (+ LODs rebuilt):", set_back)
# the storey walls are one mesh with the facade and the inside lining: split the inside off ("<walls>_Inside"), so
# the game can show it only close to the house (it is never seen from outside)
import bmesh                                    # noqa: E402
INSIDE = {"C_cottage_lining", "C_cottage_lining_v", "C_bath_tile_wall"}
split = 0
for o in list(bpy.data.collections["ON Cottages"].all_objects):
    if o.type != "MESH" or o.get("lod", 0) or not o.name.endswith("_Walls"):
        continue
    inside = {i for i, m in enumerate(o.data.materials) if m and m.name in INSIDE}
    if not inside or len(inside) == len(o.data.materials):
        continue
    cp = o.copy()
    cp.data = o.data.copy()
    cp.name = o.name + "_Inside"
    for c in o.users_collection:
        c.objects.link(cp)
    for ob, drop_inside in ((o, True), (cp, False)):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if (f.material_index in inside) == drop_inside], context="FACES")
        bm.to_mesh(ob.data)
        bm.free()
    split += 1
print("walls split into facade + inside:", split)

# Draw calls: in the game every LOD0 part was its own MeshInstance3D and every material on it a draw call (twice with
# the shadow pass), ~40 parts a cottage. Merge each cottage's LOD0 into <root>_Exterior (one surface per material),
# <root>_Inside (what the game draws only at the front door: old_neighborhood.gd INTERIOR, same names) and
# <root>_Glass (own render layer + material swap in the game); <root>_GF_Doors stays (the game's front door).
INTERIOR = ("_Inside", "Stair", "_Floor", "InnerDoors", "CasingsInside", "TopCeiling")
merged, parts_before = 0, 0
for root in [r for r in bpy.data.collections["ON Cottages"].all_objects if r.parent is None and r.children]:
    groups = {"Exterior": [], "Inside": [], "Glass": []}
    for o in root.children:
        if o.type != "MESH" or o.get("lod", 0):
            continue
        sfx = o.name[len(root.name) + 1:]
        if sfx == "GF_Doors":
            continue
        g = "Inside" if any(k in sfx for k in INTERIOR) else "Glass" if sfx.endswith("Glass") else "Exterior"
        groups[g].append(o)
    if len(groups["Exterior"]) < 2:
        continue
    for g, obs in groups.items():
        if not obs:
            continue
        parts_before += len(obs)
        for o in obs:
            o.hide_viewport = False
            o.hide_set(False)
        a = obs[0]
        if len(obs) > 1:
            with bpy.context.temp_override(active_object=a, object=a, selected_objects=obs,
                                           selected_editable_objects=obs):
                bpy.ops.object.join()
        a.name = a.data.name = f"{root.name}_{g}"
        ca = a.data.color_attributes
        names = [c.name for c in ca]
        if "Paint" in names:                         # the exporter writes the active colour layer: the paint
            ca.active_color = ca["Paint"]
            ca.render_color_index = names.index("Paint")
    merged += 1
print("cottages merged to Exterior / Inside / Glass (+ GF_Doors):", merged, "from", parts_before, "parts")

# Far draw calls: LOD2 / LOD3 kept every material of the house (~10 draw calls a house at any distance). Bake each
# to one picture + one material (lod_bake: Cycles, base colour of all its materials, paint included).
from cs_environment_elements.buildings import lod_bake   # noqa: E402
import time                                              # noqa: E402

t0 = time.time()
BAKE_DIR = os.path.join(HERE, "out", "bake")
houses = [r for r in bpy.data.collections["ON Cottages"].all_objects if r.parent is None and r.children]
baked = sum(lod_bake.bake_far(r, BAKE_DIR) for r in houses)  # a list first: baking changes the collection
print("far LODs baked to one material:", baked, "in %.0f s" % (time.time() - t0))
objs = [o for c in [top] + list(top.children_recursive) if c.name not in skip for o in c.objects
        if not o.name.startswith(LEAVE_OUT)]
bpy.ops.object.select_all(action="DESELECT")
tris = {}
for o in set(objs):
    o.hide_viewport = False
    try:
        o.hide_set(False)
        o.select_set(True)
    except RuntimeError:
        continue
    if o.type == "MESH":
        lv = o.get("lod", 0)
        t = sum(len(p.vertices) - 2 for p in o.data.polygons)
        tris[lv] = tris.get(lv, 0) + t
print("tris by LOD level:", dict(sorted(tris.items())))

# glTF has no bump: the exporter writes a Bump node's height image as the normal map, and Godot then imports that
# picture AS a normal map (red + green kept, blue rebuilt), which is also the material's colour: the yard props'
# grey planks (C_fence_old_wood, fence.png) came out yellow. For the export, a Bump feeding a BSDF's Normal is
# skipped: whatever feeds the Bump's own Normal (a real normal map) goes straight to the BSDF, else nothing.
unbumped = 0
for mat in bpy.data.materials:
    if not mat.use_nodes or mat.node_tree is None:
        continue
    links = mat.node_tree.links
    for ln in list(links):
        if ln.from_node.bl_idname != "ShaderNodeBump" or ln.to_socket.name != "Normal":
            continue
        src = ln.from_node.inputs["Normal"].links
        to = ln.to_socket
        links.remove(ln)
        if src:
            links.new(src[0].from_socket, to)
        unbumped += 1
print("bump nodes skipped (glTF has no bump):", unbumped)

kw = dict(filepath=GLB, use_selection=True, export_yup=True, export_format="GLB", export_apply=True,
          export_extras=False)
# the paint lives in the active colour attribute ("Paint"); the exporter's default ("MATERIAL") only writes a
# colour layer it sees a material use directly, which our paint shaders don't, so ask for the active one
try:
    bpy.ops.export_scene.gltf(**kw, export_vertex_color="ACTIVE", export_all_vertex_colors=False)
except TypeError:
    bpy.ops.export_scene.gltf(**kw)
print("EXPORTED", GLB, "%.1f MB" % (os.path.getsize(GLB) / 1e6))
