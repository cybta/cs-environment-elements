"""Firewood shed (ref: the user's photo: an open-fronted lean-to log store).

  WoodshedNew   fresh yellow pine
  WoodshedOld   the weathered fence planks (matches the fences, quay and yard furniture)

3.0 m wide, 1.0 m deep, 2.05 m at the front eave. A raised plank floor on joists with a
kick board, three front and three back posts, slatted back and side walls (horizontal
boards with gaps), a lean-to roof falling to the back: rafters, a board deck, a dark felt
cover and a front fascia. Two bays of split firewood fill it to about 1.3 m: the front row
is real logs (rounds, halves, quarters and wedges, end grain with rings and cracks, pine bark on
the round side, split wood on the flat sides); behind it a filler block wears the same
wood, so the store reads full through the wall gaps.

Origin: floor, centre; front (open side) to -Y. Slots: 0 wood (WoodPine / fence planks),
1 RoofFelt, 2 Firewood (one atlas: end grain, bark, split wood).

Saves cs_environment_elements/props/assets/garden/woodshed.blend (+ textures) and, unless
RENDER=0, render/woodshed.png beside this script.
Headless:  blender -b --factory-startup --python build_woodshed.py
"""
import os, math, random, importlib.util
import numpy as np
import bpy, bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
PKG = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements"))
OUT_DIR = os.path.join(PKG, "props", "assets", "garden")
TEXW = os.path.join(OUT_DIR, "textures")
BARK_PHOTO = os.path.join(PKG, "nature", "textures", "pine_trunk", "pine_bark_diff_1k.jpg")   # the pine trees' bark

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
_spec = importlib.util.spec_from_file_location("fence_geom", os.path.join(PKG, "buildings", "fence_geom.py"))
fg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fg)
rng = random.Random(41)
WOOD_I, FELT_I, FIRE_I = 0, 1, 2
exec(open(os.path.join(HERE, "plank_lib.py")).read())          # strip(), plank(), round_leg()

SIMPLE_MATERIALS.update({"RoofFelt": ((0.07, 0.07, 0.075), 0.92, 0.0, None, 0)})

# ================================================================ textures

def _fbm(n, seed, beta=2.0, stretch=(1.0, 1.0), lo=2.0):
    g = np.random.default_rng(seed)
    f = np.fft.fftfreq(n) * n
    fx, fy = np.meshgrid(f / stretch[0], f / stretch[1])
    r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
    amp = 1 / np.maximum(r, lo) ** (beta / 2); amp[0, 0] = 0
    x = np.real(np.fft.ifft2(np.fft.fft2(g.standard_normal((n, n))) * amp))
    return (x - x.min()) / (x.max() - x.min())

def _sm(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)

def _lerp(a, b, t): return a + (b - a) * t[..., None]
def _col(c): return np.array(c, np.float32)[None, None, :]

def _save(name, arr):
    h, w = arr.shape[:2]
    if arr.ndim == 2: arr = np.dstack([arr] * 3)
    if arr.shape[2] == 3: arr = np.dstack((arr, np.ones((h, w), np.float32)))
    img = bpy.data.images.new(name, w, h, alpha=True)
    img.pixels.foreach_set(np.clip(arr, 0, 1).astype(np.float32).ravel())
    img.filepath_raw = os.path.join(TEXW, name); img.file_format = "PNG"; img.save()
    bpy.data.images.remove(img); print("saved", name)

