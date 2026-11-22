"""Old garden and yard set (ref: the user's sheet: shovel, fork, hose, wheelbarrow,
watering can, crates, concrete blocks). One object per piece, origin on the floor at the
centre of its footprint:

  GardenShovel      round-point shovel standing upright, 1.12 m, D handle
  GardenFork        4-tine digging fork standing upright, 1.12 m
  GardenHose        green hose coiled on the ground, tail with a coupling
  Wheelbarrow       galvanised tray on a rusty tube frame, one wheel at the front (-Y)
  WateringCan       galvanised can, spout and rose to the front (-Y)
  WoodenCrate       slatted crate 0.56 x 0.38 x 0.3 m
  ConcreteBlock     hollow block 0.39 x 0.19 x 0.19 m, two cores (standing up)

Materials (shared with the rest of the add-on):
  C_fence_old_wood  the fence planks: handles and the crate take one plank strip each
  DarkSteel / GalvSteel / Rubber   the playground's peeled-to-rust steel, worn galvanised
                                   sheet and rubber (props/assets/playground/textures)
  BlockConcrete     generated cinder-block maps (garden/textures/cinder_block_*)
  HoseGreen, HoseFitting           plain values

Saves cs_environment_elements/props/assets/garden/garden_set.blend and, unless RENDER=0,
render/garden_set.png beside this script.
Headless:  blender -b --factory-startup --python build_garden_set.py
"""
import os, math, random, importlib.util
import bpy, bmesh
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "furniture", "old")
PKG = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements"))
OUT_DIR = os.path.join(PKG, "props", "assets", "garden")

bpy.ops.wm.read_factory_settings(use_empty=True)
exec(open(os.path.join(LIB, "bentwood_lib.py")).read())
exec(open(os.path.join(LIB, "playground_lib.py")).read())
TEX_DIR = os.path.join(PKG, "props", "assets", "playground", "textures")
_spec = importlib.util.spec_from_file_location("fence_geom", os.path.join(PKG, "buildings", "fence_geom.py"))
fg = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(fg)
rng = random.Random(5)

SIMPLE_MATERIALS.update({
    "HoseGreen": ((0.13, 0.24, 0.16), 0.55, 0.0, None, 0),
    "HoseFitting": ((0.20, 0.30, 0.20), 0.45, 0.0, None, 0),
})
WOOD = fg.MAT_WOOD
_pg_ensure = ensure_material
def ensure_material(name="OldWornWood"):
    if name == WOOD:
        return fg.wood_material()
    if name == "BlockConcrete" and not bpy.data.materials.get(name):
        cinder_maps()
        return _textured(name, {"Base Color": os.path.join(TEXG, "cinder_block_diff_1k.png"),
                                "Roughness": os.path.join(TEXG, "cinder_block_rough_1k.png"),
                                "Normal": os.path.join(TEXG, "cinder_block_nor_gl_1k.png")}, 1.0)
    return _pg_ensure(name)

TEXG = os.path.join(OUT_DIR, "textures")

