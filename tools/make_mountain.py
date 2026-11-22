"""Model a stand-alone mountain with a walking path, as a game asset.

    blender -b --factory-startup --python tools/make_mountain.py -- [seed] [out_folder]

About 250 m across (the foot wanders between 235 and 256 m) and 100 m high,
with spurs, gullies and a small flat summit. The path climbs at a steady grade from the
foot to the summit: each step is placed where the ground has exactly the path's next
height, so it follows the mountain's own folds instead of a drawn spiral. Then a level
bench is cut into the slope under it.

Writes <out>/mountain_250m.blend (textures packed), mountain_250m.fbx and textures/:
    Mountain_LOD0/1/2        ground, 1.5 / 3 / 6 m grid
    Mountain_Path_LOD0/1     the path surface, 2.6 m wide, sitting on the bench
The ground has a "Splat" colour attribute (R dirt, G rock), used by the material and
exported as vertex colour so a game shader can blend the same textures.
"""

import math
import os
import shutil
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SEED = int(ARGS[0]) if ARGS else 7
OUT = ARGS[1] if len(ARGS) > 1 else r"C:\cybta\carpentry simulator\ref\3D Models\nature\mountain_250m"

R = 128.0               # radius of the foot (wanders 0.92-1.0 of this: ~250 m across)
TOP = 100.0             # summit plateau height
PLATEAU = 8.0           # summit plateau radius
GRADE = 0.13            # path rise per metre
PATH_HW = 1.3           # half width of the path
FINE = 0.5              # working grid (m)
LODS = (1.5, 3.0, 6.0)  # ground grid per LOD (m)

TEX = {
    "grass": os.path.join(HERE, "..", "cs_environment_elements", "core", "assets", "neighborhood", "world_grass_%s.jpg"),
    "dirt": os.path.join(HERE, "..", "cs_environment_elements", "core", "assets", "neighborhood", "world_dirt_%s.jpg"),
    "gravel": os.path.join(HERE, "..", "cs_environment_elements", "core", "assets", "neighborhood", "world_gravel_%s.jpg"),
}
ROCK_DIR = r"C:\cybta\blender-plugins\cs-tree-generator\treegen\textures\rocks\marble_cliff_05_1k"


# --------------------------------------------------------------------------
# Noise and the natural shape
# --------------------------------------------------------------------------

class Noise:
    def __init__(self, seed):
        self.lat = np.random.RandomState(seed).rand(256, 256).astype(np.float64)

    def value(self, x, y):
        ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - ix, y - iy
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        L = self.lat
        a, b = L[iy % 256, ix % 256], L[iy % 256, (ix + 1) % 256]
        c, d = L[(iy + 1) % 256, ix % 256], L[(iy + 1) % 256, (ix + 1) % 256]
        return (a + (b - a) * sx) * (1 - sy) + (c + (d - c) * sx) * sy

    def fbm(self, x, y, octaves=4):
        t, amp, norm = 0.0, 1.0, 0.0
        for o in range(octaves):
            t = t + self.value(x * 2 ** o + 17 * o, y * 2 ** o + 31 * o) * amp
            norm += amp
            amp *= 0.5
        return t / norm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Mountain:
    def __init__(self, seed):
        self.n = Noise(seed)
        self.k = 1.0
        g = np.arange(-R, R + FINE, FINE)
        X, Y = np.meshgrid(g, g)
        self.k = (TOP + 3.0) / self.natural(X, Y).max()    # peak a little over the plateau

    def foot(self, th):
        c, s = np.cos(th), np.sin(th)
        return R * (0.92 + 0.08 * self.n.fbm(c * 1.6 + 40, s * 1.6 + 40, 3))

    def natural(self, x, y):
        n = self.n
        # warp the plan so the mountain is not round and its peak is off centre
        wx = x + 16.0 * (n.fbm(x / 90 + 3, y / 90 + 3, 3) - 0.5) * 2
        wy = y + 16.0 * (n.fbm(x / 90 + 50, y / 90 + 50, 3) - 0.5) * 2
        r = np.hypot(wx, wy)
        u = np.clip(r / self.foot(np.arctan2(wy, wx)), 0.0, 1.0)
        # gentle top and foot, steep middle
        body = (np.exp(-3.2 * u * u) - math.exp(-3.2)) / (1 - math.exp(-3.2))
        ridge = 1.0 - np.abs(2.0 * n.fbm(wx / 38 + 9, wy / 38 + 3, 4) - 1.0)     # ridges and gullies
        lumps = n.fbm(x / 16 + 70, y / 16 + 70, 3) - 0.5
        side = np.sin(math.pi * u)
        h = TOP * body + 15.0 * (ridge - 0.5) * 2 * side + 5.0 * lumps * side
        return np.maximum(h, 0.0) * smoothstep(1.0, 0.95, u) * self.k

    def solve_r(self, th, z):
        """Distance from the centre, along direction th, where the ground is z high
        (the outermost such point)."""
        rs = np.arange(R + 2, 0.0, -0.25)
        hs = self.natural(rs * math.cos(th), rs * math.sin(th))
        i = int(np.argmax(hs >= z))
        if hs[i] < z:
            return 0.0
        if i == 0:
            return float(rs[0])
        t = (z - hs[i - 1]) / max(hs[i] - hs[i - 1], 1e-9)
        return float(rs[i - 1] + (rs[i] - rs[i - 1]) * t)


