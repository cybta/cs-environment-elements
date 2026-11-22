"""Low playground sandbox (the old playground set): a 2.4 m square of sand edged with
20 cm debarked logs, two courses laid log-cabin style (the corners cross and stick out),
the sand a little below the top log and heaped up unevenly.

  PlaygroundSandbox   about 2.8 x 2.8 m, 0.37 m high. Origin: floor, centre.
Slots: 0 C_fence_old_wood (each log takes one plank strip of the fence sheet, the same
weathered wood as the fences and quay), 1 PlaygroundSand (generated tileable sand).

Saves cs_environment_elements/props/assets/playground/playground_sandbox.blend (+ the sand
maps in its textures/) and, unless RENDER=0, render/sandbox.png beside this script.
Headless:  blender -b --factory-startup --python build_sandbox.py
"""
import os, math, random, importlib.util
import numpy as np
import bpy, bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
PKG = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements"))
OUT_DIR = os.path.join(PKG, "props", "assets", "playground")
TEXP = os.path.join(OUT_DIR, "textures")

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
TEX_DIR = TEXP
_spec = importlib.util.spec_from_file_location("fence_geom", os.path.join(PKG, "buildings", "fence_geom.py"))
fg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fg)
rng = random.Random(9)

INNER = 2.4          # sand square, side
LOG_D = 0.20         # log diameter
COURSES = 2
SAND_TILE = 1.2

# ---------------------------------------------------------------- sand texture
N = 1024
def fbm(seed, beta=2.0, lo=2.0):
    g = np.random.default_rng(seed)
    f = np.fft.fftfreq(N) * N
    fx, fy = np.meshgrid(f, f)
    r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
    amp = 1 / np.maximum(r, lo) ** (beta / 2); amp[0, 0] = 0
    n = np.real(np.fft.ifft2(np.fft.fft2(g.standard_normal((N, N))) * amp))
    return (n - n.min()) / (n.max() - n.min())

def sm(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)

def save(name, arr):
    arr = np.clip(arr, 0, 1)
    if arr.ndim == 2: arr = np.dstack([arr] * 3)
    img = bpy.data.images.new(name, N, N, alpha=False)
    img.pixels.foreach_set(np.dstack((arr, np.ones((N, N)))).astype(np.float32).ravel())
    img.filepath_raw = os.path.join(TEXP, name); img.file_format = "PNG"; img.save()
    bpy.data.images.remove(img); print("saved", name)

def sand_maps():
    os.makedirs(TEXP, exist_ok=True)
    grain, ripple, damp, pebble = fbm(51, 0.2), fbm(52, 2.2), fbm(53, 2.6), fbm(54, 0.9)
    c = np.array((0.70, 0.61, 0.45))[None, None, :] * (0.88 + 0.2 * grain + 0.1 * ripple)[..., None]
    c = c * (1 - 0.1 * sm(0.45, 0.9, damp))[..., None]                        # damper, darker patches
    q = np.quantile(pebble, 0.985); peb = sm(q, q + 0.01, pebble)
    c = c * (1 - 0.25 * peb)[..., None]
    save("playground_sand_diff_1k.png", c)
    save("playground_sand_rough_1k.png", 0.9 + 0.08 * grain)
    h = ripple * 0.6 + grain * 0.25 + peb * 0.4
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 3.0; dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 3.0
    n = np.dstack((-dx, -dy, np.ones_like(h))); n /= np.linalg.norm(n, axis=2, keepdims=True)
    save("playground_sand_nor_gl_1k.png", n * 0.5 + 0.5)

_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    if name == fg.MAT_WOOD:
        return fg.wood_material()
    if name == "PlaygroundSand" and not bpy.data.materials.get(name):
        return _textured(name, {"Base Color": "playground_sand_diff_1k.png", "Roughness": "playground_sand_rough_1k.png",
                                "Normal": "playground_sand_nor_gl_1k.png"}, 0.7)
    return _pg_ensure(name)

# ---------------------------------------------------------------- geometry

