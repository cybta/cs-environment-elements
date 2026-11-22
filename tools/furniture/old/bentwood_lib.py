"""Shared helpers for the bentwood furniture set (game-ready geometry).

Build scripts load this with:
    HERE = os.path.dirname(os.path.abspath(__file__))
    exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
then call begin(), build parts, and finish(name, location).
Textures are expected in ../textures relative to this scripts folder."""
import os, bpy, bmesh, math
from mathutils import Vector

TILE = 0.6   # metres of furniture per texture repeat (same across the set)
TEX_DIR = os.path.normpath(os.path.join(globals().get("HERE", ""), "..", "textures"))
bm = uvl = None

def _new_principled(name):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    return mat, next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")

# Plain-value materials (no textures, glTF/Godot friendly):
# name: (base colour, roughness, metallic, emission colour or None, emission strength)
SIMPLE_MATERIALS = {
    "CreamEnamel": ((0.74, 0.71, 0.62), 0.42, 0.0, None, 0),   # 80s cream-painted metal
    "BulbGlow":    ((1.0, 0.93, 0.8),   0.4,  0.0, (1.0, 0.82, 0.55), 6.0),  # opal bulb
    "BlackEnamel": ((0.018, 0.017, 0.016), 0.32, 0.0, None, 0),  # knobs, burner caps, plinth
    "CastIron":    ((0.075, 0.055, 0.042), 0.68, 0.55, None, 0), # pan supports, slightly rusty
    "Aluminium":   ((0.72, 0.72, 0.70), 0.38, 1.0, None, 0),     # burner rings, knob bezels
    "OvenGlass":   ((0.012, 0.012, 0.014), 0.06, 0.0, None, 0),  # dark glossy oven window
    "AgedCreamEnamel": ((0.70, 0.63, 0.47), 0.5, 0.0, None, 0),  # yellowed 50s fridge enamel
    "Chrome":      ((0.85, 0.85, 0.85), 0.12, 1.0, None, 0),     # handle, badge trim
    "BadgeBlue":   ((0.03, 0.07, 0.20), 0.3,  0.3, None, 0),     # enamel nameplate strip
    "BadgeGold":   ((0.78, 0.56, 0.18), 0.3,  1.0, None, 0),     # emblem centre
}

def _simple(name):
    base, rough, metal, emit, strength = SIMPLE_MATERIALS[name]
    mat, bsdf = _new_principled(name)
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat

def ensure_material(name="OldWornWood"):
    """Get or create a shared set material by name."""
    mat = bpy.data.materials.get(name)
    if mat: return mat
    if name in SIMPLE_MATERIALS: return _simple(name)
    return _worn_wood(name)

def _worn_wood(name):
    """Shared worn-walnut PBR material (Poly Haven 'Worn Wood Table', CC0).
    Plain image -> Principled links only, so it exports cleanly to glTF/Godot."""
    mat, bsdf = _new_principled(name)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    def img(fname, data):
        n = N.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(TEX_DIR, fname), check_existing=True)
        if data: n.image.colorspace_settings.name = "Non-Color"
        return n
    L.new(img("wood_table_worn_diff_dark_2k.jpg", False).outputs["Color"], bsdf.inputs["Base Color"])
    L.new(img("wood_table_worn_rough_varnish_2k.jpg", True).outputs["Color"], bsdf.inputs["Roughness"])
    nm = N.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.45
    L.new(img("wood_table_worn_nor_gl_2k.jpg", True).outputs["Color"], nm.inputs["Color"])
    L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

def begin():
    global bm, uvl
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new("UVMap")

def catmull(pts, seg=12):
    """Smooth path through evenly spaced control points (uneven spacing overshoots)."""
    out = []
    P = [pts[0] + (pts[0]-pts[1])] + pts + [pts[-1] + (pts[-1]-pts[-2])]
    for i in range(1, len(P)-2):
        p0, p1, p2, p3 = P[i-1], P[i], P[i+1], P[i+2]
        for k in range(seg):
            t = k/seg; t2, t3 = t*t, t*t*t
            out.append(0.5*((2*p1) + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t2 + (-p0+3*p1-3*p2+p3)*t3))
    out.append(pts[-1].copy()); return out

def at_z(line, z):
    for p, q in zip(line, line[1:]):
        if (p.z-z)*(q.z-z) <= 0 and p.z != q.z:
            return p.lerp(q, (z-p.z)/(q.z-p.z))

