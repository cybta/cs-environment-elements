"""Old yard furniture (ref: the user's sheet: slatted table on cinder blocks, plank bench,
round stool). One object per piece, origin on the floor at the centre of its footprint,
front to -Y:

  YardTableOld   pallet-slat top on two bearers, on the user's square-tube metal frame
                 (sources/table-slat-metal-feet.blend), 1.0 x 0.6 x 0.47 m
  YardBenchOld   three seat planks and three back planks, tall back posts, front legs,
                 rusty nail heads, 1.5 m long, seat 0.45 m, back 0.95 m
  YardStoolOld   round seat of three planks, four splayed legs, stretchers, 0.5 m high

Materials (shared with the rest of the add-on):
  C_fence_old_wood   the fence planks: every board, leg and post takes one plank strip
  DarkSteel          the playground's dark paint peeled to rust (frame, nails)

Saves cs_environment_elements/props/assets/garden/yard_furniture.blend and, unless
RENDER=0, render/yard_furniture.png beside this script.
Headless:  blender -b --factory-startup --python build_yard_furniture.py
"""
import os, math, random, importlib.util
import bpy, bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
PKG = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements"))
OUT_DIR = os.path.join(PKG, "props", "assets", "garden")
TEXG = os.path.join(OUT_DIR, "textures")

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
TEX_DIR = os.path.join(PKG, "props", "assets", "playground", "textures")
_spec = importlib.util.spec_from_file_location("fence_geom", os.path.join(PKG, "buildings", "fence_geom.py"))
fg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fg)
rng = random.Random(23)
WOOD = fg.MAT_WOOD
WOOD_I, STEEL_I = 0, 1

_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    if name == WOOD:
        return fg.wood_material()
    return _pg_ensure(name)

# ---------------------------------------------------------------- plank-textured parts

exec(open(os.path.join(HERE, "plank_lib.py")).read())          # strip(), plank(), round_leg()

def nail(at, normal):
    """Rusty nail head on a face pointing along `normal`."""
    fs = new_faces(lathe, [(0, 0), (0.007, 0), (0.0065, 0.003), (0, 0.004)], segs=6)
    m = Vector((0, 0, 1)).rotation_difference(Vector(normal)).to_matrix()
    for v in {v for f in fs for v in f.verts}: v.co = m @ v.co + Vector(at)
    return paint(fs, STEEL_I)

def bar(lo, hi):
    """Square steel tube (rusty)."""
    fs = box(lo, hi, bevel=0.002, segs=1)
    uv_box(fs, TILE)
    return paint(fs, STEEL_I)

def clean():
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")

# ---------------------------------------------------------------- pieces

BASE_FILE = os.path.join(HERE, "sources", "table-slat-metal-feet.blend")   # the user's metal frame

def frame_base():
    """The user's metal frame (object 'Cube' in BASE_FILE: 3 cm square tube, 0.6 x 1.0 x 0.4 m,
    long side along Y, hanging below its origin), turned to run along X and stood on the
    floor, centred. Rusty steel, box-mapped. Returns its (length, depth, height)."""
    with bpy.data.libraries.load(BASE_FILE, link=False) as (src, dst):
        dst.meshes = [src.meshes[src.objects.index("Cube")] if "Cube" in src.objects else src.meshes[0]]
    me = dst.meshes[0]
    xs = [v.co.x for v in me.vertices]; ys = [v.co.y for v in me.vertices]; zs = [v.co.z for v in me.vertices]
    c = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, min(zs)))
    m = Matrix.Rotation(math.pi / 2, 4, "Z") @ Matrix.Translation(-c)
    me.transform(m)
    before = set(bm.faces)
    bm.from_mesh(me)
    fs = set(bm.faces) - before
    bpy.data.meshes.remove(me)
    uv_box(fs, TILE)
    paint(fs, STEEL_I)
    for f in fs:
        f.smooth = False
    return max(ys) - min(ys), max(xs) - min(xs), max(zs) - min(zs)

def table():
    begin()
    L, W, zf = frame_base()                              # bearers sit on the frame's top rails
    # two bearers along X, slats across them
    for sy in (-1, 1):
        plank((-L / 2 + 0.03, sy * (W / 2 - 0.07) - 0.035, zf), (L / 2 - 0.03, sy * (W / 2 - 0.07) + 0.035, zf + 0.045), 0)
    n, gap = 7, 0.022
    sw = (L - (n - 1) * gap) / n
    for i in range(n):
        x0 = -L / 2 + i * (sw + gap) + rng.uniform(-0.005, 0.005)
        dz = rng.uniform(-0.003, 0.003)
        plank((x0, -W / 2 - 0.02 + rng.uniform(-0.01, 0.01), zf + 0.045 + dz),
              (x0 + sw, W / 2 + 0.02 + rng.uniform(-0.01, 0.01), zf + 0.07 + dz), 1)
        for sy in (-1, 1):
            nail((x0 + sw / 2, sy * (W / 2 - 0.07), zf + 0.07 + dz + 0.001), (0, 0, 1))
    clean()
    return finish("YardTableOld", material=[WOOD, "DarkSteel"])