def plank_uv(faces):
    sides = [f for f in faces if len(f.verts) == 4]
    us = [l[uvl].uv[0] for f in sides for l in f.loops]; vs = [l[uvl].uv[1] for f in sides for l in f.loops]
    ulo, uhi, vlo, vhi = min(us), max(us), min(vs), max(vs)
    u0, u1, v0, v1 = rng.choice(fg.STRIPS)
    length, circ = (uhi - ulo) * TILE, (vhi - vlo) * TILE
    du = min(length * (v1 - v0) * fg._IMG_H / fg._IMG_W / max(circ, 1e-3), u1 - u0)
    s = rng.uniform(u0, u1 - du)
    hv = (v1 - v0) * 0.45                               # end grain: a disc inside the strip
    for f in faces:
        if len(f.verts) == 4:
            for l in f.loops:
                u, v = l[uvl].uv
                l[uvl].uv = (s + du * (u - ulo) / (uhi - ulo), v0 + (v1 - v0) * (v - vlo) / (vhi - vlo))
            continue
        f.normal_update()
        c = f.calc_center_median(); t1 = f.normal.orthogonal().normalized(); t2 = f.normal.cross(t1)
        k = hv / (LOG_D / 2)
        for l in f.loops:
            d = l.vert.co - c
            l[uvl].uv = (s + du * 0.5 + d.dot(t1) * k * fg._IMG_H / fg._IMG_W, (v0 + v1) / 2 + d.dot(t2) * k)
    return faces

def log(a, b):
    """Round log from a to b, slightly irregular radius along its length; one fence plank."""
    a, b = Vector(a), Vector(b)
    r0 = LOG_D / 2 * rng.uniform(0.94, 1.04)
    wob = [rng.uniform(-0.06, 0.06) for _ in range(4)]
    pts = [a.lerp(b, k / 8) for k in range(9)]
    rad = lambda t: r0 * (1 + wob[min(3, int(t * 4))] * 0.5 - 0.04 * t)
    fs = new_faces(tube, pts, rad, sides=12)
    plank_uv(fs)
    for f in fs: f.material_index = 0
    return fs

def sand(top, half, rings=10, segs=16):
    """Sand: a square grid inside the logs, heaped a little and dug in places."""
    n = 16
    vs = []
    hump = [(Vector((rng.uniform(-half, half) * 0.7, rng.uniform(-half, half) * 0.7)), rng.uniform(0.25, 0.6),
             rng.uniform(-0.05, 0.08)) for _ in range(6)]
    for j in range(n + 1):
        row = []
        for i in range(n + 1):
            x, y = -half + 2 * half * i / n, -half + 2 * half * j / n
            z = top
            edge = min(half - abs(x), half - abs(y)) / half
            for c, r, h in hump:
                d = (Vector((x, y)) - c).length / r
                if d < 1:
                    z += h * (1 - d * d) ** 2 * min(1, edge * 4)
            row.append(bm.verts.new((x, y, z)))
        vs.append(row)
    fs = []
    for j in range(n):
        for i in range(n):
            f = bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
            f.smooth = True; f.material_index = 1
            for l in f.loops: l[uvl].uv = (l.vert.co.x / SAND_TILE, l.vert.co.y / SAND_TILE)
            fs.append(f)
    return fs

def sandbox():
    begin()
    half = INNER / 2 + LOG_D / 2                   # log centre lines
    over = 0.16                                    # the ends stick out past the crossing
    r = LOG_D / 2
    for k in range(COURSES):
        # log-cabin: X logs on the bottom of each course, Y logs half a log higher, crossing
        zx = r + k * LOG_D * 0.85
        zy = zx + LOG_D * 0.42
        for s in (-1, 1):
            log((-half - over, s * half, zx), (half + over, s * half, zx))
            log((s * half, -half - over, zy), (s * half, half + over, zy))
    top = COURSES * LOG_D * 0.85 + LOG_D * 0.42 - 0.07       # sand a bit below the top log
    sand(top, INNER / 2 + 0.06)
    # sand under the fill so the box reads solid from the gaps between logs
    under = box((-INNER / 2 - 0.02, -INNER / 2 - 0.02, 0.0), (INNER / 2 + 0.02, INNER / 2 + 0.02, top - 0.03))
    for f in under: f.material_index = 1
    uv_box(under, SAND_TILE)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    return finish("PlaygroundSandbox", material=[fg.MAT_WOOD, "PlaygroundSand"])

sand_maps()
ob = sandbox()
path = os.path.join(OUT_DIR, "playground_sandbox.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    g = bpy.data.meshes.new("G"); g.from_pydata([(-6, -6, 0), (6, -6, 0), (6, 6, 0), (-6, 6, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.13, 0.14, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.2; sun.rotation_euler = (math.radians(45), 0, math.radians(-30)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    cam.location = (3.2, -3.6, 2.6)
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt); tgt.location = (0, 0, 0.1)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1200, 900
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    sc.render.filepath = os.path.join(HERE, "render", "sandbox.png")
    bpy.ops.render.render(write_still=True)
print("SANDBOX DONE")