def cinder_maps():
    """Coarse grey cinder block: open pores, aggregate speckle, dirt and a few rust stains
    (ref). Tileable; one repeat = 1 m (uv_box on the block)."""
    import numpy as np
    N = 1024
    def fbm(seed, beta=2.0, stretch=1.0, lo=2.0):
        g = np.random.default_rng(seed)
        f = np.fft.fftfreq(N) * N
        fx, fy = np.meshgrid(f / stretch, f)
        r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
        amp = 1 / np.maximum(r, lo) ** (beta / 2); amp[0, 0] = 0
        n = np.real(np.fft.ifft2(np.fft.fft2(g.standard_normal((N, N))) * amp))
        return (n - n.min()) / (n.max() - n.min())
    def sm(e0, e1, x):
        t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)
    def lerp(a, b, t): return a + (b - a) * t[..., None]
    def col(c): return np.array(c, dtype=np.float32)[None, None, :]
    def save(name, arr):
        arr = np.clip(arr, 0, 1)
        if arr.ndim == 2: arr = np.dstack([arr] * 3)
        img = bpy.data.images.new(name, N, N, alpha=False)
        img.pixels.foreach_set(np.dstack((arr, np.ones((N, N)))).astype(np.float32).ravel())
        img.filepath_raw = os.path.join(TEXG, name); img.file_format = "PNG"; img.save()
        bpy.data.images.remove(img); print("saved", name)
    os.makedirs(TEXG, exist_ok=True)
    grain, speck, pores, tone = fbm(41, 0.6), fbm(42, 0.6), fbm(43, 1.1), fbm(44, 2.6)
    q = np.quantile(pores, 0.955); pore = sm(q, q + 0.02, pores)
    rust = sm(0.68, 0.82, fbm(45, 2.2, stretch=0.35)) * sm(0.5, 0.75, fbm(46, 2.8))      # stains running down
    dirt = sm(0.55, 0.9, fbm(47, 2.4))
    c = lerp(col((0.50, 0.49, 0.47)), col((0.60, 0.58, 0.55)), sm(0.3, 0.7, tone))
    c = c * (0.85 + 0.25 * grain)[..., None]
    c = lerp(c, col((0.66, 0.64, 0.60)), sm(0.8, 0.92, speck) * 0.35)                    # pale aggregate
    c = lerp(c, col((0.48, 0.30, 0.18)), rust * 0.7)
    c = lerp(c, col((0.30, 0.27, 0.23)), dirt * 0.35)
    c = lerp(c, c * 0.5, pore)
    save("cinder_block_diff_1k.png", c)
    save("cinder_block_rough_1k.png", 0.85 + 0.1 * grain + 0.05 * pore)
    h = grain * 0.4 + speck * 0.3 - pore * 0.9
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 4.0; dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 4.0
    n = np.dstack((-dx, -dy, np.ones_like(h))); n /= np.linalg.norm(n, axis=2, keepdims=True)
    save("cinder_block_nor_gl_1k.png", n * 0.5 + 0.5)

# ---------------------------------------------------------------- helpers

def setmat(faces, slot):
    for f in faces: f.material_index = slot
    return faces

def plank_uv(faces):
    """Lay one fence plank strip along a round wooden part (tube UVs: U along, V round)."""
    sides = [f for f in faces if len(f.verts) == 4]
    us = [l[uvl].uv[0] for f in sides for l in f.loops]; vs = [l[uvl].uv[1] for f in sides for l in f.loops]
    ulo, uhi, vlo, vhi = min(us), max(us), min(vs), max(vs)
    u0, u1, v0, v1 = rng.choice(fg.STRIPS)
    length, circ = (uhi - ulo) * TILE, (vhi - vlo) * TILE
    du = min(length * (v1 - v0) * fg._IMG_H / fg._IMG_W / max(circ, 1e-3), u1 - u0)
    s = rng.uniform(u0, u1 - du)
    for f in faces:
        for l in f.loops:
            if len(f.verts) == 4:
                u, v = l[uvl].uv
                l[uvl].uv = (s + du * (u - ulo) / max(uhi - ulo, 1e-6), v0 + (v1 - v0) * (v - vlo) / max(vhi - vlo, 1e-6))
            else:                                                   # end grain: a spot inside the strip
                l[uvl].uv = (s + du * 0.5 + (l.vert.co.x % 0.02), (v0 + v1) / 2 + (l.vert.co.y % 0.02))
    return faces

def wood(faces):
    return setmat(plank_uv(faces), 0)

def along(faces, start, direction):
    """Turn parts built along +Z to point along `direction`, then move to `start`."""
    m = Vector((0, 0, 1)).rotation_difference(Vector(direction).normalized()).to_matrix()
    for v in {v for f in faces for v in f.verts}: v.co = m @ v.co + Vector(start)
    return faces

def x_axis(faces, centre, mirror=False):
    """Parts built round Z turned to round X (wheels), then moved to `centre`."""
    rot = Matrix.Rotation(math.pi / 2, 3, "Y")
    for v in {v for f in faces for v in f.verts}:
        p = rot @ v.co
        v.co = Vector((-p.x if mirror else p.x, p.y, p.z)) + Vector(centre)
    return faces

def clean():
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")   # lathe() strays

def done(name, mats):
    clean()
    return finish(name, material=mats)

# ---------------------------------------------------------------- long-handled tools

SHAFT_R = 0.0185

