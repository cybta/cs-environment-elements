"""Make the ACTIVE mesh object game-ready (the steps used on OldBentwoodChair).

1. weld loose tube caps         2. fill open tube ends
3. merge near-flat faces        4. symmetric collapse decimate (X mirror)
5. fresh UVs: smart project, each island rotated so the wood grain (texture U)
   follows the part's long direction, one texel density, random offsets.

Run in Blender (Text Editor > Open > Run Script) with the object selected/active.
Save a backup first: steps 3-4 are destructive.
"""
import bpy, bmesh, math, random
from mathutils import Vector
from bpy_extras.bmesh_utils import bmesh_linked_uv_islands

DISSOLVE_ANGLE = 4.0     # degrees; faces flatter than this get merged
DECIMATE_RATIO = 0.62    # extra collapse after dissolving (1.0 = skip)
TILE = 0.6               # metres per texture repeat (same across the furniture set)

ob = bpy.context.active_object
assert ob and ob.type == 'MESH', "Select a mesh object first"
bpy.ops.object.mode_set(mode='OBJECT')
me = ob.data
tris = lambda m: sum(len(p.vertices) - 2 for p in m.polygons)
start = tris(me)

# 1-3: weld, fill, dissolve
bm = bmesh.new(); bm.from_mesh(me)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0002)
bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=64)
left = [e for e in bm.edges if e.is_boundary]
if left: bmesh.ops.edgeloop_fill(bm, edges=left)
bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(DISSOLVE_ANGLE), use_dissolve_boundaries=False,
                         verts=bm.verts, edges=bm.edges, delimit={'NORMAL'})
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if 4 < len(f.verts) < 9])
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
bm.to_mesh(me); bm.free()

# 4: symmetric decimate
if DECIMATE_RATIO < 1.0:
    dm = ob.modifiers.new("GameDecimate", 'DECIMATE')
    dm.ratio = DECIMATE_RATIO; dm.use_symmetry = True; dm.symmetry_axis = 'X'
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_move_to_index(modifier=dm.name, index=0)
    bpy.ops.object.modifier_apply(modifier=dm.name)

# 5: grain-aligned UVs
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.0, scale_to_bounds=False)
bpy.ops.object.mode_set(mode='OBJECT')
random.seed(7)
bm = bmesh.new(); bm.from_mesh(me)
uv = bm.loops.layers.uv.active
for faces in bmesh_linked_uv_islands(bm, uv):
    a3 = sum(f.calc_area() for f in faces); auv = 0
    for f in faces:
        p = [l[uv].uv for l in f.loops]
        auv += abs(sum(p[i].x*p[i-1].y - p[i-1].x*p[i].y for i in range(len(p))))/2
    if auv < 1e-12: continue
    s = math.sqrt(a3/auv)/TILE
    loops = [l for f in faces for l in f.loops]
    c = sum((l[uv].uv for l in loops), Vector((0, 0)))/len(loops)
    sxx = sum((l[uv].uv.x-c.x)**2 for l in loops); syy = sum((l[uv].uv.y-c.y)**2 for l in loops)
    sxy = sum((l[uv].uv.x-c.x)*(l[uv].uv.y-c.y) for l in loops)
    ang = 0.5*math.atan2(2*sxy, sxx-syy); ca, sa = math.cos(-ang), math.sin(-ang)
    off = Vector((random.random(), random.random()))
    for l in loops:
        q = (l[uv].uv - c)*s
        l[uv].uv = Vector((q.x*ca - q.y*sa, q.x*sa + q.y*ca)) + off
bm.to_mesh(me); bm.free()

b = bmesh.new(); b.from_mesh(me)
print(f"{ob.name}: {start} -> {tris(me)} tris, boundary {sum(e.is_boundary for e in b.edges)}, "
      f"non-manifold {sum(not e.is_manifold for e in b.edges)}")
b.free()
