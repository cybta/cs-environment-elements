"""Old wooden electric poles (ref: Desktop/ref/old-poll.png), five variants like the ref sheet:

  ElectricPoleOld3Arm        3 crossarms (6, 6, 4 insulators)
  ElectricPoleOld2ArmDouble  2 double crossarms (a bar each side of the pole, 4 + 4 insulators)
  ElectricPoleOld2Arm        2 crossarms (4 insulators each)
  ElectricPoleOld1Arm        1 crossarm (4 insulators)
  ElectricPoleOldLampKit     optional add-on for any of them: 2 hook insulators on the side
                             and a street lamp (the add-on parents it to the pole)

Each: tapered creosoted wooden pole with a steel band, rusty angle-steel crossarms bolted
to the front (or both sides) with V braces down to the pole, white porcelain pin insulators.
Slots: 0 PoleWood, 1 DarkSteel, 2 Porcelain, 3 BulbGlow (lamp only).

Origins: foot of the pole, on the floor. Crossarms run along X, front faces -Y.
Every variant sits at the origin (the add-on places them by their own origin).

Saves cs_environment_elements/props/assets/poles/electric_pole_old.blend and, unless
RENDER=0, render/electric_pole_old.png beside this script.
Run make_pole_textures.py first. Headless:  blender -b --python build_electric_pole.py
"""
import os, math, bpy, bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
ASSETS = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements", "props", "assets"))
OUT_DIR = os.path.join(ASSETS, "poles")

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
TEX_DIR = os.path.join(ASSETS, "playground", "textures")       # DarkSteel maps (shared)
POLE_TEX = os.path.join(OUT_DIR, "textures")
SIMPLE_MATERIALS.update({"Porcelain": ((0.86, 0.85, 0.80), 0.16, 0.0, None, 0)})

WOOD, STEEL, PORC, BULB = 0, 1, 2, 3
MATS = ["PoleWood", "DarkSteel", "Porcelain"]
R0, R1 = 0.13, 0.10              # pole radius at the foot / top
WOOD_V = 2.0                     # metres of pole per texture repeat (one repeat wraps round once)

_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    global TEX_DIR
    if name != "PoleWood" or bpy.data.materials.get(name):
        return _pg_ensure(name)
    keep, TEX_DIR = TEX_DIR, POLE_TEX
    try:
        return _textured("PoleWood", {"Base Color": "pole_wood_diff_1k.png", "Roughness": "pole_wood_rough_1k.png",
                                      "Normal": "pole_wood_nor_gl_1k.png"}, 0.8)
    finally:
        TEX_DIR = keep

# ---------------------------------------------------------------- helpers

def move(faces, by):
    by = Vector(by)
    for v in {v for f in faces for v in f.verts}: v.co += by
    return faces

def rad_at(z, h):
    return R0 + (R1 - R0)*min(max(z/h, 0), 1)

def pole(h, segs=16):
    """Tapered pole, sawn flat on top (a small chamfer round the edge). U wraps once round,
    V = height / WOOD_V (grain up the pole). The seam has doubled verts (welded by finish(),
    the UVs stay split)."""
    before = set(bm.faces)
    prof = [(rad_at(z, h), z) for z in (0, h*0.25, h*0.5, h*0.75, h - 0.012)]
    prof += [(R1 - 0.01, h)]
    rings = [[bm.verts.new((r*math.cos(2*math.pi*k/segs), r*math.sin(2*math.pi*k/segs), z))
              for k in range(segs + 1)] for r, z in prof]
    for (ra, za), (rb, zb), a, b in zip(prof, prof[1:], rings, rings[1:]):
        for k in range(segs):
            f = bm.faces.new((a[k], a[k + 1], b[k + 1], b[k])); f.smooth = True
            for l, (u, v) in zip(f.loops, ((k, za), (k + 1, za), (k + 1, zb), (k, zb))):
                l[uvl].uv = (u/segs, v/WOOD_V)
    for ring, z, top in ((rings[0], 0.0, False), (rings[-1], h, True)):
        c = bm.verts.new((0, 0, z))
        for k in range(segs):
            f = bm.faces.new((ring[k], ring[k + 1], c) if top else (ring[k + 1], ring[k], c))
            f.smooth = False
            for l in f.loops: l[uvl].uv = (0.5 + l.vert.co.x, 0.5 + l.vert.co.y)
    return paint(set(bm.faces) - before, WOOD)