def bench():
    begin()
    L, D, SEAT = 1.5, 0.42, 0.45
    post = 0.075
    yb = D / 2 - post / 2                                       # back posts (also the back legs)
    for sx in (-1, 1):
        x = sx * (L / 2 - 0.12)
        plank((x - post / 2, yb - post / 2, 0), (x + post / 2, yb + post / 2, 0.98), 2, bevel=0.006)
        plank((x - post / 2, -D / 2 + 0.03, 0), (x + post / 2, -D / 2 + 0.03 + post, SEAT - 0.07), 2, bevel=0.006)
        plank((x - 0.025, -D / 2 + 0.01, SEAT - 0.115), (x + 0.025, D / 2 - 0.02, SEAT - 0.045), 1)       # seat bearer
        plank((x - 0.02, -D / 2 + 0.05, 0.12), (x + 0.02, yb - post / 2, 0.18), 1)                       # low rail
    for i in range(3):                                          # seat planks, front to back
        y0 = -D / 2 - 0.01 + i * 0.145
        dz = rng.uniform(-0.004, 0.004)
        plank((-L / 2 + rng.uniform(0, 0.02), y0, SEAT - 0.045 + dz), (L / 2 - rng.uniform(0, 0.02), y0 + 0.13, SEAT + dz), 0)
        for sx in (-1, 1):
            nail((sx * (L / 2 - 0.12), y0 + 0.065, SEAT + dz + 0.001), (0, 0, 1))
    for i in range(3):                                          # back planks, bottom to top
        z0 = SEAT + 0.14 + i * 0.13
        plank((-L / 2 + 0.06 + rng.uniform(0, 0.02), yb - post / 2 - 0.03, z0),
              (L / 2 - 0.06 - rng.uniform(0, 0.02), yb - post / 2, z0 + 0.115), 0)
        for sx in (-1, 1):
            nail((sx * (L / 2 - 0.12), yb - post / 2 - 0.031, z0 + 0.058), (0, -1, 0))
    clean()
    return finish("YardBenchOld", material=[WOOD, "DarkSteel"])

def stool():
    begin()
    R, H, th = 0.17, 0.5, 0.035
    seat = new_faces(lathe, [(0, H - th), (R - 0.006, H - th), (R, H - th + 0.006), (R, H - 0.006),
                             (R - 0.008, H), (0, H)], segs=24)
    # three boards: each band of the seat (across Y) takes its own plank strip
    bands = [strip() for _ in range(3)]
    for f in seat:
        f.material_index = WOOD_I
        cy = sum(v.co.y for v in f.verts) / len(f.verts)
        k = min(2, max(0, int((cy + R) / (2 * R / 3))))
        u0, u1, v0, v1 = bands[k]
        blo = -R + k * 2 * R / 3
        for l in f.loops:
            p = l.vert.co
            l[uvl].uv = (u0 + 0.1 + (p.x + R) * 0.12, v0 + (v1 - v0) * min(1, max(0, (p.y - blo) / (2 * R / 3))))
    feet = []
    for k in range(4):
        a = math.pi / 4 + k * math.pi / 2
        top = Vector((math.cos(a) * 0.1, math.sin(a) * 0.1, H - th))
        foot = Vector((math.cos(a) * 0.19, math.sin(a) * 0.19, 0.0))
        round_leg(foot, top, 0.019, 0.016, sides=7)
        feet.append((foot, top))
    for k in range(4):                                         # stretchers at two heights
        (f0, t0), (f1, t1) = feet[k], feet[(k + 1) % 4]
        h = 0.17 if k % 2 else 0.22
        p0 = f0.lerp(t0, h / (H - th)); p1 = f1.lerp(t1, h / (H - th))
        round_leg(p0, p1, 0.011, 0.011, sides=6)
    clean()
    return finish("YardStoolOld", material=[WOOD])

PIECES = [table(), bench(), stool()]
for ob in PIECES:
    me = ob.data
    print(ob.name, "tris", sum(len(p.vertices) - 2 for p in me.polygons))

path = os.path.join(OUT_DIR, "yard_furniture.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    for ob, (x, y, rz) in zip(PIECES, ((-0.2, -0.3, -10), (0.7, 0.9, -15), (1.1, -0.6, 0))):
        ob.location = (x, y, 0); ob.rotation_euler.z = math.radians(rz)
    g = bpy.data.meshes.new("G"); g.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.13, 0.14, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.2; sun.data.angle = math.radians(6)
    sun.rotation_euler = (math.radians(45), 0, math.radians(-30)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    cam.location, tgt.location, cam.data.lens = (-1.4, -3.4, 1.9), (0.5, 0.2, 0.35), 35
    sc.render.filepath = os.path.join(HERE, "render", "yard_furniture.png")
    bpy.ops.render.render(write_still=True)
print("YARD DONE")