# --------------------------------------------------------------------------
# The path
# --------------------------------------------------------------------------

def trace_path(m, start_angle):
    th = start_angle
    z = 0.25
    r = m.solve_r(th, z)
    pts = [(r * math.cos(th), r * math.sin(th), z)]
    step = 1.5
    while z < TOP - 1.2:
        zn = z + GRADE * step
        dth = step / max(r, 4.0)
        for _ in range(4):
            rn = m.solve_r(th + dth, zn)
            p = (rn * math.cos(th + dth), rn * math.sin(th + dth))
            dist = math.hypot(p[0] - pts[-1][0], p[1] - pts[-1][1])
            if dist < 1e-3:
                dth *= 2
                continue
            dth *= min(3.0, max(0.3, step / dist))
        rn = m.solve_r(th + dth, zn)
        th, z, r = th + dth, zn, rn
        pts.append((r * math.cos(th), r * math.sin(th), z))
        if r < PLATEAU + 2.0:
            break
    # last few metres straight onto the plateau
    x, y, z = pts[-1]
    d = math.hypot(x, y)
    if d > PLATEAU * 0.6:
        for k in range(1, 4):
            f = 1 - k / 3 * (1 - PLATEAU * 0.6 / d)
            pts.append((x * f, y * f, z + (TOP - z) * k / 3))
    P = np.array(pts)
    # gentle smoothing of the plan (the heights already climb evenly)
    for _ in range(12):
        P[1:-1, :2] = 0.25 * P[:-2, :2] + 0.5 * P[1:-1, :2] + 0.25 * P[2:, :2]
    return P


# --------------------------------------------------------------------------
# Ground: bench, plateau, splat
# --------------------------------------------------------------------------

def ground(m, path):
    g = np.arange(-R - 4, R + 4 + FINE, FINE)
    X, Y = np.meshgrid(g, g)
    H = m.natural(X, Y)
    best = np.full(H.shape, np.inf)
    target = np.zeros_like(H)
    margin = PATH_HW + 7.0
    for k in range(len(path) - 1):
        a, b = path[k], path[k + 1]
        lo = np.minimum(a[:2], b[:2]) - margin
        hi = np.maximum(a[:2], b[:2]) + margin
        j0, j1 = np.searchsorted(g, lo[0]), np.searchsorted(g, hi[0]) + 1
        i0, i1 = np.searchsorted(g, lo[1]), np.searchsorted(g, hi[1]) + 1
        x, y = X[i0:i1, j0:j1], Y[i0:i1, j0:j1]
        ab = b[:2] - a[:2]
        t = np.clip(((x - a[0]) * ab[0] + (y - a[1]) * ab[1]) / max(ab @ ab, 1e-9), 0, 1)
        d = np.hypot(x - (a[0] + t * ab[0]), y - (a[1] + t * ab[1]))
        take = d < best[i0:i1, j0:j1]
        best[i0:i1, j0:j1] = np.where(take, d, best[i0:i1, j0:j1])
        target[i0:i1, j0:j1] = np.where(take, a[2] + (b[2] - a[2]) * t, target[i0:i1, j0:j1])
    w = smoothstep(PATH_HW + 6.0, PATH_HW + 1.0, best)
    H = H * (1 - w) + target * w
    r = np.hypot(X, Y)
    w = smoothstep(PLATEAU + 7.0, PLATEAU, r)
    H = H * (1 - w) + TOP * w

    gy, gx = np.gradient(H, FINE)
    slope = np.hypot(gx, gy)
    n = m.n.fbm(X / 6 + 100, Y / 6 + 100, 3)
    rock = smoothstep(1.0, 1.45, slope + (n - 0.5) * 0.5)
    dirt = np.maximum(smoothstep(PATH_HW + 2.5, PATH_HW + 0.3, best), smoothstep(PLATEAU + 3.0, PLATEAU - 1.0, r))
    dirt = np.maximum(dirt, smoothstep(0.7, 0.8, m.n.fbm(X / 14 + 5, Y / 14 + 5, 3)) * 0.7)
    rock *= 1 - dirt
    return g, H, rock, dirt