def d_handle(z0):
    """Shaft top splits into a Y of two wooden arms joined by a crossbar grip; steel ferrule."""
    for s in (-1, 1):
        wood(bent([(0, 0, z0), (s * 0.02, 0, z0 + 0.04), (s * 0.06, 0, z0 + 0.14), (s * 0.058, 0, z0 + 0.17)],
                  0.012, bend=0.03, sides=8))
    wood(new_faces(tube, [Vector((-0.075, 0, z0 + 0.168)), Vector((0.075, 0, z0 + 0.168))], 0.016, sides=10))
    paint(new_faces(lathe, [(0.0175, z0 - 0.03), (0.0205, z0 - 0.03), (0.0205, z0 + 0.01), (0.0175, z0 + 0.01),
                            (0.0175, z0 - 0.03)], segs=12), 1)

def shaft(z0, z1):
    wood(new_faces(tube, [Vector((0, 0, z0)), Vector((0, 0, z1))], SHAFT_R, sides=12))

def socket(z0, z1, r0=0.024, r1=0.02):
    """Steel socket (frog) the shaft sits in, with a rivet."""
    paint(new_faces(lathe, [(0, z0), (r0, z0), (r1, z1), (0, z1)], segs=12), 1)
    paint(along(new_faces(lathe, [(0, 0), (0.006, 0), (0.005, 0.004), (0, 0.005)], segs=6),
                (0, -r0 * 0.9 - 0.001, (z0 + z1) / 2 + 0.03), (0, -1, 0)), 1)

def shovel():
    begin()
    W, Hb, nu, nv = 0.118, 0.30, 10, 12
    grid = []
    for j in range(nv + 1):
        v = j / nv
        w = W * math.sin(min(v / 0.55, 1) * math.pi / 2) ** 0.75
        row = []
        for i in range(nu + 1):
            u = -1 + 2 * i / nu
            row.append(bm.verts.new((u * w, -0.035 * (1 - u * u) - 0.01 * v, 0.004 + v * Hb)))
        grid.append(row)
    sheet = []
    for a, b in zip(grid, grid[1:]):
        for i in range(nu):
            sheet.append(bm.faces.new((a[i], a[i + 1], b[i + 1], b[i])))
    bmesh.ops.remove_doubles(bm, verts=grid[0], dist=1e-5)              # the point
    sheet = [f for f in sheet if f.is_valid]
    res = bmesh.ops.solidify(bm, geom=sheet, thickness=0.003)
    blade = {f for f in bm.faces}
    uv_box(blade, TILE)
    paint(blade, 2)
    # top edge rolled into a tread, and the socket up the back
    paint(new_faces(tube, [Vector((-W, -0.01, Hb + 0.004)), Vector((W, -0.01, Hb + 0.004))], 0.005, sides=6), 2)
    socket(Hb - 0.08, Hb + 0.13)
    shaft(Hb + 0.1, 0.93)
    d_handle(0.93)
    return done("GardenShovel", [WOOD, "DarkSteel", "GalvSteel"])

def fork():
    begin()
    zt = 0.31
    xs = (-0.084, -0.028, 0.028, 0.084)
    for x in xs:                                                     # tines: square, tapering, curving forward a touch
        pts = [Vector((x * (1 - 0.04 * k / 5), -0.004 * k * k / 5, zt - zt * k / 5)) for k in range(6)]
        paint(new_faces(tube, pts, lambda t: 0.0075 - 0.0055 * t, sides=4), 1)
    paint(bent([(-0.092, 0, zt + 0.01), (-0.06, 0, zt + 0.05), (0.06, 0, zt + 0.05), (0.092, 0, zt + 0.01)],
               0.01, bend=0.04, sides=6), 1)
    socket(zt + 0.04, zt + 0.22, 0.022, 0.0195)
    shaft(zt + 0.2, 0.93)
    d_handle(0.93)
    return done("GardenFork", [WOOD, "DarkSteel"])

# ---------------------------------------------------------------- hose

