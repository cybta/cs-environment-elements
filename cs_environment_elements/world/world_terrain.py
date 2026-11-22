"""World terrain: the height field, ground splat weights, terrain/water meshes, the
boundary collider and the heightmap / splatmap files for a game engine.

Heights live on an N x N grid (row 0 = south edge, column 0 = west edge) covering the
whole map. Natural ground = rolling hills + the mountain rim round the edge + the
cedar mountain. Roads, plots and zones then pull the ground towards their own level
(the town is flat at TOWN_Z), the trail cuts a level bench into the mountain side, and
last the river bed and the lake are carved out below WATER_Z.
"""

import json
import math
import os
import struct
import zlib

import bpy
import numpy as np

from . import world_layout as wl

RIM_H = 108.0           # mountain rim height
RIVER_BED = -3.2
SLOPE_BANK = 0.45       # river / lake banks (rise per metre)


# --------------------------------------------------------------------------
# Noise
# --------------------------------------------------------------------------

def value_noise(X, Y, scale, seed):
    """Smooth value noise in [0, 1] with features about `scale` metres across."""
    rs = np.random.RandomState(seed & 0x7FFFFFFF)
    n = int(2 * wl.HALF / scale) + 3
    lat = rs.rand(n + 1, n + 1).astype(np.float32)
    gx = (X + wl.HALF) / scale
    gy = (Y + wl.HALF) / scale
    ix, iy = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - ix, gy - iy
    ix, iy = np.clip(ix, 0, n - 1), np.clip(iy, 0, n - 1)
    sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    a, b = lat[iy, ix], lat[iy, ix + 1]
    c, d = lat[iy + 1, ix], lat[iy + 1, ix + 1]
    return (a + (b - a) * sx) * (1 - sy) + (c + (d - c) * sx) * sy


def fbm(X, Y, scale, seed, octaves=4):
    total, amp, norm = 0.0, 1.0, 0.0
    for o in range(octaves):
        total = total + value_noise(X, Y, scale / 2 ** o, seed + 101 * o) * amp
        norm += amp
        amp *= 0.5
    return total / norm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


# --------------------------------------------------------------------------
# Height field
# --------------------------------------------------------------------------

