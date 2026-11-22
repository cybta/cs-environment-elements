"""Old clothesline set (ref: the user's sheet: two T-posts, three sagging ropes, a prop
pole, pegs, sheets and towels, peg bag, wicker basket, wash tub).

  ClotheslineLaundry   two weathered T-posts 4.6 m apart (braced crossbars, rusty eye hooks),
                       three ropes sagging between them, a prop pole holding up the front
                       rope, a peg bag on the right post, and the washing pegged out: sheets,
                       towels, tea towels, blankets (flat cloth only; cut-out garments looked 2D)
  ClotheslineEmpty     the same posts, ropes and prop pole, nothing hanging
  LaundryBasket        woven wicker basket with two handles, heaped with folded washing
  WashTub              galvanised round tub with ribs and two handles, a towel over the rim

Origins on the floor at the centre; the ropes run along X, the prop pole stands out to the
front (-Y). All the washing shares ONE opaque material, LaundryCloth: an atlas of eight
cloths (laundry_textures.py); each piece is a wrinkled grid pegged to a rope, or folded
over it. Slots on the clothesline: 0 fence wood,
1 DarkSteel (eye hooks), 2 LaundryRope, 3 LaundryPeg, 4 LaundryCloth.

Saves cs_environment_elements/props/assets/garden/clothesline.blend (+ textures/) and,
unless RENDER=0, render/clothesline.png beside this script.
Headless:  blender -b --factory-startup --python build_clothesline.py
"""
import os, math, random, importlib.util
import bpy, bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
PKG = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements"))
OUT_DIR = os.path.join(PKG, "props", "assets", "garden")
TEXL = os.path.join(OUT_DIR, "textures")

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
TEX_DIR = os.path.join(PKG, "props", "assets", "playground", "textures")
_spec = importlib.util.spec_from_file_location("fence_geom", os.path.join(PKG, "buildings", "fence_geom.py"))
fg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fg)
exec(open(os.path.join(HERE, "laundry_textures.py")).read())
rng = random.Random(31)
WOOD = fg.MAT_WOOD
WOOD_I, STEEL_I, ROPE_I, PEG_I, CLOTH_I = 0, 1, 2, 3, 4
exec(open(os.path.join(HERE, "plank_lib.py")).read())          # strip(), plank(), round_leg()

SIMPLE_MATERIALS.update({
    "LaundryRope": ((0.50, 0.43, 0.32), 0.9, 0.0, None, 0),
    "LaundryPeg": ((0.68, 0.55, 0.38), 0.6, 0.0, None, 0),
})