def hose():
    begin()
    r, loops, per = 0.011, 8, 44
    pts = []
    for i in range(loops * per):
        t = i / per
        a = 2 * math.pi * t
        R = 0.24 + 0.025 * math.sin(1.3 * t + 0.5) + 0.01 * t
        c = Vector((0.03 * math.sin(0.7 * t), 0.025 * math.cos(0.45 * t), 0))
        lift = 0.045 * (1 + math.cos(a - 1.7 * t)) / 2 + 0.006 * t     # loops tilt this way and that
        pts.append(c + Vector((R * math.cos(a), R * 0.82 * math.sin(a), r + lift)))
    end = pts[-1]
    out = Vector((end.x, end.y, 0)).normalized()
    side = Vector((-out.y, out.x, 0))
    for k in range(1, 9):                                             # the tail runs off across the floor
        p = end + out * (0.06 * k) + side * (0.08 * math.sin(k / 3))
        p.z = r + max(0.0, end.z - r) * max(0.0, 1 - k / 3)
        pts.append(p)
    setmat(new_faces(tube, pts, r, sides=7), 0)
    d = (pts[-1] - pts[-2]).normalized()
    fit = new_faces(lathe, [(0, 0), (0.014, 0), (0.016, 0.01), (0.014, 0.02), (0.016, 0.03), (0.016, 0.045),
                            (0.011, 0.055), (0.009, 0.075), (0, 0.075)], segs=10)
    setmat(along(fit, pts[-1] - d * 0.01, d), 1)
    return done("GardenHose", ["HoseGreen", "HoseFitting"])

# ---------------------------------------------------------------- wheelbarrow

def rr(hx_, hy_, r, cy=0.0, n=4):
    pts = []
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx, cyy = sx * (hx_ - r), sy * (hy_ - r) + cy
        for k in range(n + 1):
            a = math.radians(a0 + 90 * k / n)
            pts.append((cx + r * math.cos(a), cyy + r * math.sin(a)))
    return pts

def loft(rings):
    vr = [[bm.verts.new((x, y, z)) for x, y in pts] for pts, z in rings]
    m = len(vr[0]); faces = []
    for a, b in zip(vr, vr[1:]):
        for k in range(m):
            faces.append(bm.faces.new((a[k], a[(k + 1) % m], b[(k + 1) % m], b[k])))
    faces.append(bm.faces.new(list(reversed(vr[0])))); faces.append(bm.faces.new(vr[-1]))
    for f in faces: f.smooth = True
    return set(faces)

def wheelbarrow():
    begin()
    zb, zt = 0.31, 0.62
    bot = lambda g: rr(0.21 + g, 0.29 + g, 0.07 + g, cy=0.08)
    top = lambda g: rr(0.36 + g, 0.50 + g, 0.12 + g, cy=-0.1)
    tray = loft([(bot(-0.02), zb), (bot(0), zb + 0.02), (top(0), zt), (top(-0.006), zt), (bot(-0.006), zb + 0.026)])
    uv_box(tray, TILE); paint(tray, 2)
    rim = [Vector((x, y, zt)) for x, y in top(0.004)]
    paint(new_faces(tube, rim, 0.011, sides=8, closed=True), 2)
    ax = Vector((0, -0.66, 0.17))
    for s in (-1, 1):
        frame = [(s * 0.056, ax.y, ax.z), (s * 0.15, -0.42, 0.27), (s * 0.2, -0.08, 0.295), (s * 0.24, 0.42, 0.38),
                 (s * 0.275, 0.86, 0.56)]
        paint(bent(frame, 0.014, bend=0.12, sides=10), 1)
        d = (Vector(frame[-1]) - Vector(frame[-2])).normalized()
        paint(new_faces(tube, [Vector(frame[-1]) - d * 0.13, Vector(frame[-1]) + d * 0.015], 0.019, sides=10), 3)
        paint(bent([(s * 0.205, 0.08, 0.31), (s * 0.23, 0.13, 0.014), (s * 0.23, 0.34, 0.014), (s * 0.225, 0.39, 0.36)],
                   0.012, bend=0.05, sides=8), 1)                               # leg
    paint(new_faces(tube, [Vector((-0.2, 0.1, 0.32)), Vector((0.2, 0.1, 0.32))], 0.01, sides=8), 1)
    tyre = [(0.115, -0.04), (0.15, -0.042), (0.168, -0.024), (0.17, 0.0), (0.168, 0.024), (0.15, 0.042),
            (0.115, 0.04), (0.115, -0.04)]
    x_axis(setmat(new_faces(lathe, tyre, segs=24), 3), ax)
    x_axis(paint(new_faces(lathe, [(0, -0.03), (0.117, -0.03), (0.117, 0.03), (0, 0.03)], segs=24), 1), ax)
    x_axis(paint(new_faces(lathe, [(0, -0.07), (0.011, -0.07), (0.011, 0.07), (0, 0.07)], segs=8), 1), ax)
    return done("Wheelbarrow", [WOOD, "DarkSteel", "GalvSteel", "Rubber"])