class Terrain:
    def __init__(self, layout, res=1025, mesh_step=4.0):
        self.L = layout
        self.N = res
        self.step = 2 * wl.HALF / (res - 1)
        g = np.linspace(-wl.HALF, wl.HALF, res, dtype=np.float32)
        self.X, self.Y = np.meshgrid(g, g)
        self.mesh_step = mesh_step
        self.mesh_h = None

    # ---- grid helpers -----------------------------------------------------
    def _window(self, lo, hi):
        """Row/column slices of the grid covering the box lo..hi (x, y)."""
        j0 = max(0, int((lo[0] + wl.HALF) / self.step))
        j1 = min(self.N, int((hi[0] + wl.HALF) / self.step) + 2)
        i0 = max(0, int((lo[1] + wl.HALF) / self.step))
        i1 = min(self.N, int((hi[1] + wl.HALF) / self.step) + 2)
        return slice(i0, i1), slice(j0, j1)

    def _segments(self, poly, margin):
        """Yield (rows, cols, distance, t, k) for each segment k of the polyline, over the
        grid window round it."""
        for k in range(len(poly) - 1):
            a, b = poly[k], poly[k + 1]
            rows, cols = self._window(np.minimum(a, b) - margin, np.maximum(a, b) + margin)
            X, Y = self.X[rows, cols], self.Y[rows, cols]
            ab = b - a
            L2 = max(float(ab @ ab), 1e-9)
            t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0.0, 1.0)
            d = np.hypot(X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1]))
            yield rows, cols, d, t, k

    def poly_distance(self, poly, margin):
        out = np.full((self.N, self.N), np.inf, np.float32)
        for rows, cols, d, _, _ in self._segments(poly, margin):
            np.minimum(out[rows, cols], d, out=out[rows, cols])
        return out

    def box_distance(self, box):
        """Distance from every grid point to an oriented box (0 inside) -> (rows, cols, d)."""
        r = max(box.hw, box.hd) * 1.5 + 40
        rows, cols = self._window(box.c - r, box.c + r)
        dx = self.X[rows, cols] - box.c[0]
        dy = self.Y[rows, cols] - box.c[1]
        u = np.abs(dx * box.u[0] + dy * box.u[1]) - box.hw
        v = np.abs(dx * box.v[0] + dy * box.v[1]) - box.hd
        return rows, cols, np.hypot(np.maximum(u, 0), np.maximum(v, 0))

    # ---- build -------------------------------------------------------------
    def compute(self):
        L, X, Y, seed = self.L, self.X, self.Y, self.L.seed
        # Natural ground
        hills = 0.4 + fbm(X, Y, 260.0, seed + 1) ** 1.3 * 10.0       # never below the water
        d_edge = wl.HALF - wl.edge_r(X, Y)
        s = smoothstep(215.0, 5.0, d_edge)                 # long slopes the forest can climb
        ridge = 1.0 - np.abs(fbm(X, Y, 120.0, seed + 7, 3) - 0.5) * 2.0
        rim = RIM_H * s ** 1.2 * (0.7 + 0.6 * fbm(X, Y, 300.0, seed + 3, 3)) + 14.0 * ridge * s
        m = L.mountain_h(X, Y)
        mountain = m + 7.0 * (fbm(X, Y, 60.0, seed + 11, 3) - 0.5) * np.clip(m / 20.0, 0, 1)
        self.natural = (hills + np.maximum(rim, mountain) + 0.25 * np.minimum(rim, mountain)).astype(np.float32)

        # Flatten under roads, plots and zones
        mask = np.zeros_like(self.natural)
        target = np.zeros_like(self.natural)

        def blend(rows, cols, w, tgt):
            cur = mask[rows, cols]
            take = w > cur
            mask[rows, cols] = np.where(take, w, cur)
            target[rows, cols] = np.where(take, tgt, target[rows, cols])

        for road in L.roads:
            poly = road.loop_pts()
            if road.kind in ("NEW", "OLD"):
                core, fall = road.outer + 3.0, 26.0
            else:
                core, fall = road.outer + 2.5, 9.0          # a level bench wider than the path
            if road.kind == "TRAIL":
                hs = self.sample_natural(poly)          # the trail keeps the mountain's height
            for rows, cols, d, t, k in self._segments(poly, core + fall):
                w = smoothstep(core + fall, core, d)
                if road.kind == "TRAIL":
                    tgt = hs[k] + (hs[k + 1] - hs[k]) * t
                else:
                    tgt = np.full_like(d, wl.TOWN_Z)
                blend(rows, cols, w, tgt)
        for box in list(L.plots) + list(L.zones):
            summit = getattr(box, "kind", None) == "SUMMIT"
            core, fall = (box.hw, 12.0) if summit else (3.0, 24.0)
            rows, cols, d = self.box_distance(box)
            if summit:
                tgt = float(self.sample_natural(np.array([box.c]))[0])
            else:
                tgt = wl.TOWN_Z
            blend(rows, cols, smoothstep(core + fall, core, d), np.full_like(d, tgt))
        h = self.natural * (1 - mask) + target * mask

        # River and lake
        self.d_river = self.poly_distance(L.river, 160.0)
        e = np.maximum(self.d_river - L.river_hw, 0.0)
        carve = RIVER_BED + e * SLOPE_BANK + np.maximum(e - 12.0, 0) ** 1.6 * 0.05
        h = np.minimum(h, carve)
        q = L.lake_q(X, Y)
        self.lake_e = (q - 1.0) * min(L.lake[2], L.lake[3])        # metres from the shore (approx.)
        inside = wl.WATER_Z - 0.4 - 3.4 * (1 - np.clip(q, 0, 1) ** 2)
        beach = wl.WATER_Z - 0.4 + np.clip(self.lake_e, 0, 26) * 0.07 + np.maximum(self.lake_e - 26, 0) * 0.5
        h = np.minimum(h, np.where(q < 1.0, inside, beach))
        self.h = h.astype(np.float32)
        self.flat = mask
        self.slope_grid = self.slope().astype(np.float32)
        return self

    # ---- sampling ----------------------------------------------------------
    def _bilinear(self, grid, pts, step, n):
        pts = np.atleast_2d(np.asarray(pts, float))
        gx = np.clip((pts[:, 0] + wl.HALF) / step, 0, n - 1.0001)
        gy = np.clip((pts[:, 1] + wl.HALF) / step, 0, n - 1.0001)
        j, i = gx.astype(int), gy.astype(int)
        fx, fy = gx - j, gy - i
        return (grid[i, j] * (1 - fx) * (1 - fy) + grid[i, j + 1] * fx * (1 - fy) +
                grid[i + 1, j] * (1 - fx) * fy + grid[i + 1, j + 1] * fx * fy)

    def sample_natural(self, pts):
        return self._bilinear(self.natural, pts, self.step, self.N)

    def sample_fine(self, pts):
        return self._bilinear(self.h, pts, self.step, self.N)

    def sample(self, pts):
        """Height of the terrain *mesh* (what the eye sees), for placing things on it."""
        if self.mesh_h is None:
            return self.sample_fine(pts)
        return self._bilinear(self.mesh_h, pts, self.mesh_step, self.mesh_h.shape[0])

    def z(self, x, y):
        return float(self.sample([(x, y)])[0])

    def slope(self):
        gy, gx = np.gradient(self.h, self.step)
        return np.hypot(gx, gy)

    # ---- splat ---------------------------------------------------------------
    def splat(self):
        """(N, N, 4) weights: R dirt, G rock, B sand, A grass (they sum to 1)."""
        L, X, Y, seed = self.L, self.X, self.Y, self.L.seed
        h, sl = self.h, self.slope()
        n1 = fbm(X, Y, 40.0, seed + 21, 3)
        rock = smoothstep(0.8, 1.25, sl + (n1 - 0.5) * 0.5)
        rock = np.maximum(rock, smoothstep(112.0, 140.0, h + (n1 - 0.5) * 30))
        sand = np.where(self.lake_e < 30.0, smoothstep(1.2, -0.4, h - (n1 - 0.5)), 0.0)
        sand = np.maximum(sand, np.where(self.d_river < L.river_hw + 14, smoothstep(-0.2, -1.0, h), 0.0))
        dirt = np.zeros_like(h)
        for road in L.roads:
            if road.kind in ("OLD", "TRAIL", "PATH"):
                d = self.poly_distance(road.loop_pts(), 12.0)
                dirt = np.maximum(dirt, smoothstep(road.outer + 4.0 + n1 * 3, road.outer, d))
        for p in L.plots:
            if p.district == "POOR":
                rows, cols, d = self.box_distance(p)
                w = smoothstep(4.0, -2.0, d) * smoothstep(0.35, 0.65, fbm(X[rows, cols], Y[rows, cols], 9.0, seed + 5, 2))
                dirt[rows, cols] = np.maximum(dirt[rows, cols], w * 0.85)
        for z in L.zones:
            if z.kind == "PLAYGROUND" and z.extra.get("style") == "DIRT" or z.kind == "SUMMIT":
                rows, cols, d = self.box_distance(z)
                dirt[rows, cols] = np.maximum(dirt[rows, cols], smoothstep(5.0, -1.0, d))
        wild = (1 - self.flat) * smoothstep(0.62, 0.75, fbm(X, Y, 30.0, seed + 31, 3))       # forest floor
        dirt = np.maximum(dirt, wild * 0.6)
        rock = rock * (1 - sand)
        dirt = dirt * (1 - rock) * (1 - sand)
        grass = np.clip(1 - dirt - rock - sand, 0, 1)
        out = np.stack([dirt, rock, sand, grass], -1).astype(np.float32)
        return out / np.maximum(out.sum(-1, keepdims=True), 1e-6)


