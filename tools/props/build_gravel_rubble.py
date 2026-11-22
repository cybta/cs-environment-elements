"""Gravel and rubble heaps (ref: Desktop/ref/gravel-rubble.jpeg + gravel-rubble-texture.jpeg).

Three pieces, one mesh each, origin on the floor at the centre:
  GravelPileLarge   ~2.8 x 1.9 m, 0.5 m high: pebbles, a few big broken stones on one side
  GravelPileSmall   ~1.4 x 1.0 m, 0.25 m high
  GravelSpill       ~2.2 x 1.5 m, a low spread of gravel (ground clutter)

Each is a low mound wearing the gravel photo (planar UVs from above, one GRAVEL_TILE
repeat centred on it; slot 0 GravelRubble) with real stones on it so the outline isn't smooth: rounded
pebbles (smooth-shaded convex hulls), angular broken stones (flat-shaded), and a few
pebbles rolled out onto the ground round the foot. Stones use slot 1 RubbleStone, a
generated mottled stone texture, each stone at a random UV offset so they differ in tone.
The mound's edge runs a little below the floor (z < 0) so it sinks into uneven ground.

Writes cs_environment_elements/props/assets/rubble/:
  gravel_rubble.blend
  textures/gravel_rubble_diff.jpg   (the photo, copied)
  textures/gravel_rubble_nor_gl.jpg, gravel_rubble_rough.jpg   (derived from the photo)
  textures/rubble_stone_diff_1k.png, _rough_1k.png, _nor_gl_1k.png   (generated)
and, unless RENDER=0, render/gravel_rubble.png beside this script.
Headless:  blender -b --factory-startup --python build_gravel_rubble.py
"""
import os, math, random, shutil
import numpy as np
import bpy, bmesh
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.expanduser("~"), "Desktop", "ref", "gravel-rubble-texture.jpeg")
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements", "props", "assets", "rubble"))
TEX = os.path.join(OUT_DIR, "textures")
GRAVEL_TILE = 3.0        # metres of ground per repeat of the gravel photo: the photo's stones then
                         # match the ref, and one repeat covers a whole heap centred on it (the
                         # photo doesn't tile cleanly, so no heap ever shows its seam)
STONE_TILE = 0.6         # metres per repeat of the stone texture

bpy.ops.wm.read_factory_settings(use_empty=True)
os.makedirs(TEX, exist_ok=True)

# ---------------------------------------------------------------- textures

def blur(a, sigma):
    """Gaussian blur through the FFT (wraps round, so tileable maps stay tileable)."""
    h, w = a.shape
    fy, fx = np.fft.fftfreq(h)[:, None], np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (math.pi * sigma) ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))

def normal_from(hgt, strength):
    dx = (np.roll(hgt, -1, 1) - np.roll(hgt, 1, 1)) * strength
    dy = (np.roll(hgt, -1, 0) - np.roll(hgt, 1, 0)) * strength
    n = np.dstack((-dx, -dy, np.ones_like(hgt)))
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5

def save(name, arr, fmt="PNG"):
    arr = np.clip(arr, 0, 1)
    if arr.ndim == 2:
        arr = np.dstack([arr] * 3)
    h, w = arr.shape[:2]
    img = bpy.data.images.new(name, w, h, alpha=False)
    img.pixels.foreach_set(np.dstack((arr, np.ones((h, w)))).astype(np.float32).ravel())
    img.filepath_raw = os.path.join(TEX, name)
    img.file_format = fmt
    if fmt == "JPEG":
        bpy.context.scene.render.image_settings.quality = 92
    img.save()
    bpy.data.images.remove(img)
    print("saved", name)

