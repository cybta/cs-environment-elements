"""Upholstery helpers for the sofa set. Load AFTER bentwood_lib.py:
    exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
    exec(open(os.path.join(HERE, "sofa_lib.py")).read())

sweep(): an arbitrary 2D outline extruded between two planes, with both ends rounded
(the outline is inset as it approaches each end), like a stuffed, piped panel.
Fabric materials: 'PlaidFabric' (generated gingham texture) and 'GreenVelvet'."""
import os, bpy, math
from mathutils import Vector

FABRIC_TILE = 0.5   # metres per fabric texture repeat (8 checks -> ~6 cm squares)

def _ccw(pts):
    a = sum(p[0]*q[1] - q[0]*p[1] for p, q in zip(pts, pts[1:] + pts[:1]))
    return pts if a > 0 else list(reversed(pts))

def offset_outline(pts, d):
    """Inset a CCW outline by d (mitred, clamped so sharp corners don't explode)."""
    n, out = len(pts), []
    for i in range(n):
        p0, p1, p2 = Vector(pts[i-1]), Vector(pts[i]), Vector(pts[(i+1) % n])
        e1, e2 = (p1 - p0).normalized(), (p2 - p1).normalized()
        n1, n2 = Vector((-e1.y, e1.x)), Vector((-e2.y, e2.x))
        m = n1 + n2
        m = n1 if m.length < 1e-6 else m.normalized()
        out.append(p1 + m*d/max(m.dot(n1), 0.35))
    return out

def sweep(outline, w0, w1, r0, r1, to_world, rsegs=3, uv_scale=FABRIC_TILE):
    """Extrude a 2D outline (a, b) from w0 to w1; ends rounded with radius r0 / r1.
    to_world(a, b, w) -> (x, y, z). Returns the new faces (box-UV'd)."""
    pts = _ccw([tuple(p) for p in outline])
    prof = []
    if r0:
        prof += [(r0*(1 - math.sin(t)), w0 + r0*(1 - math.cos(t)))
                 for t in (math.pi/2*k/rsegs for k in range(rsegs + 1))]
    else: prof.append((0, w0))
    if r1:
        prof += [(r1*(1 - math.cos(t)), w1 - r1 + r1*math.sin(t))
                 for t in (math.pi/2*k/rsegs for k in range(rsegs + 1))]
    else: prof.append((0, w1))
    before = set(bm.faces)
    rings = [[bm.verts.new(to_world(p.x, p.y, w)) for p in offset_outline(pts, ins)]
             for ins, w in prof]
    n = len(pts)
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k+1) % n], b[(k+1) % n], b[k]))
    bm.faces.new(rings[0]); bm.faces.new(list(reversed(rings[-1])))
    new = set(bm.faces) - before
    for f in new: f.smooth = True
    uv_box(new, uv_scale); return new

def arc(cx, cy, r, a0, a1, n):
    """Points on a circle from angle a0 to a1 (degrees), n segments, inclusive."""
    return [(cx + r*math.cos(math.radians(a0 + (a1 - a0)*k/n)),
             cy + r*math.sin(math.radians(a0 + (a1 - a0)*k/n))) for k in range(n + 1)]

