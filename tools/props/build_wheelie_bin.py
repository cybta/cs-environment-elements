"""240 L wheelie bin, green and black (ref: the user's bin sheet, green + dark grey).

  WheelieBinGreen / WheelieBinBlack            body: tapered tub with rounded corners, a rim
                                               with ribs under it, the rear handle bar the lid
                                               hinges on, two spoked wheels on an axle housing,
                                               a foot step at the back
  WheelieBinGreenLid / WheelieBinBlackLid      child: the lid (raised panel, two front handle
                                               tabs); its origin is on the hinge axis, so
                                               rotating it about local X (negative = open,
                                               up to about -110 degrees) swings it open

About 0.58 x 0.73 x 1.07 m. Origin: floor, centre of the body. Front faces -Y, the
wheels and handle are at the back (+Y).
Slots: 0 BinPlastic<Colour> (worn plastic: scratches, grime heavier towards the bottom),
1 BinRubber (tyres), 2 BinHub (dark plastic wheel centres), 3 BinAxle (steel).
The plastic is UV-mapped with V = height (0 at the floor, 1 at 1.1 m) and U round the
walls in metres, so the grime in the texture sits at the foot of the bin.

Writes cs_environment_elements/props/assets/bins/wheelie_bin.blend and textures/, and
unless RENDER=0, render/wheelie_bin.png beside this script.
Headless:  blender -b --factory-startup --python build_wheelie_bin.py
"""
import os, math
import numpy as np
import bpy, bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements", "props", "assets", "bins"))
TEXDIR = os.path.join(OUT_DIR, "textures")

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
TEX_DIR = TEXDIR
os.makedirs(TEXDIR, exist_ok=True)

COLOURS = {"Green": (0.20, 0.34, 0.20), "Black": (0.085, 0.088, 0.093)}       # sRGB
SCRATCH = {"Green": (0.42, 0.52, 0.40), "Black": (0.30, 0.30, 0.31)}
V_SPAN = 1.1                       # metres of height per texture (V 0..1)
PLASTIC, RUBBER, HUB, AXLE = 0, 1, 2, 3

# ================================================================ textures
N = 1024

def fbm(seed, beta=2.0, stretch=1.0, lo=2.0):
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(N) * N
    fx, fy = np.meshgrid(f / stretch, f)
    r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
    amp = 1 / np.maximum(r, lo) ** (beta / 2); amp[0, 0] = 0
    n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * amp))
    return (n - n.min()) / (n.max() - n.min())

def blur(a, sigma):
    fy, fx = np.fft.fftfreq(N)[:, None], np.fft.fftfreq(N)[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (math.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))))

def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)

def lerp(a, b, t): return a + (b - a) * t[..., None]
def col(c): return np.array(c, dtype=np.float32)[None, None, :]

def normal_from(h, s):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * s
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * s
    n = np.dstack((-dx, -dy, np.ones_like(h))); n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5

def save(name, arr):
    arr = np.clip(arr, 0, 1)
    if arr.ndim == 2: arr = np.dstack([arr] * 3)
    img = bpy.data.images.new(name, N, N, alpha=False)
    img.pixels.foreach_set(np.dstack((arr, np.ones((N, N)))).astype(np.float32).ravel())
    img.filepath_raw = os.path.join(TEXDIR, name); img.file_format = "PNG"; img.save()
    bpy.data.images.remove(img); print("saved", name)