def sample(g, A, x, y):
    fx = np.clip((x - g[0]) / FINE, 0, len(g) - 1.001)
    fy = np.clip((y - g[0]) / FINE, 0, len(g) - 1.001)
    j, i = fx.astype(int), fy.astype(int)
    tx, ty = fx - j, fy - i
    return (A[i, j] * (1 - tx) * (1 - ty) + A[i, j + 1] * tx * (1 - ty) +
            A[i + 1, j] * (1 - tx) * ty + A[i + 1, j + 1] * tx * ty)


# --------------------------------------------------------------------------
# Meshes
# --------------------------------------------------------------------------

def ground_mesh(name, g, H, rock, dirt, m, step, mat):
    xs = np.arange(-R - 3, R + 3 + step, step)
    X, Y = np.meshgrid(xs, xs)
    Z = sample(g, H, X, Y)
    n = len(xs)
    idx = np.arange(n * n).reshape(n, n)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    zf = Z.ravel()
    keep = zf[quads].max(1) > 0.02                  # drop the flat ground round the foot
    quads = quads[keep]
    used = np.unique(quads)
    remap = np.full(n * n, -1)
    remap[used] = np.arange(len(used))
    co = np.stack([X.ravel()[used], Y.ravel()[used], np.maximum(zf[used], 0.0)], 1)
    quads = remap[quads]
    me = bpy.data.meshes.new(name)
    me.from_pydata(co.tolist(), [], quads.tolist())
    uv = me.uv_layers.new(name="UVMap")
    loops = np.empty(len(me.loops), int)
    me.loops.foreach_get("vertex_index", loops)
    uv.data.foreach_set("uv", co[loops][:, :2].ravel().astype(np.float32))      # 1 UV = 1 m
    col = me.color_attributes.new("Splat", "FLOAT_COLOR", "POINT")
    rk = sample(g, rock, co[:, 0], co[:, 1])
    dt = sample(g, dirt, co[:, 0], co[:, 1])
    rgba = np.stack([dt, rk, np.zeros_like(dt), np.ones_like(dt)], 1).astype(np.float32)
    col.data.foreach_set("color", rgba.ravel())
    me.shade_smooth()
    me.materials.append(mat)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def path_mesh(name, path, g, H, step, mat):
    P = path
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P[:, :2], axis=0), axis=1))])
    t = np.arange(0, s[-1], step)
    t = np.append(t, s[-1])
    pts = np.stack([np.interp(t, s, P[:, 0]), np.interp(t, s, P[:, 1])], 1)
    d = np.gradient(pts, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    verts, faces, uvs = [], [], []
    for i, p in enumerate(pts):
        for side in (-1, 1):
            q = p + nrm[i] * side * PATH_HW
            verts.append((q[0], q[1], float(sample(g, H, q[0], q[1])) + 0.06))
    for i in range(len(pts) - 1):
        a = 2 * i
        faces.append((a, a + 2, a + 3, a + 1))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            uv.data[li].uv = ((vi % 2) * 2 * PATH_HW / 4.0, t[vi // 2] / 4.0)    # 4 m repeats
    me.shade_smooth()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def image(path, colour):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    return img


def layer_files():
    rock = [os.path.join(ROCK_DIR, "marble_cliff_05_%s_1k.%s" % (k, e))
            for k, e in (("diff", "jpg"), ("nor_gl", "exr"), ("rough", "exr"))]
    return {"grass": ([TEX["grass"] % k for k in ("diff", "nor", "rough")], 4.0),
            "rock": (rock, 8.0),
            "dirt": ([TEX["dirt"] % k for k in ("diff", "nor", "rough")], 3.0)}


def ground_material():
    mat = bpy.data.materials.new("Mountain_Ground")
    mat.use_nodes = True
    nt = mat.node_tree
    N, link = nt.nodes, nt.links.new
    bsdf = N["Principled BSDF"]
    uv = N.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    splat = N.new("ShaderNodeVertexColor")
    splat.layer_name = "Splat"
    sep = N.new("ShaderNodeSeparateColor")
    link(splat.outputs["Color"], sep.inputs["Color"])
    obj_co = N.new("ShaderNodeTexCoord")
    layers = {}
    for key, (files, tile) in layer_files().items():
        mp = N.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / tile, 1 / tile, 1 / tile)
        # rock is projected from all sides (no stretching on cliffs); a game shader would
        # use triplanar mapping for it too. The other layers use the UVs (1 UV = 1 m).
        link(obj_co.outputs["Object"] if key == "rock" else uv.outputs["UV"], mp.inputs["Vector"])
        outs = []
        for f, colour in zip(files, (True, False, False)):
            node = N.new("ShaderNodeTexImage")
            node.image = image(f, colour)
            if key == "rock":
                node.projection, node.projection_blend = "BOX", 0.3
            link(mp.outputs["Vector"], node.inputs["Vector"])
            outs.append(node.outputs["Color"])
        if key == "rock":                       # the marble photo is very bright: weather it down
            hsv = N.new("ShaderNodeHueSaturation")
            hsv.inputs["Value"].default_value = 0.72
            hsv.inputs["Saturation"].default_value = 0.85
            link(outs[0], hsv.inputs["Color"])
            outs[0] = hsv.outputs["Color"]
        layers[key] = outs

    def mix(a, b, fac):
        m = N.new("ShaderNodeMix")
        m.data_type = "RGBA"
        ins = {s.identifier: s for s in m.inputs}
        link(fac, ins["Factor_Float"])
        link(a, ins["A_Color"])
        link(b, ins["B_Color"])
        return next(s for s in m.outputs if s.identifier == "Result_Color")

    def blend(k):
        return mix(mix(layers["grass"][k], layers["rock"][k], sep.outputs["Green"]), layers["dirt"][k], sep.outputs["Red"])

    link(blend(0), bsdf.inputs["Base Color"])
    link(blend(2), bsdf.inputs["Roughness"])
    nm = N.new("ShaderNodeNormalMap")
    nm.inputs["Strength"].default_value = 0.6
    link(blend(1), nm.inputs["Color"])
    link(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def path_material():
    mat = bpy.data.materials.new("Mountain_Path")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    for k, sock, colour in (("diff", "Base Color", True), ("rough", "Roughness", False)):
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = image(TEX["gravel"] % k, colour)
        nt.links.new(node.outputs["Color"], bsdf.inputs[sock])
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = image(TEX["gravel"] % "nor", False)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(node.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# --------------------------------------------------------------------------

def main():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    m = Mountain(SEED)
    start = np.random.RandomState(SEED).uniform(0, 2 * math.pi)
    path = trace_path(m, start)
    g, H, rock, dirt = ground(m, path)
    gm, pm = ground_material(), path_material()
    obs = [ground_mesh("Mountain_LOD%d" % i, g, H, rock, dirt, m, st, gm) for i, st in enumerate(LODS)]
    obs += [path_mesh("Mountain_Path_LOD0", path, g, H, 1.5, pm), path_mesh("Mountain_Path_LOD1", path, g, H, 5.0, pm)]
    length = float(np.linalg.norm(np.diff(path[:, :2], axis=0), axis=1).sum())
    for ob in obs:
        n = sum(len(p.vertices) - 2 for p in ob.data.polygons)
        print("%-22s %7d tris" % (ob.name, n))
    print("height %.1f m, foot %.0f-%.0f m across, path %.0f m long, %.1f%% grade"
          % (H.max(), 2 * m.foot(np.linspace(0, 6.28, 64)).min(), 2 * m.foot(np.linspace(0, 6.28, 64)).max(),
             length, 100 * (path[-1, 2] - path[0, 2]) / length))

    os.makedirs(os.path.join(OUT, "textures"), exist_ok=True)
    for img in bpy.data.images:
        if img.filepath:
            shutil.copy(bpy.path.abspath(img.filepath), os.path.join(OUT, "textures"))
    for ob in obs:
        ob.select_set(True)
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "mountain_250m.fbx"), use_selection=True,
                             object_types={"MESH"}, mesh_smooth_type="FACE", colors_type="LINEAR",
                             apply_scale_options="FBX_SCALE_ALL", path_mode="STRIP")
    for ob in obs:                                # show LOD0 in the .blend
        if ob.name.endswith(("LOD1", "LOD2")):
            ob.hide_viewport = ob.hide_render = True
    for img in bpy.data.images:
        if img.filepath:
            img.pack()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "mountain_250m.blend"))


main()