def gravel_maps():
    diff = os.path.join(TEX, "gravel_rubble_diff.jpg")
    shutil.copyfile(REF, diff)
    img = bpy.data.images.load(diff)
    w, h = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3]
    bpy.data.images.remove(img)
    lum = px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    print("gravel photo %dx%d  seam L|R %.3f  T|B %.3f  (neighbouring columns %.3f)" % (
        w, h, np.abs(lum[:, 0] - lum[:, -1]).mean(), np.abs(lum[0] - lum[-1]).mean(),
        np.abs(lum[:, w // 2] - lum[:, w // 2 + 1]).mean()))
    # stones are lit and lighter than the sand between them, so a blurred luminance makes
    # a usable height: broad shapes (stones) plus a little fine grain
    hgt = blur(lum, 6.0) * 0.7 + blur(lum, 1.5) * 0.3
    hgt = (hgt - hgt.min()) / (hgt.max() - hgt.min())
    save("gravel_rubble_nor_gl.jpg", normal_from(hgt, 9.0), "JPEG")
    cavity = np.clip((blur(lum, 4.0) - lum) * 4 + 0.5, 0, 1)      # dark gaps between stones
    save("gravel_rubble_rough.jpg", 0.72 + 0.2 * cavity, "JPEG")

N = 1024
def fbm(seed, beta=2.0, lo=2.0):
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(N) * N
    fx, fy = np.meshgrid(f, f)
    r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
    amp = 1 / np.maximum(r, lo) ** (beta / 2); amp[0, 0] = 0
    n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * amp))
    return (n - n.min()) / (n.max() - n.min())

def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)

def col(c):
    return np.array(c, dtype=np.float32)[None, None, :]

def lerp(a, b, t):
    return a + (b - a) * t[..., None]

def stone_maps():
    """Mottled stone: big patches of grey / brown-grey / dark (each stone, at its own UV
    offset, lands on a different tone like the ref), fine speckle, small pits."""
    tone, tone2 = fbm(21, 3.2), fbm(22, 3.0)
    fine, speck, pits = fbm(23, 1.2), fbm(24, 0.4), fbm(25, 0.9)
    c = lerp(col((0.53, 0.52, 0.50)), col((0.56, 0.48, 0.39)), smooth(0.35, 0.65, tone))
    c = lerp(c, col((0.34, 0.33, 0.31)), smooth(0.55, 0.8, tone2) * 0.7)
    c = c * (0.82 + 0.3 * fine)[..., None] * (0.94 + 0.1 * speck)[..., None]
    q = np.quantile(pits, 0.93)
    pit = smooth(q - 0.01, q + 0.01, pits)
    c = lerp(c, c * 0.55, pit)
    dust = smooth(0.6, 0.9, fbm(26, 2.4))                           # sandy dust in places
    c = lerp(c, col((0.52, 0.46, 0.38)), dust * 0.35)
    save("rubble_stone_diff_1k.png", c)
    save("rubble_stone_rough_1k.png", 0.7 + 0.15 * fine + 0.1 * pit)
    save("rubble_stone_nor_gl_1k.png", normal_from(fine * 0.6 + speck * 0.2 - pit * 0.5, 4.0))

def textured(name, maps, normal_strength):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for sock, fname in maps.items():
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(os.path.join(TEX, fname), check_existing=True)
        if sock != "Base Color":
            n.image.colorspace_settings.name = "Non-Color"
        if sock == "Normal":
            nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = normal_strength
            nt.links.new(n.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        else:
            nt.links.new(n.outputs["Color"], bsdf.inputs[sock])
    bsdf.inputs["Metallic"].default_value = 0.0
    return mat

# ---------------------------------------------------------------- mound

class Heap:
    """Analytic heap: an irregular oval outline and a dome with a few humps and dents,
    so stones can be set on its surface exactly."""

    def __init__(self, rng, rx, ry, h, peak=(0.0, 0.0), humps=12):
        self.rx, self.ry, self.h = rx, ry, h
        self.lobes = [(rng.uniform(0.04, 0.09) / k, k, rng.uniform(0, 2 * math.pi)) for k in range(2, 7)]
        self.peak = Vector(peak)
        self.bumps = [(Vector((rng.uniform(-rx, rx) * 0.8, rng.uniform(-ry, ry) * 0.8)),
                       rng.uniform(0.15, 0.45) * min(rx, ry), rng.uniform(-0.12, 0.18) * h) for _ in range(humps)]

    def rim(self, th):
        """Outline radius at angle th."""
        e = 1 / math.sqrt((math.cos(th) / self.rx) ** 2 + (math.sin(th) / self.ry) ** 2)
        return e * (1 + sum(a * math.cos(k * th + p) for a, k, p in self.lobes))

    def rn(self, x, y):
        """0 at the peak, 1 on the outline (the peak may sit off centre)."""
        th = math.atan2(y, x)
        R = self.rim(th)
        rho = math.hypot(x, y) / R
        # shift the dome's top towards `peak`, fading out at the rim
        q = Vector((x, y)) - self.peak * max(0.0, 1 - rho)
        return math.hypot(q.x, q.y) / self.rim(math.atan2(q.y, q.x))

    def z(self, x, y):
        t = self.rn(x, y)
        if t >= 1:
            return -0.03 * min(1.0, (t - 1) * 8)
        z = self.h * (1 - t * t) ** 1.4
        for c, r, a in self.bumps:
            d = (Vector((x, y)) - c).length / r
            if d < 1:
                z += a * (1 - d * d) ** 2 * (1 - t)
        return max(z, 0.0)

def mound(bm, uvl, heap, rings=18, segs=56):
    """Polar grid over the heap out to a skirt just past the outline (dips below z=0)."""
    centre = bm.verts.new((0, 0, heap.z(0, 0)))
    grid = []
    for i in range(1, rings + 2):
        f = i / rings if i <= rings else 1.1                 # last ring: the skirt
        row = []
        for k in range(segs):
            th = 2 * math.pi * k / segs
            R = heap.rim(th) * f
            x, y = R * math.cos(th), R * math.sin(th)
            row.append(bm.verts.new((x, y, heap.z(x, y))))
        grid.append(row)
    faces = []
    for k in range(segs):
        faces.append(bm.faces.new((centre, grid[0][k], grid[0][(k + 1) % segs])))
    for a, b in zip(grid, grid[1:]):
        for k in range(segs):
            k2 = (k + 1) % segs
            faces.append(bm.faces.new((a[k], b[k], b[k2], a[k2])))
    for f in faces:
        f.material_index = 0
        f.smooth = True
        for l in f.loops:
            l[uvl].uv = (l.vert.co.x / GRAVEL_TILE + 0.5, l.vert.co.y / GRAVEL_TILE + 0.5)

# ---------------------------------------------------------------- stones

def stone(bm, uvl, rng, at, size, flat, angular):
    """Convex hull. angular: a box's corners pushed about and a few corners knocked off,
    flat shaded (a blocky broken stone); else points on a squashed ellipsoid, smooth
    (a pebble). size = (x, y, z) full extents."""
    pts = []
    if angular:
        for cx in (-1, 1):
            for cy in (-1, 1):
                for cz in (-1, 1):
                    p = Vector((cx, cy, cz)) + Vector([rng.uniform(-0.3, 0.3) for _ in range(3)])
                    if rng.random() < 0.45:                            # chipped corner: two points in from it
                        ax = rng.randrange(3)
                        q = p.copy(); q[ax] *= rng.uniform(0.3, 0.6)
                        p[(ax + 1) % 3] *= rng.uniform(0.3, 0.6)
                        pts.append(q)
                    pts.append(p)
        pts = [Vector((p.x * size[0], p.y * size[1], p.z * size[2])) * 0.36 for p in pts]   # ~size overall
    else:
        for _ in range(rng.randint(9, 12)):
            v = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
            pts.append(Vector((v.x * size[0] / 2, v.y * size[1] / 2, v.z * size[2] / 2)))
    rot = Euler((rng.uniform(-flat, flat), rng.uniform(-flat, flat), rng.uniform(0, 2 * math.pi))).to_matrix()
    verts = [bm.verts.new(rot @ p + at) for p in pts]
    res = bmesh.ops.convex_hull(bm, input=verts)
    junk = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if junk:
        bmesh.ops.delete(bm, geom=junk, context="VERTS")
    faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace) and g.is_valid]
    du, dv = rng.random(), rng.random()
    for f in faces:
        f.material_index = 1
        f.smooth = not angular
        f.normal_update()
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for l in f.loops:
            l[uvl].uv = (l.vert.co[a] / STONE_TILE + du, l.vert.co[b] / STONE_TILE + dv)
    return faces