def beam_faces(a, b, w=0.025, t=0.005):
    a, b = Vector(a), Vector(b)
    d = (b - a).normalized(); s = d.cross(Vector((1, 0, 0))).normalized(); n = d.cross(s)
    c = [p + s * sx * w / 2 + n * nx * t / 2 for p in (a, b) for sx, nx in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    vs = [bm.verts.new(p) for p in c]
    fs = {bm.faces.new([vs[i] for i in q]) for q in
          ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))}
    uv_box(fs, TILE); return fs

# ---------------------------------------------------------------- watering can

def watering_can():
    begin()
    body = [(0, 0.004), (0.118, 0.004), (0.125, 0.012), (0.122, 0.022), (0.12, 0.128), (0.124, 0.134), (0.12, 0.14),
            (0.124, 0.146), (0.12, 0.152), (0.116, 0.248), (0.12, 0.256), (0.112, 0.264), (0.09, 0.284),
            (0.052, 0.296), (0.05, 0.302), (0.043, 0.302), (0.043, 0.27), (0, 0.27)]
    paint(new_faces(lathe, body, segs=28), 0)
    a, b = Vector((0, -0.105, 0.05)), Vector((0, -0.41, 0.31))
    paint(new_faces(tube, [a, b], lambda t: 0.021 - 0.009 * t, sides=10), 0)                   # spout
    d = (b - a).normalized()
    rose = [(0, 0), (0.013, 0), (0.024, 0.02), (0.036, 0.034), (0.038, 0.042), (0.034, 0.046), (0, 0.044)]
    paint(along(new_faces(lathe, rose, segs=14), b - d * 0.005, d), 0)
    paint(new_faces(tube, [Vector((0, -0.112, 0.235)), a.lerp(b, 0.62)], 0.004, sides=5), 0)    # brace
    paint(bent([(0, -0.07, 0.288), (0, -0.045, 0.40), (0, 0.06, 0.40), (0, 0.09, 0.276)], 0.009, bend=0.06,
               sides=8), 0)                                                                    # top handle
    paint(bent([(0, 0.116, 0.24), (0, 0.205, 0.265), (0, 0.215, 0.14), (0, 0.122, 0.075)], 0.008, bend=0.05,
               sides=8), 0)                                                                    # back handle
    return done("WateringCan", ["GalvSteel"])

# ---------------------------------------------------------------- crate and block (Parts / boxes)

def crate():
    P = fg.Parts(rng)
    L, W, H, t, slat = 0.56, 0.38, 0.30, 0.012, 0.082
    zs = [0.012 + slat / 2 + k * (slat + 0.022) for k in range(3)]
    for sy in (-1, 1):                                                   # long sides
        for z in zs:
            P.box((0, sy * (W / 2 - t / 2), z), (1, 0, 0), (0, 0, 1), L, slat, t)
    for sx in (-1, 1):                                                   # ends
        for z in zs:
            P.box((sx * (L / 2 - t / 2), 0, z), (0, 1, 0), (0, 0, 1), W - 2 * t, slat, t)
    post = 0.034
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.upright((sx * (L / 2 - t - post / 2), sy * (W / 2 - t - post / 2), 0), (1, 0, 0), post, post, H)
    for k in range(4):                                                   # bottom boards
        y = -W / 2 + t + 0.045 + k * (W - 2 * t - 0.09) / 3
        P.box((0, y, t / 2), (1, 0, 0), (0, 1, 0), L - 2 * t, 0.075, t)
    me = P.mesh("WoodenCrate"); me.materials.append(fg.wood_material())
    ob = bpy.data.objects.new("WoodenCrate", me); bpy.context.collection.objects.link(ob)
    print("WoodenCrate tris", sum(len(p.vertices) - 2 for p in me.polygons), "dims", tuple(round(v, 3) for v in ob.dimensions))
    return ob