def tube(path, radius, sides=8, closed=False):
    """Tube along path; capped unless closed (a loop). U runs along the length = grain."""
    pts = list(path)
    if closed and (pts[0]-pts[-1]).length < 1e-6: pts = pts[:-1]
    n = len(pts)
    rad = radius if callable(radius) else (lambda t: radius)
    def tan(i):
        if closed: return (pts[(i+1) % n] - pts[i-1]).normalized()
        return (pts[min(i+1, n-1)] - pts[max(i-1, 0)]).normalized()
    t0 = tan(0)
    up = Vector((0, 0, 1)) if abs(t0.z) < 0.9 else Vector((1, 0, 0))
    nrm = t0.cross(up).normalized()
    length = [0.0]
    for i in range(1, n): length.append(length[-1] + (pts[i]-pts[i-1]).length)
    total = length[-1] + ((pts[0]-pts[-1]).length if closed else 0)
    rings = []
    for i, p in enumerate(pts):
        t = tan(i)
        if closed: nrm = (up - t*up.dot(t)).normalized()     # loops: fixed up axis, no twist seam
        else: nrm = (nrm - t*nrm.dot(t)).normalized()        # parallel transport
        b = t.cross(nrm); r = rad(length[i]/total if total else 0)
        rings.append([bm.verts.new(p + (nrm*math.cos(a) + b*math.sin(a))*r)
                      for a in (2*math.pi*k/sides for k in range(sides))])
    circ = 2*math.pi*rad(0.5)
    segs = n if closed else n-1
    for i in range(segs):
        j = (i+1) % n
        u0, u1 = length[i]/TILE, (length[j] if j else total)/TILE
        for k in range(sides):
            k2 = (k+1) % sides
            f = bm.faces.new((rings[i][k], rings[i][k2], rings[j][k2], rings[j][k])); f.smooth = True
            for l, (u, kk) in zip(f.loops, ((u0, k), (u0, k+1), (u1, k+1), (u1, k))):
                l[uvl].uv = (u, kk/sides*circ/TILE)
    if not closed:
        for ring, rev in ((rings[0], True), (rings[-1], False)):
            f = bm.faces.new(list(reversed(ring)) if rev else ring)
            c = sum((v.co for v in ring), Vector())/sides
            for l in f.loops:
                d = l.vert.co - c; l[uvl].uv = (d.x/TILE + 0.3, d.y/TILE + 0.7)

def lathe(profile, segs=48):
    """Revolve (r, z) profile around Z; r=0 points become a centre vertex.
    Flat faces get planar UVs (grain along X), the rest wrap round the circumference."""
    before = set(bm.faces)
    rings = []
    for (r, z) in profile:
        rings.append(None if r < 1e-6 else
                     [bm.verts.new((r*math.cos(2*math.pi*k/segs), r*math.sin(2*math.pi*k/segs), z)) for k in range(segs)])
    centers = {}
    for i in range(len(profile)-1):
        a, b = rings[i], rings[i+1]
        for k in range(segs):
            k2 = (k+1) % segs
            if a is None:
                c = centers.setdefault(i, bm.verts.new((0, 0, profile[i][1]))); f = bm.faces.new((c, b[k], b[k2]))
            elif b is None:
                c = centers.setdefault(i+1, bm.verts.new((0, 0, profile[i+1][1]))); f = bm.faces.new((a[k], c, a[k2]))
            else:
                f = bm.faces.new((a[k], a[k2], b[k2], b[k]))
            f.smooth = True
    for f in set(bm.faces) - before:
        f.normal_update()
        if abs(f.normal.z) > 0.7:
            for l in f.loops: l[uvl].uv = (l.vert.co.x/TILE, l.vert.co.y/TILE)
        else:
            angs = [math.atan2(l.vert.co.y, l.vert.co.x) for l in f.loops]
            if max(angs) - min(angs) > math.pi: angs = [a + 2*math.pi if a < 0 else a for a in angs]
            for l, a in zip(f.loops, angs):
                l[uvl].uv = (a*l.vert.co.xy.length/TILE, l.vert.co.z/TILE)

def uv_box(faces, scale=1.0):
    """Box projection: each face projected on its dominant axis, `scale` metres per UV unit."""
    for f in faces:
        f.normal_update(); n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for l in f.loops: l[uvl].uv = (l.vert.co[a]/scale, l.vert.co[b]/scale)

def box(lo, hi, bevel=0.0, segs=2):
    """Axis-aligned box from corner lo to hi, optional rounded edges. Returns its faces."""
    before = set(bm.faces)
    vs = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    lo, hi = Vector(lo), Vector(hi); c, s = (lo + hi)/2, hi - lo
    for v in vs: v.co = Vector((v.co.x*s.x, v.co.y*s.y, v.co.z*s.z)) + c
    if bevel > 0:
        edges = list({e for v in vs for e in v.link_edges})
        bmesh.ops.bevel(bm, geom=edges, offset=min(bevel, min(s)/2.2), segments=segs,
                        profile=0.5, affect='EDGES', clamp_overlap=True)
    new = set(bm.faces) - before
    for f in new: f.smooth = bevel > 0
    uv_box(new); return new

def new_faces(fn, *a, **k):
    """Run a builder and return the faces it added."""
    before = set(bm.faces); fn(*a, **k); return set(bm.faces) - before

def facing_front(faces, at):
    """Turn parts built along +Z (e.g. lathe) to point out of the front (-Y), then move to `at`."""
    vs = list({v for f in faces for v in f.verts})
    for v in vs:
        x, y, z = v.co
        v.co = Vector((x, -z, y)) + Vector(at)

def ring_profile(r_in, r_out, z0, z1, c=0.003):
    """Closed rounded-rectangle profile for a bentwood ring (seat rim, apron)."""
    return [(r_in, z1), (r_out - c, z1), (r_out, z1 - c), (r_out, z0 + c),
            (r_out - c, z0), (r_in + c, z0), (r_in, z0 + c), (r_in, z1)]

def finish(name, location=(0, 0, 0), material="OldWornWood"):
    global bm
    old = bpy.data.objects.get(name)
    if old: bpy.data.objects.remove(old, do_unlink=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); bm = None
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    for m in (material if isinstance(material, (list, tuple)) else [material]):
        me.materials.append(ensure_material(m))      # face.material_index picks the slot
    ob.location = location
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_auto_smooth(angle=math.radians(60))
    b2 = bmesh.new(); b2.from_mesh(me)
    print(name, "tris", sum(len(f.verts)-2 for f in b2.faces),
          "boundary", sum(e.is_boundary for e in b2.edges),
          "non-manifold", sum(not e.is_manifold for e in b2.edges),
          "dims", tuple(round(v, 3) for v in ob.dimensions))
    b2.free()
    return ob
