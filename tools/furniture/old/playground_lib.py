"""Helpers for the old playground set (ref/playground). Load AFTER bentwood_lib.py:
    exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
    exec(open(os.path.join(HERE, "playground_lib.py")).read())

Adds worn peeled-paint / rust / galvanised materials (see PEELED) and gives:
  bent(pts, r, bend)   polyline tube with rounded bends (welded pipe frames)
  fillet(pts, bend)    the rounded path itself
  ring_tube(...)       closed planar loop (chain links, hoops) with a fixed plane normal
  chain(a, b, ...)     chain of alternating links from a to b
  sheet(path, prof)    a cross-section swept along a path in the YZ plane (slide chute)
  paint(faces, slot)   set the material slot of faces (+ random UV offset per part)
  part(name, slots, parent, at)  finish() a moving part as a child with its own pivot
"""
import math
from mathutils import Vector, Quaternion

SIMPLE_MATERIALS.update({
    "Rubber": ((0.02, 0.02, 0.02), 0.85, 0.0, None, 0),  # foot caps, bumpers
})

# Worn textured materials (maps from make_peeled_textures.py, in ../textures).
# name: (paint colour, what shows through the peeled paint)
PEELED = {
    "PaintRed": ("red", "rust"), "PaintBlue": ("blue", "rust"), "PaintGreen": ("green", "rust"),
    "PaintYellow": ("yellow", "rust"),
    "DarkSteel": ("dark", "rust"),           # chains, bench arches, pivots: dark paint gone to rust
    "PeeledWoodRed": ("red", "wood"), "PeeledWoodBlue": ("blue", "wood"),
    "PeeledWoodGreen": ("green", "wood"), "PeeledWoodYellow": ("yellow", "wood"),
}

def _textured(name, maps, normal_strength=0.6):
    """Principled with plain image links only (exports cleanly to glTF / Godot)."""
    mat, bsdf = _new_principled(name)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    for socket, fname in maps.items():
        n = N.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(TEX_DIR, fname), check_existing=True)
        if socket != "Base Color": n.image.colorspace_settings.name = "Non-Color"
        if socket == "Normal":
            nm = N.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = normal_strength
            L.new(n.outputs["Color"], nm.inputs["Color"]); L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        else:
            L.new(n.outputs["Color"], bsdf.inputs[socket])
    if "Metallic" not in maps: bsdf.inputs["Metallic"].default_value = 0.0
    return mat

_base_ensure_material = ensure_material
def ensure_material(name="OldWornWood"):
    mat = bpy.data.materials.get(name)
    if mat: return mat
    if name in PEELED:
        colour, under = PEELED[name]
        return _textured(name, {"Base Color": f"peeled_{colour}_{under}_diff_1k.png",
                                "Roughness": f"peeled_{under}_rough_1k.png",
                                "Normal": f"peeled_{under}_nor_gl_1k.png"})
    if name == "GalvSteel":                  # slide chute, bin liner
        return _textured(name, {"Base Color": "galv_worn_diff_1k.png", "Roughness": "galv_worn_rough_1k.png",
                                "Metallic": "galv_worn_metal_1k.png", "Normal": "galv_worn_nor_gl_1k.png"}, 0.4)
    return _base_ensure_material(name)

import random as _random
_uv_rng = _random.Random(11)

def paint(faces, slot):
    """Set the material slot, and shift the part's UVs by a random amount so
    identical pipes and planks don't show the same patch of wear."""
    du, dv = _uv_rng.random(), _uv_rng.random()
    for f in faces:
        f.material_index = slot
        for l in f.loops: l[uvl].uv = (l[uvl].uv[0] + du, l[uvl].uv[1] + dv)
    return faces

def V(*a): return Vector(a if len(a) == 3 else a[0])

def fillet(pts, bend, seg=6):
    """Polyline with every inner corner replaced by an arc of radius `bend`."""
    pts = [V(p) for p in pts]
    out = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        d1, d2 = (a - b).normalized(), (c - b).normalized()
        ang = d1.angle(d2)
        if ang > math.pi - 1e-3: out.append(b); continue      # straight, no bend
        r = min(bend, (a-b).length*0.49*math.tan(ang/2), (c-b).length*0.49*math.tan(ang/2))
        t = r/math.tan(ang/2)
        p0, p1 = b + d1*t, b + d2*t
        ctr = b + (d1 + d2).normalized()*(r/math.sin(ang/2))
        v0, v1 = p0 - ctr, p1 - ctr
        sweep = v0.angle(v1)
        axis = v0.cross(v1).normalized()
        for k in range(seg + 1):
            out.append(ctr + Quaternion(axis, sweep*k/seg) @ v0)
    out.append(pts[-1])
    return out