def sizes(rng, lo, hi, flatness):
    s = rng.uniform(lo, hi)
    return (s * rng.uniform(0.8, 1.25), s * rng.uniform(0.7, 1.0), s * rng.uniform(*flatness))

def scatter(bm, uvl, rng, heap, count, lo, hi, angular, region=None, out=False, flat=0.35):
    """`count` stones on the heap (or, out=True, on the floor round its foot)."""
    placed = 0
    tries = 0
    while placed < count and tries < count * 40:
        tries += 1
        th = rng.uniform(0, 2 * math.pi)
        t = rng.uniform(1.0, 1.45) if out else math.sqrt(rng.random()) * 0.97
        R = heap.rim(th) * t
        x, y = R * math.cos(th), R * math.sin(th)
        if region and not region(x, y):
            continue
        sz = sizes(rng, lo, hi, (0.45, 0.75) if angular else (0.5, 0.8))
        sink = rng.uniform(0.0, 0.2) if angular and sz[0] > 0.12 else rng.uniform(0.05, 0.25)
        z = (0.0 if out else heap.z(x, y)) + sz[2] * sink                       # sunk in a little
        stone(bm, uvl, rng, Vector((x, y, z)), sz, flat, angular)
        placed += 1

# ---------------------------------------------------------------- pieces