# --------------------------------------------------------------------------
# Blender objects
# --------------------------------------------------------------------------

def _grid_mesh(name, xs, ys, Z, uv_map=True):
    """A quad grid mesh over xs (columns) x ys (rows) with heights Z[row, col]."""
    ny, nx = Z.shape
    Xg, Yg = np.meshgrid(xs, ys)
    co = np.stack([Xg, Yg, Z], -1).reshape(-1, 3).astype(np.float32)
    idx = np.arange(nx * ny).reshape(ny, nx)
    quads = np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(co))
    me.vertices.foreach_set("co", co.ravel())
    me.loops.add(quads.size)
    me.loops.foreach_set("vertex_index", quads.ravel().astype(np.int32))
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", np.arange(0, quads.size, 4, dtype=np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(quads), 4, np.int32))
    if uv_map:
        uv = me.uv_layers.new(name="UVMap")
        lv = co[quads.ravel()]
        uvs = np.stack([(lv[:, 0] + wl.HALF) / (2 * wl.HALF), (lv[:, 1] + wl.HALF) / (2 * wl.HALF)], -1)
        uv.data.foreach_set("uv", uvs.ravel().astype(np.float32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    return me


def build_meshes(T, coll, mat_ground, mat_water, chunks=4):
    """Terrain as chunks x chunks objects (for culling), the water surface and the collider."""
    n = int(round(2 * wl.HALF / T.mesh_step)) + 1
    xs = np.linspace(-wl.HALF, wl.HALF, n)
    Xg, Yg = np.meshgrid(xs, xs)
    T.mesh_h = T.sample_fine(np.stack([Xg.ravel(), Yg.ravel()], 1)).reshape(n, n).astype(np.float32)
    T.mesh_step = 2 * wl.HALF / (n - 1)
    objs = []
    cuts = np.linspace(0, n - 1, chunks + 1).astype(int)
    for a in range(chunks):
        for b in range(chunks):
            r0, r1, c0, c1 = cuts[a], cuts[a + 1] + 1, cuts[b], cuts[b + 1] + 1
            name = f"Terrain_{a}{b}"
            me = _grid_mesh(name, xs[c0:c1], xs[r0:r1], T.mesh_h[r0:r1, c0:c1])
            me.materials.append(mat_ground)
            ob = bpy.data.objects.new(name, me)
            coll.objects.link(ob)
            ob["world_part"] = "terrain"
            objs.append(ob)

    # Water: every cell whose lowest corner is under the water line, flat at WATER_Z
    H = T.mesh_h
    low = np.minimum(np.minimum(H[:-1, :-1], H[:-1, 1:]), np.minimum(H[1:, :-1], H[1:, 1:]))
    wet = low < wl.WATER_Z + 0.05
    wet = wet | np.roll(wet, 1, 0) | np.roll(wet, -1, 0) | np.roll(wet, 1, 1) | np.roll(wet, -1, 1)
    rows, cols = np.nonzero(wet)
    verts, faces, vid = [], [], {}

    def v(i, j):
        key = (i, j)
        if key not in vid:
            vid[key] = len(verts)
            verts.append((xs[j], xs[i], wl.WATER_Z))
        return vid[key]

    for i, j in zip(rows, cols):
        faces.append((v(i, j), v(i, j + 1), v(i + 1, j + 1), v(i + 1, j)))
    me = bpy.data.meshes.new("Water")
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (co.x / 8.0, co.y / 8.0)
    me.materials.append(mat_water)
    water = bpy.data.objects.new("Water", me)
    coll.objects.link(water)
    water["world_part"] = "water"
    return objs, water


def build_collider(coll):
    """An invisible wall round the playable area (the rim is the visible edge)."""
    k = 256
    ang = np.linspace(0, 2 * math.pi, k, endpoint=False)
    c, s = np.cos(ang), np.sin(ang)
    r = wl.PLAY / (np.abs(c) ** 5 + np.abs(s) ** 5) ** 0.2
    verts = [(float(x), float(y), z) for x, y in zip(r * c, r * s) for z in (-30.0, 300.0)]
    faces = [(2 * i, 2 * ((i + 1) % k), 2 * ((i + 1) % k) + 1, 2 * i + 1) for i in range(k)]
    me = bpy.data.meshes.new("World_Boundary_Collider")
    me.from_pydata(verts, [], faces)
    ob = bpy.data.objects.new("World_Boundary_Collider", me)
    coll.objects.link(ob)
    ob.display_type = "WIRE"
    ob.hide_render = True
    ob.visible_camera = False
    ob["collider"] = True
    ob["world_part"] = "collider"
    return ob


# --------------------------------------------------------------------------
# Files for the game engine
# --------------------------------------------------------------------------

def _png(path, rows, width, height, color_type, bit_depth):
    """Write a PNG. `rows` = bytes of each row, top row first."""
    raw = b"".join(b"\x00" + r for r in rows)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(raw, 6)))
        f.write(chunk(b"IEND", b""))