def cloth_material():
    mat = bpy.data.materials.new("LaundryCloth"); mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.join(TEXL, "laundry_atlas_2k.png"), check_existing=True)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nor = nt.nodes.new("ShaderNodeTexImage")
    nor.image = bpy.data.images.load(os.path.join(TEXL, "laundry_atlas_nor_2k.png"), check_existing=True)
    nor.image.colorspace_settings.name = "Non-Color"
    nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.5
    nt.links.new(nor.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    bsdf.inputs["Roughness"].default_value = 0.85
    mat.use_backface_culling = False          # single-sided cards: show both faces
    return mat

_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    if name == WOOD:
        return fg.wood_material()
    if bpy.data.materials.get(name):
        return bpy.data.materials[name]
    if name == "LaundryCloth":
        return cloth_material()
    if name == "Wicker":
        old = TEX_DIR
        try:
            globals()["TEX_DIR"] = TEXL
            return _textured("Wicker", {"Base Color": "wicker_1k.png", "Normal": "wicker_nor_1k.png"}, 0.8)
        finally:
            globals()["TEX_DIR"] = old
    return _pg_ensure(name)

# ---------------------------------------------------------------- ropes

class Rope:
    """A rope through anchors, sagging (parabola) by `sags[i]` between anchor i and i + 1."""
    def __init__(self, anchors, sags):
        self.a = [Vector(p) for p in anchors]; self.sags = sags
        self.y = self.a[0].y

    def at(self, x):
        for (p, q), s in zip(zip(self.a, self.a[1:]), self.sags):
            if p.x - 1e-6 <= x <= q.x + 1e-6:
                t = (x - p.x) / (q.x - p.x)
                v = p.lerp(q, t); v.z -= s * 4 * t * (1 - t)
                return v
        return self.a[0] if x < self.a[0].x else self.a[-1]

    def points(self, step=0.12):
        x0, x1 = self.a[0].x, self.a[-1].x
        n = max(2, int((x1 - x0) / step))
        return [self.at(x0 + (x1 - x0) * k / n) for k in range(n + 1)]

def rope_mesh(rope):
    fs = new_faces(tube, rope.points(), 0.0065, sides=6)
    for f in fs: f.material_index = ROPE_I
    return fs

def ring(centre, axis, R=0.026, r=0.006, n=8):
    """Eye hook: a steel ring round `axis` with a short shank back along -axis."""
    axis = Vector(axis).normalized(); u = axis.orthogonal().normalized(); v = axis.cross(u)
    pts = [Vector(centre) + (u * math.cos(2 * math.pi * k / n) + v * math.sin(2 * math.pi * k / n)) * R for k in range(n)]
    fs = new_faces(tube, pts, r, sides=5, closed=True)
    return paint(fs, STEEL_I)

# ---------------------------------------------------------------- washing

def peg(x, rope):
    p = rope.at(x)
    for sy in (-1, 1):
        fs = box((x - 0.006, p.y + sy * 0.0045 - 0.0035, p.z - 0.055), (x + 0.006, p.y + sy * 0.0045 + 0.0035, p.z + 0.02),
                 bevel=0.0015, segs=1)
        for f in fs: f.material_index = PEG_I

def hang(rope, x0, x1, length, cell, fold=False, sub=None, pegs=2, nx=10, ny=10, side=-1):
    """A piece of washing pegged to `rope` from x0 to x1, `length` down (each side, if folded
    over the rope). `cell` is the atlas cell; `sub` (u0, v0, u1, v1) a part of it."""
    cu0, cv0, cu1, cv1 = CELL_UV(cell)
    su0, sv0, su1, sv1 = sub or (0.0, 0.0, 1.0, 1.0)
    U = lambda a: cu0 + (cu1 - cu0) * (su0 + (su1 - su0) * a)            # noqa: E731
    V = lambda b: cv0 + (cv1 - cv0) * (sv0 + (sv1 - sv0) * b)            # noqa: E731
    peg_x = [x0 + 0.04 + (x1 - x0 - 0.08) * k / max(1, pegs - 1) for k in range(pegs)]
    ph = [rng.uniform(0, 6.28) for _ in range(4)]
    k1, k2 = rng.uniform(14, 22), rng.uniform(30, 45)
    rows = (2 * ny) if fold else ny
    grid = []
    for j in range(rows + 1):
        row = []
        for i in range(nx + 1):
            a = i / nx
            x = x0 + (x1 - x0) * a
            top = rope.at(x)
            seg = min(peg_x, key=lambda q: abs(q - x))
            between = [q for q in peg_x if q != seg]
            gap = min((abs(q - seg) for q in between), default=x1 - x0)
            droop = 0.03 * math.sin(math.pi * min(1.0, abs(x - seg) / max(gap, 1e-3))) if pegs > 1 else 0.0
            if fold:
                s = j / ny - 1.0                                         # -1 back side .. 1 front side
                t = abs(s)
                sd = 1 if s >= 0 else -1
                b = (s + 1) / 2
            else:
                t, sd, b = j / ny, side, 1 - j / ny
            wr = (0.03 * math.sin(x * k1 + ph[0]) + 0.011 * math.sin(x * k2 + ph[1])) * t ** 0.7
            wr += 0.012 * math.sin(t * 9 + ph[2]) * math.sin(x * 6 + ph[3]) * t
            z = top.z - droop * min(1, t * 4) - t * length * (1 + 0.04 * math.sin(x * 11 + ph[1]) * t)
            y = top.y + sd * (0.008 + 0.025 * t ** 1.3) + wr
            v = bm.verts.new((x, y, z))
            row.append((v, U(a), V(b)))
        grid.append(row)
    fs = []
    for r0, r1 in zip(grid, grid[1:]):
        for i in range(nx):
            q = (r0[i], r0[i + 1], r1[i + 1], r1[i])
            f = bm.faces.new([c[0] for c in q])
            f.material_index = CLOTH_I; f.smooth = True
            for l, c in zip(f.loops, q): l[uvl].uv = (c[1], c[2])
            fs.append(f)
    for x in peg_x:
        peg(x, rope)
    return fs

# ---------------------------------------------------------------- posts, pole, bag

X_POST, CROSS_Z = 2.3, 1.99
ROPE_YS = (-0.45, 0.0, 0.45)

def brace(a, b, w=0.07, t=0.06):
    a, b = Vector(a), Vector(b); d = b - a; L = d.length
    fs = plank((-w / 2, -t / 2, -L / 2), (w / 2, t / 2, L / 2), 2, bevel=0.004)
    m = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix()
    c = (a + b) / 2
    for v in {v for f in fs for v in f.verts}: v.co = m @ v.co + c
    return fs

def post(sx):
    x = sx * X_POST
    plank((x - 0.065, -0.065, 0), (x + 0.065, 0.065, 2.16), 2, bevel=0.008)
    plank((x - 0.06, -0.66, 1.93), (x + 0.06, 0.66, 2.05), 1, bevel=0.008)
    for sy in (-1, 1):
        brace((x, sy * 0.05, 1.42), (x, sy * 0.42, 1.95))
    for y in ROPE_YS:                                                   # eye hooks on the inner face
        ring((x - sx * 0.09, y, CROSS_Z), (0, 1, 0))
        paint(new_faces(tube, [Vector((x - sx * 0.06, y, CROSS_Z)), Vector((x - sx * 0.066, y, CROSS_Z))], 0.005, sides=5),
              STEEL_I)
        ring((x - sx * 0.1, y, CROSS_Z - 0.004), (1, 0, 0), R=0.012, r=0.0065, n=6)        # the knot

def ropes(prop_x):
    ax = X_POST - 0.09
    out = []
    for y in ROPE_YS:
        if y == ROPE_YS[0]:                                             # the front rope rests on the prop pole
            r = Rope([(-ax, y, CROSS_Z), (prop_x, y, CROSS_Z - 0.06), (ax, y, CROSS_Z)], [0.1, 0.12])
        else:
            r = Rope([(-ax, y, CROSS_Z), (ax, y, CROSS_Z)], [0.22 if y == 0 else 0.18])
        rope_mesh(r); out.append(r)
    return out

def prop_pole(rope, x):
    top = rope.at(x)
    foot = Vector((x + 0.4, top.y - 0.75, 0.0))
    d = (top - foot).normalized()
    round_leg(foot, top - d * 0.04, 0.022, 0.019, sides=8)
    for s in (-1, 1):                                                   # the fork the rope sits in
        tip = top + Vector((s * 0.035, 0, 0.03))
        round_leg(top - d * 0.06, tip, 0.012, 0.009, sides=6)

def peg_bag(sx):
    x = sx * X_POST - sx * 0.075
    hook = Vector((x - sx * 0.02, 0.0, 1.45))
    paint(bent([(sx * X_POST - sx * 0.065, 0, 1.47), (hook.x, 0, 1.47), (hook.x, 0, 1.43)], 0.004, bend=0.01, sides=5), STEEL_I)
    top = hook - Vector((sx * 0.1, 0, 0.04))
    prof = [(0, -0.24), (0.06, -0.235), (0.095, -0.19), (0.105, -0.11), (0.1, -0.03), (0.085, 0.0), (0.0, -0.01)]
    fs = new_faces(lathe, prof, segs=12)
    cu0, cv0, cu1, cv1 = CELL_UV(0)
    for f in fs:
        f.material_index = CLOTH_I
        for l in f.loops:
            a = (math.atan2(l.vert.co.y, l.vert.co.x) / (2 * math.pi)) % 1.0
            l[uvl].uv = (cu0 + (cu1 - cu0) * (0.1 + 0.8 * a), cv0 + (cv1 - cv0) * (0.3 + 0.6 * (l.vert.co.z + 0.24) / 0.24))
    for v in {v for f in fs for v in f.verts}: v.co += top
    paint(new_faces(tube, [top + Vector((sx * 0.06, 0, 0.0)), hook], 0.003, sides=4), ROPE_I)
    for k in range(4):                                                  # pegs poking out of the mouth
        a = k * 1.6
        p = top + Vector((math.cos(a) * 0.04, math.sin(a) * 0.04, -0.03))
        f = box((p.x - 0.006, p.y - 0.004, p.z), (p.x + 0.006, p.y + 0.004, p.z + 0.07), bevel=0.0015, segs=1)
        for ff in f: ff.material_index = PEG_I

def clean():
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")

MATS = [WOOD, "DarkSteel", "LaundryRope", "LaundryPeg", "LaundryCloth"]
PROP_X = -0.22

def clothesline(name, washing):
    begin()
    post(-1); post(1)
    front, mid, back = ropes(PROP_X)
    prop_pole(front, PROP_X)
    peg_bag(1)
    if washing:
        hang(front, -1.95, -1.5, 0.75, 1, pegs=2)                                   # beige towel
        hang(front, -1.4, -0.4, 0.62, 0, fold=True, pegs=3)                         # sheet over the rope
        hang(front, -0.05, 0.4, 0.5, 4, pegs=2)                                     # tea towel
        hang(front, 0.55, 1.45, 0.55, 5, fold=True, pegs=3)                         # grey wool blanket
        hang(front, 1.6, 1.95, 0.6, 7, pegs=2)                                      # yellow towel
        hang(mid, -1.95, -0.9, 1.05, 0, pegs=3, side=1)                             # sheet
        hang(mid, -0.75, 0.4, 0.68, 3, fold=True, pegs=3)                           # floral sheet
        hang(mid, 0.6, 0.95, 0.55, 1, pegs=2, side=1)                               # beige towel
        hang(mid, 1.15, 1.95, 0.9, 6, pegs=3, side=1)                               # striped linen
        hang(back, -1.0, 0.15, 0.55, 2, fold=True, pegs=3)                          # plaid blanket
        hang(back, 0.3, 1.05, 0.62, 6, fold=True, pegs=3)                           # striped linen
        hang(back, 1.25, 1.65, 0.5, 4, pegs=2, side=1)                              # tea towel
    clean()
    return finish(name, material=MATS)

# ---------------------------------------------------------------- basket, tub

def heap(c, r, h, cell, seed):
    """A lumpy mound of folded washing (a domed grid) at c, mapped to an atlas cell."""
    g = random.Random(seed)
    cu0, cv0, cu1, cv1 = CELL_UV(cell)
    n = 10
    lumps = [(Vector((g.uniform(-r, r) * 0.6, g.uniform(-r, r) * 0.6)), g.uniform(0.06, 0.12), g.uniform(0.01, 0.04))
             for _ in range(7)]
    vs = []
    for j in range(n + 1):
        row = []
        for i in range(n + 1):
            x, y = -r + 2 * r * i / n, -r + 2 * r * j / n
            d = math.hypot(x, y) / r
            z = h * max(0.0, 1 - d * d) if d < 1 else -0.02
            for p, rr, a in lumps:
                e = (Vector((x, y)) - p).length / rr
                if e < 1: z += a * (1 - e * e) ** 2 * max(0.0, 1 - d)
            row.append(bm.verts.new((c.x + x * min(1, 1.0 / max(d, 1e-6)) if d > 1 else c.x + x, c.y + (y if d <= 1 else y / d), c.z + z)))
        vs.append(row)
    for j in range(n):
        for i in range(n):
            f = bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
            f.material_index = 1; f.smooth = True
            for l in f.loops:
                l[uvl].uv = (cu0 + (cu1 - cu0) * ((l.vert.co.x - c.x) / (2 * r) + 0.5),
                             cv0 + (cv1 - cv0) * ((l.vert.co.y - c.y) / (2 * r) + 0.5))

def basket():
    begin()
    prof = [(0, 0.0), (0.19, 0.0), (0.2, 0.012), (0.255, 0.3), (0.268, 0.31), (0.268, 0.326), (0.25, 0.326),
            (0.244, 0.31), (0.186, 0.022), (0, 0.022)]
    fs = new_faces(lathe, prof, segs=28)
    k = TILE / WICKER_TILE
    for f in fs:
        for l in f.loops: l[uvl].uv = (l[uvl].uv[0] * k, l[uvl].uv[1] * k)
    rim = [Vector((math.cos(a) * 0.262, math.sin(a) * 0.262, 0.326)) for a in (2 * math.pi * i / 28 for i in range(28))]
    new_faces(tube, rim, 0.012, sides=6, closed=True)
    for s in (-1, 1):                                                   # two handles
        bent([(s * 0.262, -0.07, 0.3), (s * 0.29, -0.06, 0.365), (s * 0.29, 0.06, 0.365), (s * 0.262, 0.07, 0.3)],
             0.009, bend=0.03, sides=6)
    heap(Vector((0.0, 0.0, 0.25)), 0.23, 0.12, 3, 1)
    heap(Vector((0.05, -0.04, 0.29)), 0.15, 0.09, 2, 2)
    clean()
    return finish("LaundryBasket", material=["Wicker", "LaundryCloth"])

def wash_tub():
    begin()
    prof = [(0, 0.012), (0.225, 0.012), (0.234, 0.0), (0.242, 0.012), (0.25, 0.06), (0.255, 0.065), (0.252, 0.072),
            (0.262, 0.17), (0.267, 0.175), (0.264, 0.182), (0.276, 0.26), (0.286, 0.266), (0.286, 0.277),
            (0.271, 0.274), (0.259, 0.18), (0.236, 0.024), (0, 0.024)]
    fs = new_faces(lathe, prof, segs=32)
    paint(fs, 0)
    for s in (-1, 1):
        paint(bent([(s * 0.28, -0.06, 0.24), (s * 0.33, -0.05, 0.25), (s * 0.33, 0.05, 0.25), (s * 0.28, 0.06, 0.24)],
                   0.007, bend=0.025, sides=6), 0)
    # a towel over the rim (front, -Y): in at the water side, over the lip, down the outside
    cu0, cv0, cu1, cv1 = CELL_UV(1)
    path = [(0.21, 0.2), (0.25, 0.27), (0.285, 0.295), (0.31, 0.27), (0.315, 0.18), (0.305, 0.08)]
    n, a0, a1 = 8, -math.pi / 2 - 0.35, -math.pi / 2 + 0.35
    grid = []
    for j, (r, z) in enumerate(path):
        row = []
        for i in range(n + 1):
            a = a0 + (a1 - a0) * i / n
            rr = r + 0.008 * math.sin(i * 1.7 + j)
            row.append((bm.verts.new((math.cos(a) * rr, math.sin(a) * rr, z)), i / n, j / (len(path) - 1)))
        grid.append(row)
    for r0, r1 in zip(grid, grid[1:]):
        for i in range(n):
            q = (r0[i], r0[i + 1], r1[i + 1], r1[i])
            f = bm.faces.new([c[0] for c in q]); f.material_index = 1; f.smooth = True
            for l, c in zip(f.loops, q): l[uvl].uv = (cu0 + (cu1 - cu0) * c[1], cv1 - (cv1 - cv0) * c[2] * 0.6)
    clean()
    return finish("WashTub", material=["GalvSteel", "LaundryCloth"])

make_laundry_textures()
PIECES = [clothesline("ClotheslineLaundry", True), clothesline("ClotheslineEmpty", False), basket(), wash_tub()]
for ob in PIECES:
    print(ob.name, "tris", sum(len(p.vertices) - 2 for p in ob.data.polygons))

path = os.path.join(OUT_DIR, "clothesline.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    bpy.data.objects["ClotheslineEmpty"].location = (0, 4.0, 0)
    bpy.data.objects["LaundryBasket"].location = (-1.3, -1.1, 0)
    bpy.data.objects["WashTub"].location = (1.3, -0.9, 0)
    g = bpy.data.meshes.new("G"); g.from_pydata([(-8, -6, 0), (8, -6, 0), (8, 8, 0), (-8, 8, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.13, 0.14, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.2; sun.data.angle = math.radians(5)
    sun.rotation_euler = (math.radians(48), 0, math.radians(-35)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1000
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    for fname, at, look, lens in (("clothesline.png", (-2.6, -6.2, 2.4), (0.2, 0.0, 1.1), 30),
                                  ("clothesline_close.png", (1.0, -2.6, 1.5), (0.6, 0.0, 1.3), 35)):
        cam.location, tgt.location, cam.data.lens = at, look, lens
        sc.render.filepath = os.path.join(HERE, "render", fname)
        bpy.ops.render.render(write_still=True)
print("CLOTHESLINE DONE")