def piece(name, seed, rx, ry, h, peak, pebbles, chunks, chips, outside, big=(0.16, 0.38), humps=12):
    rng = random.Random(seed)
    bm = bmesh.new(); uvl = bm.loops.layers.uv.new("UVMap")
    heap = Heap(rng, rx, ry, h, peak, humps)
    mound(bm, uvl, heap)
    side = Vector((math.cos(seed), math.sin(seed)))                     # the big stones gather on one side
    scatter(bm, uvl, rng, heap, chunks, *big, angular=True, region=lambda x, y: Vector((x / rx, y / ry)).dot(side) > -0.1)
    scatter(bm, uvl, rng, heap, chips, 0.05, 0.12, angular=True)
    scatter(bm, uvl, rng, heap, pebbles, 0.035, 0.08, angular=False)
    scatter(bm, uvl, rng, heap, outside, 0.025, 0.07, angular=False, out=True)
    scatter(bm, uvl, rng, heap, outside // 4, 0.04, 0.1, angular=True, out=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob)
    me.materials.append(MATS[0]); me.materials.append(MATS[1])
    print(name, "tris", sum(len(p.vertices) - 2 for p in me.polygons), "dims",
          tuple(round(v, 2) for v in ob.dimensions))
    return ob

gravel_maps()
stone_maps()
MATS = [textured("GravelRubble", {"Base Color": "gravel_rubble_diff.jpg", "Roughness": "gravel_rubble_rough.jpg",
                                  "Normal": "gravel_rubble_nor_gl.jpg"}, 1.0),
        textured("RubbleStone", {"Base Color": "rubble_stone_diff_1k.png", "Roughness": "rubble_stone_rough_1k.png",
                                 "Normal": "rubble_stone_nor_gl_1k.png"}, 0.6)]

PIECES = [
    piece("GravelPileLarge", 3, 1.45, 0.95, 0.5, (0.25, 0.1), pebbles=170, chunks=8, chips=34, outside=70),
    piece("GravelPileSmall", 5, 0.72, 0.5, 0.25, (0.08, 0.05), pebbles=60, chunks=3, chips=14, outside=30,
          big=(0.12, 0.22), humps=6),
    piece("GravelSpill", 8, 1.1, 0.75, 0.07, (0.2, 0.0), pebbles=70, chunks=2, chips=20, outside=45,
          big=(0.12, 0.2), humps=10),
]

path = os.path.join(OUT_DIR, "gravel_rubble.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

# ---------------------------------------------------------------- preview render
if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    for ob, x in zip(PIECES, (0.0, 3.0, -3.2)):
        ob.location.x = x
    g = bpy.data.meshes.new("G"); g.from_pydata([(-8, -6, 0), (8, -6, 0), (8, 6, 0), (-8, 6, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.11, 0.11, 0.11, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.0; sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(40), 0, math.radians(-30)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.55, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    for fname, at, look, lens, res in (("gravel_rubble.png", (1.2, -7.5, 3.6), (0.0, 0, 0.1), 32, (1400, 800)),
                                       ("gravel_rubble_close.png", (1.2, -3.3, 1.7), (0.1, 0, 0.15), 35, (1400, 800))):
        cam.location = at; tgt.location = look; cam.data.lens = lens
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.filepath = os.path.join(HERE, "render", fname)
        bpy.ops.render.render(write_still=True)
print("RUBBLE DONE")