def bent(pts, r, bend=0.08, sides=10, seg=6):
    """Welded pipe through the points with rounded bends. Returns the new faces."""
    return new_faces(tube, fillet(pts, bend, seg), r, sides=sides)

def ring_tube(pts, r, normal, sides=6):
    """Closed tube along a planar loop; `normal` is the loop's plane normal (no twist)."""
    pts = [V(p) for p in pts]; n = len(pts); N = V(normal).normalized()
    before = set(bm.faces); rings = []
    for i, p in enumerate(pts):
        t = (pts[(i+1) % n] - pts[i-1]).normalized()
        side = t.cross(N).normalized()
        rings.append([bm.verts.new(p + (side*math.cos(a) + N*math.sin(a))*r)
                      for a in (2*math.pi*k/sides for k in range(sides))])
    for i in range(n):
        j = (i+1) % n
        for k in range(sides):
            f = bm.faces.new((rings[i][k], rings[i][(k+1) % sides], rings[j][(k+1) % sides], rings[j][k]))
            f.smooth = True
    new = set(bm.faces) - before; uv_box(new, 0.05); return new

def stadium(a, b, half_w, axis_w, seg=4):
    """Points of an elongated loop between centres a and b, widened along axis_w."""
    a, b = V(a), V(b); d = (b - a).normalized(); w = V(axis_w).normalized()
    pts = []
    for c, base in ((b, 0), (a, math.pi)):
        for k in range(seg + 1):
            ang = base - math.pi/2 + math.pi*k/seg
            pts.append(c + (d*math.cos(ang) + w*math.sin(ang))*half_w)
    return pts

def chain(top, bottom, wire=0.0032, pitch=0.034, width=0.011, sides=4):
    """Alternating flat links hanging from top to bottom. Returns faces."""
    top, bottom = V(top), V(bottom)
    d = bottom - top; L = d.length; d.normalize()
    n = max(2, round(L/pitch))
    step = L/n
    a1 = d.cross(V(0, 0, 1)) if abs(d.z) < 0.9 else V(1, 0, 0)
    a1.normalize(); a2 = d.cross(a1).normalized()
    faces = set()
    for i in range(n):
        p = top + d*(i*step); q = top + d*((i+1)*step)
        w = a1 if i % 2 == 0 else a2
        inset = wire*0.6                                       # links overlap: they interlock
        loop = stadium(p + d*(width - inset), q - d*(width - inset), width, w)
        faces |= ring_tube(loop, wire, w.cross(d), sides)
    return faces

def sheet(path, profile, x_axis=V(1, 0, 0)):
    """Sweep a closed (x, h) profile along a path of points in the YZ plane.
    h is offset along the path's upward normal. Capped ends. Returns faces."""
    path = [V(p) for p in path]; n = len(path)
    before = set(bm.faces); rings = []
    for i, p in enumerate(path):
        t = (path[min(i+1, n-1)] - path[max(i-1, 0)]).normalized()
        up = x_axis.cross(t).normalized()
        if up.z < 0: up = -up
        rings.append([bm.verts.new(p + x_axis*x + up*h) for x, h in profile])
    m = len(profile)
    for a, b in zip(rings, rings[1:]):
        for k in range(m):
            f = bm.faces.new((a[k], a[(k+1) % m], b[(k+1) % m], b[k])); f.smooth = False
    bm.faces.new(list(reversed(rings[0]))); bm.faces.new(rings[-1])
    new = set(bm.faces) - before; uv_box(new); return new

def part(name, mats, parent=None, at=(0, 0, 0)):
    """finish() the current bmesh as `name`, parented with its origin at `at` (world)."""
    ob = finish(name, location=at, material=mats)
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob

def offset_verts(faces, by):
    """Move the verts of `faces` by `by` (build a part in world space, then centre it on its pivot)."""
    for v in {v for f in faces for v in f.verts}: v.co -= V(by)

def center_footprint():
    """Move the whole mesh so the origin is on the floor at the centre of the XY footprint."""
    xs = [v.co.x for v in bm.verts]; ys = [v.co.y for v in bm.verts]; zs = [v.co.z for v in bm.verts]
    c = Vector(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, min(zs)))
    for v in bm.verts: v.co -= c
    return c