def concrete_block():
    begin()
    L, W, H, wall = 0.39, 0.19, 0.19, 0.032
    fs = set()
    for sy in (-1, 1):
        fs |= box((-L / 2, sy * W / 2 - (wall if sy > 0 else 0), 0), (L / 2, sy * W / 2 + (0 if sy > 0 else wall), H),
                  bevel=0.004, segs=1)
    for x in (-L / 2 + wall / 2, 0, L / 2 - wall / 2):
        fs |= box((x - wall / 2, -W / 2 + wall, 0), (x + wall / 2, W / 2 - wall, H))
    uv_box(fs, 1.0)
    du, dv = rng.random(), rng.random()
    for f in fs:
        for l in f.loops: l[uvl].uv = (l[uvl].uv[0] + du, l[uvl].uv[1] + dv)
    return done("ConcreteBlock", ["BlockConcrete"])

PIECES = [shovel(), fork(), hose(), wheelbarrow(), watering_can(), crate(), concrete_block()]

os.makedirs(OUT_DIR, exist_ok=True)
path = os.path.join(OUT_DIR, "garden_set.blend")
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.file.make_paths_relative()
bpy.ops.wm.save_mainfile()
print("saved", path)

if os.environ.get("RENDER", "1") != "0":
    sc = bpy.context.scene
    lay = {"WateringCan": (-2.1, 0.1, 30), "Wheelbarrow": (-1.15, 0.1, -35), "GardenHose": (-0.1, -0.45, 0),
           "GardenShovel": (0.55, 0.3, 10), "GardenFork": (0.85, 0.35, -10), "WoodenCrate": (1.6, 0.4, 5),
           "ConcreteBlock": (1.75, -0.15, -20)}
    for n, (x, y, rz) in lay.items():
        ob = bpy.data.objects[n]; ob.location = (x, y, 0); ob.rotation_euler.z = math.radians(rz)
    g = bpy.data.meshes.new("G"); g.from_pydata([(-8, -6, 0), (8, -6, 0), (8, 6, 0), (-8, 6, 0)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("PreviewGround", g); sc.collection.objects.link(go)
    gm = bpy.data.materials.new("PreviewGrey"); gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.13, 0.13, 0.14, 1)
    g.materials.append(gm)
    sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", "SUN"))
    sun.data.energy = 3.2; sun.data.angle = math.radians(6)
    sun.rotation_euler = (math.radians(45), 0, math.radians(-25)); sc.collection.objects.link(sun)
    world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.52, 0.56, 1)
    cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
    sc.collection.objects.link(cam); sc.camera = cam
    tgt = bpy.data.objects.new("CamTarget", None); sc.collection.objects.link(tgt)
    c = cam.constraints.new("TRACK_TO"); c.target = tgt; c.track_axis = "TRACK_NEGATIVE_Z"; c.up_axis = "UP_Y"
    sc.render.engine = "CYCLES"; sc.cycles.samples = 32; sc.cycles.use_denoising = True
    os.makedirs(os.path.join(HERE, "render"), exist_ok=True)
    for fname, at, look, lens, res in (("garden_set.png", (0.0, -4.6, 1.9), (-0.15, 0.1, 0.35), 32, (1800, 900)),
                                       ("garden_set_close.png", (-1.0, -2.0, 1.1), (-1.3, 0.1, 0.3), 40, (1200, 900)),
                                       ("garden_set_can.png", (-2.6, -0.9, 0.55), (-2.15, 0.05, 0.2), 45, (1000, 800)),
                                       ("garden_set_right.png", (1.3, -1.6, 0.9), (1.25, 0.15, 0.35), 38, (1200, 900))):
        cam.location = at; tgt.location = look; cam.data.lens = lens
        sc.render.resolution_x, sc.render.resolution_y = res
        sc.render.filepath = os.path.join(HERE, "render", fname)
        bpy.ops.render.render(write_still=True)
print("GARDEN DONE")