def scratches(seed, count):
    """Thin random scuffs, mostly near horizontal (bins get dragged and knocked)."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((N, N), np.float32)
    for _ in range(count):
        x0, y0 = rng.uniform(0, N, 2)
        ang = rng.normal(0, 0.5) if rng.random() < 0.7 else rng.uniform(0, math.pi)
        ln = rng.uniform(4, 45) * (1.8 if rng.random() < 0.08 else 1)
        t = np.arange(0, ln, 0.5)
        xs = (x0 + np.cos(ang) * t).astype(int) % N
        ys = (y0 + np.sin(ang) * t).astype(int) % N
        acc[ys, xs] += rng.uniform(0.25, 0.8)
    return np.clip(blur(acc, 0.7) * 2.2, 0, 1)

def plastic_maps():
    v = (np.arange(N) / N)[:, None] * np.ones((1, N))          # row 0 = V 0 = the floor
    mottle, dirtn = fbm(31, 2.4), fbm(32, 1.8)
    drip = fbm(33, 2.0, stretch=6.0)                            # stretched along V: streaks down
    sc = scratches(34, 380)
    grime = smooth(0.33, 0.02, v) * (0.45 + 0.55 * dirtn)                       # splashed-up dirt
    grime = np.maximum(grime, smooth(0.62, 0.8, drip) * smooth(0.75, 0.15, v) * 0.45)   # rain streaks
    dust = smooth(0.55, 0.85, fbm(35, 1.0)) * 0.25
    for name, c in COLOURS.items():
        base = col(c) * (0.9 + 0.18 * mottle)[..., None]
        d = lerp(base, col(SCRATCH[name]), sc * 0.35)
        d = lerp(d, col((0.23, 0.19, 0.14)), grime * 0.85)
        d = lerp(d, col((0.45, 0.42, 0.37)), dust * (1 - grime))
        save(f"bin_plastic_{name.lower()}_diff_1k.png", d)
    save("bin_plastic_rough_1k.png", 0.5 + 0.12 * mottle + 0.12 * sc + 0.3 * grime)
    save("bin_plastic_nor_gl_1k.png", normal_from(mottle * 0.3 - sc * 0.25 + grime * 0.15, 3.0))

SIMPLE_MATERIALS.update({
    "BinRubber": ((0.025, 0.025, 0.025), 0.85, 0.0, None, 0),
    "BinHub": ((0.035, 0.036, 0.038), 0.55, 0.0, None, 0),
    "BinAxle": ((0.45, 0.45, 0.45), 0.4, 1.0, None, 0),
})
_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    if name.startswith("BinPlastic") and not bpy.data.materials.get(name):
        return _textured(name, {"Base Color": f"bin_plastic_{name[10:].lower()}_diff_1k.png",
                                "Roughness": "bin_plastic_rough_1k.png", "Normal": "bin_plastic_nor_gl_1k.png"}, 0.5)
    return _pg_ensure(name)

# ================================================================ geometry
TOP_Z, RIM_Z = 0.90, 0.915        # body top, rim top (the lid sits on it)
def hx(z): return 0.225 + 0.045 * z / TOP_Z     # half width, tapering to the floor
def hy(z): return 0.245 + 0.055 * z / TOP_Z     # half depth
HY_T, HX_T = hy(TOP_Z), hx(TOP_Z)
BAR = Vector((0, HY_T + 0.065, 0.94))           # handle bar / lid hinge axis (along X)

def setmat(faces, slot):
    for f in faces: f.material_index = slot
    return faces

def plastic_uv(faces):
    """V = height / V_SPAN; U round the walls in metres; tops use a clean strip near V=0.95."""
    for f in faces:
        f.normal_update(); n = f.normal
        for l in f.loops:
            p = l.vert.co
            if abs(n.z) > 0.7:
                l[uvl].uv = (p.x + 0.5, 0.93 + p.y * 0.05)
            elif abs(n.x) > abs(n.y):
                l[uvl].uv = (p.y + (0.0 if n.x > 0 else 0.37), p.z / V_SPAN)
            else:
                l[uvl].uv = (p.x + (0.61 if n.y > 0 else 0.15), p.z / V_SPAN)
    return faces

def rr(hx_, hy_, r, n=4, cy=0.0):
    """Rounded rectangle, counter-clockwise."""
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx, cyy = sx * (hx_ - r), sy * (hy_ - r) + cy
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cyy + r * math.sin(a)))
    return pts

def loft(rings, cap_bottom=True, cap_top=True):
    vr = [[bm.verts.new((x, y, z)) for x, y in pts] for pts, z in rings]
    m = len(vr[0]); faces = []
    for a, b in zip(vr, vr[1:]):
        for k in range(m):
            faces.append(bm.faces.new((a[k], a[(k + 1) % m], b[(k + 1) % m], b[k])))
    if cap_bottom: faces.append(bm.faces.new(list(reversed(vr[0]))))
    if cap_top: faces.append(bm.faces.new(vr[-1]))
    for f in faces: f.smooth = True
    return set(faces)

def ring(z, grow=0.0, r=0.055):
    return rr(hx(z) + grow, hy(z) + grow, r + grow), z

def gusset(w0, w1, o1, t):
    """Triangular rib under the rim: wall bottom w0, wall top w1, outer top o1, thickness along t."""
    tv = Vector(t) * 0.006
    a = [bm.verts.new(p - tv) for p in (w0, w1, o1)]
    b = [bm.verts.new(p + tv) for p in (w0, w1, o1)]
    fs = [bm.faces.new(a), bm.faces.new(list(reversed(b)))]
    for i in range(3):
        j = (i + 1) % 3
        fs.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    return set(fs)

def wheel(cx):
    """Spoked wheel centred at (cx, axle), spokes facing out."""
    out = 1 if cx > 0 else -1
    fs = set()
    tyre = [(0.07, -0.0225), (0.091, -0.0225), (0.1, -0.013), (0.1, 0.013), (0.091, 0.0225), (0.07, 0.0225),
            (0.07, -0.0225)]
    fs |= setmat(new_faces(lathe, tyre, segs=20), RUBBER)
    rim_ = [(0.058, -0.019), (0.071, -0.019), (0.071, 0.019), (0.058, 0.019), (0.058, -0.019)]
    fs |= setmat(new_faces(lathe, rim_, segs=20), HUB)
    fs |= setmat(new_faces(lathe, [(0, -0.008), (0.06, -0.008), (0.06, 0.006), (0, 0.006)], segs=20), HUB)
    fs |= setmat(new_faces(lathe, [(0, 0.0), (0.022, 0.0), (0.02, 0.022), (0, 0.024)], segs=12), HUB)
    for k in range(6):
        sp = box((0.018, -0.006, -0.004), (0.062, 0.006, 0.016))
        m = Matrix.Rotation(k * math.pi / 3, 3, "Z")
        for v in {v for f in sp for v in f.verts}: v.co = m @ v.co
        fs |= setmat(sp, HUB)
    rot = Matrix.Rotation(math.pi / 2, 3, "Y")                   # lathe axis Z -> X (spokes to +X)
    centre = Vector((cx, AXLE_Y, AXLE_Z))
    for v in {v for f in fs for v in f.verts}:
        p = rot @ v.co
        v.co = Vector((p.x * out, p.y, p.z)) + centre
    return fs

AXLE_Y, AXLE_Z, WHEEL_X = 0.2, 0.1, 0.268

def body():
    begin()
    plastic = set()
    # one hollow shell: outside up, out over the rim, back in and down the inside to the floor
    plastic |= loft([(rr(hx(0) - 0.016, hy(0) - 0.016, 0.04), 0.0), ring(0.02), ring(0.6), ring(0.853),
                     ring(0.858, 0.012), ring(0.868, 0.022), ring(RIM_Z, 0.022), ring(RIM_Z + 0.004, 0.012),
                     ring(RIM_Z + 0.004, -0.008), ring(0.6, -0.008), ring(0.05, -0.008)])
    zt, zb = 0.853, 0.765
    for x in (-0.13, 0.13):                                      # ribs under the rim, front and sides
        plastic |= gusset(Vector((x, -hy(zb), zb)), Vector((x, -hy(zt), zt)), Vector((x, -hy(zt) - 0.022, zt)), (1, 0, 0))
    for s in (-1, 1):
        for y in (-0.13, 0.1):
            plastic |= gusset(Vector((s * hx(zb), y, zb)), Vector((s * hx(zt), y, zt)),
                              Vector((s * (hx(zt) + 0.022), y, zt)), (0, 1, 0))
    # rear handle bar, its end brackets and the spokes joining it to the rim
    plastic |= bent([(-0.235, BAR.y, BAR.z), (0.235, BAR.y, BAR.z)], 0.017, sides=10)
    for s in (-1, 1):
        plastic |= box((s * 0.245 - 0.013, HY_T + 0.01, 0.89), (s * 0.245 + 0.013, BAR.y + 0.022, 0.958), bevel=0.004)
    for x in (-0.15, -0.05, 0.05, 0.15):
        plastic |= box((x - 0.008, HY_T + 0.015, 0.922), (x + 0.008, BAR.y, 0.95), bevel=0.003)
    # axle housing between the wheels, foot step under it
    plastic |= box((-0.236, 0.15, 0.045), (0.236, 0.262, 0.155), bevel=0.012)
    plastic |= box((-0.09, 0.235, 0.012), (0.09, 0.325, 0.036), bevel=0.004)
    for y in (0.258, 0.282, 0.306):
        plastic |= box((-0.08, y - 0.004, 0.035), (0.08, y + 0.004, 0.041))
    setmat(plastic_uv(plastic), PLASTIC)
    setmat(new_faces(tube, [Vector((-0.29, AXLE_Y, AXLE_Z)), Vector((0.29, AXLE_Y, AXLE_Z))], 0.011, sides=8), AXLE)
    wheel(-WHEEL_X); wheel(WHEEL_X)

def lid():
    begin()
    plastic = set()
    e = 0.03
    plastic |= loft([(rr(HX_T + e, HY_T + e, 0.06 + e), 0.895), (rr(HX_T + e, HY_T + e, 0.06 + e), 0.945),
                     (rr(HX_T + e - 0.01, HY_T + e - 0.01, 0.05 + e), 0.953)])
    plastic |= loft([(rr(0.215, 0.225, 0.07, cy=-0.025), 0.948), (rr(0.195, 0.205, 0.06, cy=-0.025), 0.984),
                     (rr(0.187, 0.197, 0.055, cy=-0.025), 0.988)])
    yf = -(HY_T + e) + 0.03
    for x0, x1 in ((-0.25, -0.165), (0.165, 0.25)):             # front handle tabs
        plastic |= bent([(x0, yf, 0.946), (x0, yf - 0.022, 0.976), (x1, yf - 0.022, 0.976), (x1, yf, 0.946)],
                        0.0075, bend=0.012, sides=8)
    for x in (-0.2, 0.2):                                         # hinge knuckles round the bar
        plastic |= new_faces(tube, [Vector((x - 0.03, BAR.y, BAR.z)), Vector((x + 0.03, BAR.y, BAR.z))], 0.026, sides=10)
        plastic |= box((x - 0.03, HY_T + 0.02, 0.925), (x + 0.03, BAR.y, 0.95))
    setmat(plastic_uv(plastic), PLASTIC)
    offset_verts(plastic, BAR)

def clean():
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")   # lathe() strays

def build(colour):
    mats = [f"BinPlastic{colour}", "BinRubber", "BinHub", "BinAxle"]
    body(); clean()
    ob = finish(f"WheelieBin{colour}", material=mats)
    lid(); clean()
    part(f"WheelieBin{colour}Lid", mats, parent=ob, at=BAR)
    return ob

plastic_maps()
BINS = [build("Green"), build("Black")]

path = os.path.join(OUT_DIR, "wheelie_bin.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    BINS[0].location.x, BINS[1].location.x = -0.45, 0.45
    BINS[1].rotation_euler.z = math.radians(25)
    BINS[1].children[0].rotation_euler.x = math.radians(-100)      # one lid open
    g = bpy.data.meshes.new("G"); g.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.12, 0.12, 0.13, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.0; sun.data.angle = math.radians(6)
    sun.rotation_euler = (math.radians(45), 0, math.radians(-40)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    for fname, at, look in (("wheelie_bin.png", (-1.6, -2.6, 1.6), (0.0, 0, 0.55)),
                            ("wheelie_bin_back.png", (1.9, 2.2, 1.2), (0.0, 0, 0.5))):
        cam.location = at; tgt.location = look; cam.data.lens = 40
        sc.render.resolution_x, sc.render.resolution_y = 1200, 1000
        sc.render.filepath = os.path.join(HERE, "render", fname)
        bpy.ops.render.render(write_still=True)
print("BINS DONE")