def pine_sheet():
    """The fence plank sheet re-toned to fresh yellow pine (same layout, so plank() UVs fit)."""
    img = bpy.data.images.load(fg.TEX_PATH)
    w, h = img.size
    px = np.array(img.pixels[:], np.float32).reshape(h, w, 4)
    bpy.data.images.remove(img)
    lum = px[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    t = np.clip((lum - 0.15) / 0.6, 0, 1)
    grain = 0.75 + 0.35 * t
    c = _col((0.86, 0.66, 0.38)) * grain[..., None]
    c = _lerp(c, _col((0.62, 0.42, 0.22)), _sm(0.35, 0.1, lum) * 0.7)          # knots, darker grain
    _save("fence_pine.png", np.dstack((c, px[..., 3])))

def firewood_atlas():
    """1024 x 1024: end grain (u 0-.5, v .5-1), pine bark photo (u .5-1, v .5-1), split wood (v 0-.5)."""
    n = 512
    ys, xs = (np.mgrid[0:n, 0:n] + 0.5) / n
    r = np.hypot(xs - 0.5, ys - 0.5) / 0.5
    ang = np.arctan2(ys - 0.5, xs - 0.5)
    wob = _fbm(n, 3, 2.0) * 0.08
    rings = 0.5 + 0.5 * np.sin((r + wob) * 2 * math.pi * 14)
    end = _col((0.78, 0.6, 0.38)) * (0.82 + 0.18 * rings)[..., None]
    end = _lerp(end, _col((0.6, 0.38, 0.2)), _sm(0.45, 0.0, r) * 0.45)          # heartwood
    end = _lerp(end, _col((0.28, 0.2, 0.14)), _sm(0.9, 0.97, r))                # bark ring
    crack = np.zeros((n, n), np.float32)
    g = random.Random(4)
    for _ in range(5):                                                           # drying checks
        a0 = g.uniform(-math.pi, math.pi)
        d = np.abs(((ang - a0 + math.pi) % (2 * math.pi)) - math.pi) * r
        crack = np.maximum(crack, _sm(0.012, 0.0, d) * _sm(0.2, 0.5, r) * (r < 0.9))
    end = _lerp(end, _col((0.2, 0.13, 0.08)), crack * 0.8)
    end = end * (0.9 + 0.15 * _fbm(n, 5, 1.2))[..., None]
    # bark: the pine trees' own bark photo (nature/textures/pine_trunk), its height along the
    # log (atlas V), averaged down 2x to fill the 512 cell
    img = bpy.data.images.load(BARK_PHOTO)
    bw, bh = img.size
    bp = np.array(img.pixels[:], np.float32).reshape(bh, bw, 4)[..., :3]
    bpy.data.images.remove(img)
    f = max(1, bw // n)
    bark = bp[:n * f, :n * f].reshape(n, f, n, f, 3).mean(axis=(1, 3))
    split = np.zeros((n, 2 * n, 3), np.float32)
    ys2, xs2 = (np.mgrid[0:n, 0:2 * n] + 0.5) / n
    fib = _fbm(2 * n, 8, 1.4, stretch=(1.0, 0.08))[:n, :]
    split[:] = _col((0.8, 0.63, 0.42)) * (0.78 + 0.32 * fib)[..., None]
    atlas = np.zeros((2 * n, 2 * n, 3), np.float32)
    atlas[:n, :] = split
    atlas[n:, :n] = end
    atlas[n:, n:] = bark
    _save("firewood_atlas_1k.png", atlas)

def material(name, image, rough):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = bpy.data.images.load(os.path.join(TEXW, image), check_existing=True)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    return mat

_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    if bpy.data.materials.get(name):
        return bpy.data.materials[name]
    if name == fg.MAT_WOOD:
        return fg.wood_material()
    if name == "WoodPine":
        return material("WoodPine", "fence_pine.png", 0.7)
    if name == "Firewood":
        return material("Firewood", "firewood_atlas_1k.png", 0.85)
    return _pg_ensure(name)

# ================================================================ shed

W, D = 3.0, 1.0
FLOOR = 0.16                     # deck top
H_FRONT, H_BACK = 2.0, 1.72      # top of the front / back beams
POST = 0.09

def roof_z(y):
    """Underside of the rafters at depth y (front y = -D/2 is high)."""
    t = (y + D / 2) / D
    return H_FRONT + (H_BACK - H_FRONT) * t

def shear(fs, y0, k):
    """Tilt parts built level: z += k * (y - y0) (roof slope)."""
    for v in {v for f in fs for v in f.verts}: v.co.z += k * (v.co.y - y0)
    return fs

def shed():
    xs = (-W / 2 + POST / 2, 0.0, W / 2 - POST / 2)
    # floor: joists along Y, deck boards along X, front kick board
    for x in (-W / 2 + 0.05, -W / 4, 0.0, W / 4, W / 2 - 0.05):
        plank((x - 0.03, -D / 2, 0.0), (x + 0.03, D / 2, FLOOR - 0.025), 1)
    y = -D / 2
    while y < D / 2 - 0.02:
        bw = min(0.14, D / 2 - y)
        plank((-W / 2, y, FLOOR - 0.025), (W / 2, y + bw - 0.008, FLOOR), 0)
        y += bw
    plank((-W / 2, -D / 2 - 0.025, 0.0), (W / 2, -D / 2, FLOOR + 0.05), 0)                     # kick board
    # posts
    for x in xs:
        plank((x - POST / 2, -D / 2, 0.0), (x + POST / 2, -D / 2 + POST, H_FRONT), 2, bevel=0.006)
        plank((x - POST / 2, D / 2 - POST, 0.0), (x + POST / 2, D / 2, H_BACK), 2, bevel=0.006)
    # beams: front header and back plate, side top rails
    plank((-W / 2, -D / 2 - 0.045, H_FRONT - 0.16), (W / 2, -D / 2, H_FRONT), 0)
    plank((-W / 2, D / 2, H_BACK - 0.14), (W / 2, D / 2 + 0.045, H_BACK), 0)
    # slatted walls: back (outside the back posts) and sides (outside the end posts)
    slat, gap, z = 0.12, 0.045, FLOOR + 0.06
    while z + slat < H_BACK - 0.16:
        plank((-W / 2, D / 2, z), (W / 2, D / 2 + 0.022, z + slat), 0)
        for sx in (-1, 1):
            x0 = sx * W / 2
            lo, hi = sorted((x0, x0 + sx * 0.022))
            top = min(z + slat, roof_z(-D / 2) - 0.02)
            plank((lo, -D / 2, z), (hi, D / 2 + 0.022, top), 1)
        z += slat + gap
    for sx in (-1, 1):                                    # side top rails, following the slope
        x0 = sx * (W / 2 + 0.011)
        lo, hi = sorted((x0 - 0.011, x0 + 0.011))
        shear(plank((lo, -D / 2, H_FRONT - 0.12), (hi, D / 2, H_FRONT)), -D / 2, (H_BACK - H_FRONT) / D)
    # roof: rafters, deck boards, felt, fascia
    k = (H_BACK - H_FRONT) / D
    yf, yb = -D / 2 - 0.3, D / 2 + 0.12
    n = 8
    for i in range(n):
        x = -W / 2 + 0.03 + i * (W - 0.06) / (n - 1)
        shear(plank((x - 0.025, yf, H_FRONT), (x + 0.025, yb, H_FRONT + 0.12), 1), -D / 2, k)
    x = -W / 2 - 0.1
    while x < W / 2 + 0.1 - 0.01:
        bw = min(0.16, W / 2 + 0.1 - x)
        shear(plank((x, yf, H_FRONT + 0.12), (x + bw - 0.004, yb, H_FRONT + 0.14), 1), -D / 2, k)
        x += bw
    felt = box((-W / 2 - 0.11, yf - 0.01, H_FRONT + 0.14), (W / 2 + 0.11, yb + 0.01, H_FRONT + 0.155))
    shear(felt, -D / 2, k)
    uv_box(felt, TILE)
    for f in felt: f.material_index = FELT_I
    fz = H_FRONT + k * (yf + D / 2)
    plank((-W / 2 - 0.11, yf - 0.022, fz + 0.01), (W / 2 + 0.11, yf, fz + 0.16), 0)    # front fascia

# ================================================================ firewood

SECTIONS = {"round": (0.0, 2 * math.pi), "half": (0.0, math.pi), "quarter": (0.0, math.pi / 2),
            "third": (0.0, 2 * math.pi / 3)}

def log(cx, cz, y0, y1, R, kind, spin):
    """A split log along Y from y0 to y1; its tree centre lands so the piece is centred on
    (cx, cz). End faces show the rings round the tree centre, arcs bark, flats split wood."""
    a0, a1 = SECTIONS[kind]
    nseg = {"round": 8, "half": 5, "quarter": 3, "third": 4}[kind]
    pts = [(math.cos(a0 + (a1 - a0) * i / nseg) * R, math.sin(a0 + (a1 - a0) * i / nseg) * R, True)
           for i in range(nseg + (0 if kind == "round" else 1))]
    if kind != "round":
        pts.append((0.0, 0.0, False))                                 # the tree centre (split faces meet here)
    c, s = math.cos(spin), math.sin(spin)
    pts = [(c * x - s * z, s * x + c * z, bark) for x, z, bark in pts]
    mx = sum(p[0] for p in pts) / len(pts); mz = sum(p[1] for p in pts) / len(pts)
    off = (cx - mx, cz - mz)
    front = [bm.verts.new((x + off[0], y0, z + off[1])) for x, z, _ in pts]
    back = [bm.verts.new((x + off[0], y1, z + off[1])) for x, z, _ in pts]
    m = len(pts)
    du = rng.uniform(-0.04, 0.04)
    def end_uv(i):
        x, z, _ = pts[i]
        return (0.25 + 0.235 * x / R + du * 0.1, 0.75 + 0.235 * z / R)
    f = bm.faces.new(front[::-1]); f.material_index = FIRE_I
    for l in f.loops: l[uvl].uv = end_uv(front.index(l.vert))
    f = bm.faces.new(back); f.material_index = FIRE_I
    for l in f.loops: l[uvl].uv = end_uv(back.index(l.vert))
    sv = rng.random() * 0.4
    for i in range(m):
        j = (i + 1) % m
        f = bm.faces.new((front[i], front[j], back[j], back[i])); f.material_index = FIRE_I
        bark = pts[i][2] and pts[j][2]
        if bark:
            u0, u1 = 0.5 + 0.5 * i / m, 0.5 + 0.5 * (i + 1) / m
            uvs = ((u0, 0.5), (u1, 0.5), (u1, 0.99), (u0, 0.99))
        else:
            uvs = ((sv, 0.02), (sv + 0.25, 0.02), (sv + 0.25, 0.48), (sv, 0.48))
        for l, uv in zip(f.loops, uvs): l[uvl].uv = uv

def stack(x0, x1, z0, z1, y0, y1):
    """One bay: the front row of logs, ends to the front, and a filler block behind."""
    cell = 0.135
    row = 0
    z = z0 + cell / 2
    while z < z1:
        x = x0 + cell / 2 + (cell / 2 if row % 2 else 0)
        while x < x1 - cell * 0.4:
            if z + cell > z1 and rng.random() < 0.45:                # ragged top
                x += cell; continue
            kind = rng.choices(("round", "half", "quarter", "third"), (0.25, 0.3, 0.25, 0.2))[0]
            R = {"round": 0.068, "half": 0.09, "quarter": 0.12, "third": 0.105}[kind] * rng.uniform(0.85, 1.12)
            yy = y0 + rng.uniform(-0.03, 0.02)
            log(x + rng.uniform(-0.01, 0.01), z + rng.uniform(-0.01, 0.01), yy, yy + rng.uniform(0.36, 0.42), R, kind,
                rng.uniform(0, 2 * math.pi))
            x += cell
        z += cell * 0.88
        row += 1
    fill = box((x0 + 0.01, y0 + 0.3, z0), (x1 - 0.01, y1, z1 - cell * 1.3))
    for f in fill:
        f.material_index = FIRE_I
        f.normal_update()
        for l in f.loops:                                                # split-wood sides all round
            p = l.vert.co
            l[uvl].uv = ((p.x if abs(f.normal.x) < 0.5 else p.y) * 0.6 % 1.0, 0.02 + 0.46 * ((p.z * 0.8) % 1.0))

def build(name, wood):
    begin()
    shed()
    inner = W / 2 - POST - 0.03
    for bx0, bx1 in ((-inner, -POST / 2 - 0.03), (POST / 2 + 0.03, inner)):
        stack(bx0, bx1, FLOOR + 0.005, FLOOR + 1.3, -D / 2 + 0.12, D / 2 - 0.06)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    return finish(name, material=[wood, "RoofFelt", "Firewood"])

os.makedirs(TEXW, exist_ok=True)
pine_sheet()
firewood_atlas()
rng = random.Random(41)
new = build("WoodshedNew", "WoodPine")
rng = random.Random(41)
old = build("WoodshedOld", fg.MAT_WOOD)
for ob in (new, old):
    print(ob.name, "tris", sum(len(p.vertices) - 2 for p in ob.data.polygons))

path = os.path.join(OUT_DIR, "woodshed.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    old.location.x = 3.8
    g = bpy.data.meshes.new("G"); g.from_pydata([(-8, -6, 0), (10, -6, 0), (10, 8, 0), (-8, 8, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.13, 0.14, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.2; sun.data.angle = math.radians(5)
    sun.rotation_euler = (math.radians(50), 0, math.radians(-25)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1800, 1000
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    for fname, at, look, lens in (("woodshed.png", (-0.6, -7.4, 2.4), (1.9, 0, 1.0), 32),
                                  ("woodshed_close.png", (-1.0, -3.4, 1.4), (-0.3, 0, 0.8), 32)):
        cam.location, tgt.location, cam.data.lens = at, look, lens
        sc.render.filepath = os.path.join(HERE, "render", fname)
        bpy.ops.render.render(write_still=True)
print("WOODSHED DONE")