def rrect(x0, y0, x1, y1, r, segs=4):
    """Rounded rectangle outline from corner (x0, y0) to (x1, y1)."""
    r = min(r, (x1 - x0)/2.01, (y1 - y0)/2.01)
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90),
                       (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        pts += arc(cx, cy, r, a0, a0 + 90, segs)
    return pts

def rolled_arm_outline(width, height, z_bot, overhang):
    """Front-view outline of a rolled (scroll) arm, inner side at a = 0, outer side at
    a = width. The roll (diameter width + overhang) sits on top and overhangs outward."""
    r = (width + overhang)/2
    cx, cz = r, height - r
    return ([(0.0, z_bot), (0.0, cz - 0.05)] + arc(cx, cz, r, 180, -50, 14)
            + [(width, cz - r*0.95), (width, z_bot)])

def tapered_leg(at, height, r_top, r_bot, splay=(0.0, 0.0), segs=10, slot=1):
    """Turned, tapered wood leg hanging from `at` (top centre) down to the floor.
    splay = (dx, dy) offset of the foot relative to the top."""
    faces = new_faces(lathe, [(0, height), (r_top, height), (r_top*0.97, height*0.8),
                              (r_bot, 0.012), (r_bot*0.92, 0), (0, 0)], segs=segs)
    for v in {v for f in faces for v in f.verts}:
        t = 1 - v.co.z/height                       # 0 at top, 1 at foot
        v.co = Vector((v.co.x + at[0] + splay[0]*t, v.co.y + at[1] + splay[1]*t, v.co.z))
    for f in faces: f.material_index = slot
    return faces

def _plaid_image(path, size=512, checks=8):
    """Brown/cream gingham with a fine weave, saved as PNG next to the other textures."""
    import numpy as np
    x = np.arange(size)
    band = ((x*checks//size) % 2 == 0).astype(np.float32)
    h, v = band[None, :], band[:, None]
    dark = np.array([0.30, 0.25, 0.20]); mid = np.array([0.47, 0.41, 0.35])
    light = np.array([0.66, 0.62, 0.54])
    t = (h + v)[..., None]                          # 0 light, 1 mid, 2 dark
    col = np.where(t > 1.5, dark, np.where(t > 0.5, mid, light))
    weave = 0.93 + 0.07*((x[None, :] + x[:, None]) % 4 < 2)[..., None]
    rng = np.random.default_rng(3)
    col = np.clip(col*weave*(0.96 + 0.08*rng.random((size, size, 1))), 0, 1)
    img = bpy.data.images.new("fabric_plaid", size, size)
    rgba = np.concatenate([col, np.ones((size, size, 1))], axis=2).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = path; img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img)

def fabric_material(name):
    mat = bpy.data.materials.get(name)
    if mat: return mat
    mat, bsdf = _new_principled(name)
    if name == "PlaidFabric":
        path = os.path.join(TEX_DIR, "fabric_plaid_512.png")
        if not os.path.exists(path): _plaid_image(path)
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path, check_existing=True)
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 0.92
    elif name == "GreenVelvet":
        bsdf.inputs["Base Color"].default_value = (0.075, 0.16, 0.035, 1)
        bsdf.inputs["Roughness"].default_value = 0.85
        bsdf.inputs["Sheen Weight"].default_value = 0.6
        bsdf.inputs["Sheen Tint"].default_value = (0.55, 0.75, 0.4, 1)
    return mat

WORN_FABRICS = {   # material: (texture prefix, normal strength, sheen)
    "PlaidFabricWorn":  ("fabric_plaid_worn", 0.8, 0.0),
    "GreenVelvetWorn":  ("velvet_green_worn", 0.7, 0.35),
    "ExposedStuffing":  ("stuffing_foam", 1.0, 0.0),
}

def worn_fabric_material(name):
    """Image-textured worn upholstery (make_worn_fabric_textures.py). Base colour is the
    texture multiplied by the mesh's 'Wear' colour attribute (grime from sofa_age_lib),
    a pattern the glTF exporter writes as baseColorTexture + COLOR_0."""
    mat = bpy.data.materials.get(name)
    if mat: return mat
    prefix, nstr, sheen = WORN_FABRICS[name]
    mat, bsdf = _new_principled(name)
    N, L = mat.node_tree.nodes, mat.node_tree.links
    def img(suffix, data):
        n = N.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(TEX_DIR, f"{prefix}_{suffix}_1k.png"),
                                       check_existing=True)
        if data: n.image.colorspace_settings.name = "Non-Color"
        return n
    diff = img("diff", False)
    vc = N.new("ShaderNodeVertexColor"); vc.layer_name = "Wear"
    mix = N.new("ShaderNodeMix"); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs["Factor"].default_value = 1.0
    L.new(diff.outputs["Color"], mix.inputs[6]); L.new(vc.outputs["Color"], mix.inputs[7])
    L.new(mix.outputs[2], bsdf.inputs["Base Color"])
    if name == "ExposedStuffing":
        bsdf.inputs["Roughness"].default_value = 0.95
    else:
        L.new(img("rough", True).outputs["Color"], bsdf.inputs["Roughness"])
        if sheen:
            bsdf.inputs["Sheen Weight"].default_value = sheen
            bsdf.inputs["Sheen Tint"].default_value = (0.5, 0.65, 0.4, 1)
    nm = N.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = nstr
    L.new(img("nor_gl", True).outputs["Color"], nm.inputs["Color"])
    L.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

_ensure_material_base = ensure_material
def ensure_material(name="OldWornWood"):
    if name in ("PlaidFabric", "GreenVelvet"): return fabric_material(name)
    if name in WORN_FABRICS: return worn_fabric_material(name)
    return _ensure_material_base(name)