def band(z, h, w=0.05):
    r = rad_at(z, h)
    prof = [(r - 0.004, z), (r + 0.007, z), (r + 0.007, z + w), (r - 0.004, z + w), (r - 0.004, z)]
    return paint(new_faces(lathe, prof, segs=16), STEEL)

def beam(a, b, side, w, t):
    """Flat bar from a to b, `w` wide along `side`, `t` thick. Returns faces."""
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized(); s = Vector(side).normalized()
    n = d.cross(s).normalized(); s = n.cross(d).normalized()
    c = [p + s*sx*w/2 + n*nx*t/2 for p in (a, b) for sx, nx in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    vs = [bm.verts.new(p) for p in c]
    quads = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    fs = {bm.faces.new([vs[i] for i in q]) for q in quads}
    uv_box(fs, TILE); return fs

def bolt(at, side):
    """Hex bolt head on a face pointing towards `side` (-1 = -Y, +1 = +Y)."""
    fs = new_faces(lathe, [(0, 0), (0.013, 0), (0.013, 0.009), (0, 0.009)], segs=6)
    for v in {v for f in fs for v in f.verts}:
        x, y, z = v.co
        v.co = Vector((x, side*z, y)) + Vector(at)
    return paint(fs, STEEL)

INSULATOR = [(0.0, 0.0), (0.036, 0.0), (0.040, 0.01), (0.031, 0.026), (0.034, 0.042),
             (0.027, 0.056), (0.019, 0.060), (0.018, 0.070), (0.025, 0.080), (0.021, 0.093), (0.0, 0.097)]

def insulator(at, pin=0.025):
    """Porcelain pin insulator standing on a short steel pin at `at` (bottom of the pin)."""
    at = Vector(at)
    paint(move(new_faces(lathe, [(0, 0), (0.008, 0), (0.008, pin + 0.01), (0, pin + 0.01)], segs=6), at), STEEL)
    paint(move(new_faces(lathe, INSULATOR, segs=8), at + Vector((0, 0, pin))), PORC)

def crossarm(z, h, xs, sides=(-1,), length=1.5):
    """Angle-steel crossarm(s) whose top is at z: a vertical flange against the pole and a
    top flange reaching out; insulators at x positions `xs`; V braces down to the pole."""
    r = rad_at(z, h)
    for sd in sides:
        y0 = sd*(r - 0.01)
        lo, hi = sorted((y0, y0 + sd*0.006))
        paint(box((-length/2, lo, z - 0.065), (length/2, hi, z)), STEEL)              # vertical flange
        lo, hi = sorted((y0, y0 + sd*0.065))
        paint(box((-length/2, lo, z - 0.006), (length/2, hi, z)), STEEL)             # top flange
        for x in xs:
            insulator((x, y0 + sd*0.036, z))
        foot = z - 0.62
        yf = sd*(rad_at(foot, h) + 0.003)
        for sx in (-1, 1):
            paint(beam((sx*0.5, y0 + sd*0.009, z - 0.05), (sx*0.02, yf, foot), (0, 1, 0), 0.032, 0.006), STEEL)
        bolt((0, y0 + sd*0.006, z - 0.035), sd)
        bolt((0, yf + sd*0.003, foot), sd)

XS4 = (-0.62, -0.3, 0.3, 0.62)
XS6 = (-0.66, -0.42, -0.18, 0.18, 0.42, 0.66)

def hook(z, h, out=0.13, up=0.07):
    """J-hook (screwed into the side of the pole, -X) carrying an insulator."""
    r = rad_at(z, h)
    paint(bent([(-(r - 0.03), 0, z), (-(r + out), 0, z), (-(r + out), 0, z + up)], 0.009, bend=0.03), STEEL)
    paint(move(new_faces(lathe, INSULATOR, segs=8), (-(r + out), 0, z + up)), PORC)

def street_lamp(z, h, reach=0.95, drop=0.14):
    """Pipe arm from a band at z out to -X, bending down into a dark enamel shade with a bulb."""
    r = rad_at(z, h)
    band(z - 0.03, h, 0.07)
    paint(bent([(-(r - 0.02), 0, z), (-(reach - 0.1), 0, z), (-reach, 0, z - drop)], 0.017, bend=0.08), STEEL)
    top = Vector((-reach, 0, z - drop - 0.005))
    shade = [(0, 0.03), (0.032, 0.03), (0.04, 0.0), (0.07, -0.035), (0.25, -0.15), (0.256, -0.165),
             (0.247, -0.165), (0.062, -0.043), (0.0, -0.043)]
    paint(move(new_faces(lathe, shade, segs=10), top), STEEL)
    bulb = [(0, -0.035), (0.016, -0.045), (0.04, -0.085), (0.042, -0.11), (0.03, -0.14), (0, -0.15)]
    paint(move(new_faces(lathe, bulb, segs=10), top), BULB)

# ---------------------------------------------------------------- variants

def _finish(name, mats):
    # bentwood_lib.lathe() leaves a stray loose vertex per r=0 profile point (setdefault
    # builds its default every call); drop them so bounds and exports stay clean
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    return finish(name, material=mats)

def build(name, h, arms, band_z=3.0):
    begin()
    pole(h)
    band(band_z, h)
    for dz, xs, sides in arms:
        crossarm(h - dz, h, xs, sides)
    return _finish(name, MATS)

# Optional street lamp (the add-on parents it to any pole): 2 hook insulators and the lamp,
# at fixed heights clear of the lowest crossarm braces of every variant (about 6 m).
# The pole radius there barely changes between the variants, so one kit fits them all.
KIT_H = 8.3
def lamp_kit(name):
    begin()
    hook(5.72, KIT_H)
    hook(5.27, KIT_H)
    street_lamp(4.65, KIT_H)
    return _finish(name, MATS + ["BulbGlow"])

BOTH = (-1, 1)
VARIANTS = [
    ("ElectricPoleOld3Arm", 8.0, [(0.2, XS6, (-1,)), (0.8, XS6, (-1,)), (1.4, XS4, (-1,))]),
    ("ElectricPoleOld2ArmDouble", 8.0, [(0.2, XS4, BOTH), (0.85, XS4, BOTH)]),
    ("ElectricPoleOld2Arm", 8.2, [(0.2, XS4, (-1,)), (0.85, XS4, (-1,))]),
    ("ElectricPoleOld1Arm", 8.4, [(0.2, XS4, (-1,))]),
]
for name, h, arms in VARIANTS:
    build(name, h, arms)
lamp_kit("ElectricPoleOldLampKit")

os.makedirs(OUT_DIR, exist_ok=True)
path = os.path.join(OUT_DIR, "electric_pole_old.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

# ---------------------------------------------------------------- preview render (not saved in the asset)
if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    row = [bpy.data.objects[v[0]] for v in VARIANTS]
    row.append(row[0].copy())                                  # 5th: the 3-arm pole with the lamp kit
    sc.collection.objects.link(row[-1])
    for i, ob in enumerate(row):
        ob.location.x = (i - 2)*2.4
    bpy.data.objects["ElectricPoleOldLampKit"].location.x = 2*2.4
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.5; sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
    sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (0.25, 0.27, 0.3, 1); bg.inputs["Strength"].default_value = 1.0
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    shots = [("electric_pole_old.png", (3.0, -16.0, 4.5), (0, 0, 4.4), 28, (1200, 1000)),
             ("electric_pole_old_top.png", (-1.4, -2.6, 8.2), (-2.4, 0, 7.6), 40, (1000, 1000)),
             ("electric_pole_old_lamp.png", (6.6, -5.0, 5.6), (4.5, 0, 5.8), 30, (1000, 1000))]
    for fname, at, look, lens, (rx, ry) in shots:
        cam.location = at; tgt.location = look; cam.data.lens = lens
        sc.render.resolution_x, sc.render.resolution_y = rx, ry
        sc.render.filepath = os.path.join(HERE, "render", fname)
        bpy.ops.render.render(write_still=True)
print("POLES DONE")