def export_maps(T, folder, splat=None):
    """heightmap.png (16-bit grey) + heightmap.r16 (raw little-endian, Unity) + splatmap.png
    (RGBA: dirt, rock, sand, grass) + terrain.json with the scale. North is the top row."""
    os.makedirs(folder, exist_ok=True)
    h = T.h
    lo, hi = float(h.min()), float(h.max())
    q = np.round((h - lo) / max(hi - lo, 1e-6) * 65535).astype(np.uint16)[::-1]
    n = T.N
    _png(os.path.join(folder, "heightmap.png"), [r.astype(">u2").tobytes() for r in q], n, n, 0, 16)
    q.astype("<u2").tofile(os.path.join(folder, "heightmap.r16"))
    files = ["heightmap.png", "heightmap.r16"]
    if splat is not None:
        s8 = np.round(np.clip(splat, 0, 1) * 255).astype(np.uint8)[::-1]
        _png(os.path.join(folder, "splatmap.png"), [r.tobytes() for r in s8], n, n, 6, 8)
        files.append("splatmap.png")
    info = {
        "size_m": 2 * wl.HALF, "resolution": n, "metres_per_pixel": T.step,
        "height_min_m": lo, "height_max_m": hi, "water_level_m": wl.WATER_Z,
        "origin": "map centre is (0, 0); X east, Y north (Blender), Z up",
        "heightmap": "16-bit, 0 = height_min_m, 65535 = height_max_m, top row = north",
        "splatmap": "RGBA weights: R dirt, G rock, B sand, A grass",
        "boundary": f"superellipse |x|^5 + |y|^5 = {wl.PLAY}^5 (invisible wall)",
    }
    with open(os.path.join(folder, "terrain.json"), "w") as f:
        json.dump(info, f, indent=2)
    files.append("terrain.json")
    return files


def splat_image(splat, name="World_Splatmap"):
    """The splat weights as a packed Blender image, for the terrain material."""
    n = splat.shape[0]
    img = bpy.data.images.get(name)
    if img is not None and tuple(img.size) != (n, n):
        bpy.data.images.remove(img)
        img = None
    if img is None:
        img = bpy.data.images.new(name, n, n, alpha=True, float_buffer=False)
    img.colorspace_settings.name = "Non-Color"
    img.alpha_mode = "CHANNEL_PACKED"
    img.pixels.foreach_set(splat.astype(np.float32).ravel())
    img.pack()
    return img
