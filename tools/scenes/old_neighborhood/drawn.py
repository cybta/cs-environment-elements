"""The user's drawn plan (read_old_neighborhood_drawing.py -> out/old_neighborhood_drawn.json + the drawing
itself, out/old_neighborhood_Edit.png): lots, houses, gates, the dirt road mask, and the road surface mesh.

Sheet pixels <-> world (Blender metres): x = x0 + px / S, y = y1 - py / S (out/old_neighborhood_roads.json).
"""
import math

import bmesh
import bpy
import numpy as np

from .layout import polys_overlap  # noqa: F401  (re-exported for the builders)

STREET = 6.5                    # fence to fence across a street (user: 6 - 7 m)


def _rgb(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return np.round(px.reshape(h, w, 4)[::-1, :, :3] * 255).astype(np.int16)      # row 0 = top


def inside(pts, poly):
    """Even-odd point-in-polygon for many points (n, 2) -> (n,) bool."""
    pts = np.atleast_2d(pts)
    x, y = pts[:, 0], pts[:, 1]
    res = np.zeros(len(pts), bool)
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[i - 1]
        cross = ((y0 > y) != (y1 > y)) & (x < (x1 - x0) * (y - y0) / ((y1 - y0) or 1e-12) + x0)
        res ^= cross
    return res


def _dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


class Plan:
    def __init__(self, data, mapping, sheet_png):
        self.data = data
        self.S, self.x0, self.y1 = mapping["px_per_m"], mapping["x0"], mapping["y1"]
        rgb = _rgb(sheet_png)
        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        dirt = (abs(r - 145) <= 6) & (abs(g - 135) <= 6) & (abs(b - 125) <= 6)
        grey = (abs(r - 128) <= 3) & (abs(g - 128) <= 3) & (abs(b - 128) <= 3)
        H, W = dirt.shape
        yy, xx = np.mgrid[0:H, 0:W]
        # the old grey road survives only as the road to the bridge (east of the quarter's junction)
        bridge = grey & (xx > 1180) & (yy < 620)
        dirt = _dilate(dirt, 4)                                    # close the holes the labels left
        dirt = ~_dilate(~dirt, 4)
        self.dirt, self.bridge = dirt, bridge
        self.road = dirt | bridge
        self.lots = {L["lot"]: L for L in data["lots"]}
        for L in self.lots.values():
            L["outline"] = [tuple(p) for p in L["outline"]]
        self.houses = {h["lot"]: h for h in data["houses"]}
        # road = road surface that is not inside a lot (inside a lot it's that lot's driveway)
        world_px = self.to_world(np.stack([xx[::2, ::2].ravel() + 0.5, yy[::2, ::2].ravel() + 0.5], -1))
        in_lot = np.zeros(len(world_px), bool)
        for L in self.lots.values():
            in_lot |= inside(world_px, L["outline"])
        on_road = self.road[::2, ::2].ravel() & ~in_lot
        self.road_pts = world_px[on_road]                         # 25 cm spacing
        self.road_near = _dilate(self.road, int(round(0.6 * self.S)))

    # ------------------------------------------------------------ coordinates
    def to_world(self, px):
        px = np.asarray(px, float)
        return np.stack([self.x0 + px[..., 0] / self.S, self.y1 - px[..., 1] / self.S], -1)

    def to_px(self, pts):
        pts = np.atleast_2d(np.asarray(pts, float))
        return np.stack([(pts[:, 0] - self.x0) * self.S, (self.y1 - pts[:, 1]) * self.S], -1)

    def _sample(self, m, pts):
        p = self.to_px(pts)
        H, W = m.shape
        c = np.clip(p[:, 0].astype(int), 0, W - 1)
        r = np.clip(p[:, 1].astype(int), 0, H - 1)
        return m[r, c]

    def on_road(self, pts):
        return self._sample(self.road, pts)

    def near_road(self, pts):
        """Within ~60 cm of any road / driveway surface."""
        return self._sample(self.road_near, pts)

    def road_dist(self, p):
        d = self.road_pts - np.asarray(p, float)[None]
        k = int(np.argmin((d * d).sum(1)))
        return float(np.sqrt((d[k] ** 2).sum())), self.road_pts[k]

    # ------------------------------------------------------------ fences toward the road
    def _street_edges(self, n):
        """Outward unit normals of lot n's edges that face a road (road within 3 m outside), by edge index."""
        poly = self.lots[n]["outline"]
        shared = {s["side"] for s in self.lots[n]["shared"]}
        out = {}
        for i in range(len(poly)):
            if i + 1 in shared:
                continue
            a, b = np.array(poly[i]), np.array(poly[(i + 1) % len(poly)])
            ln = np.linalg.norm(b - a)
            if ln < 2.0:
                continue
            t = (b - a) / ln
            nrm = np.array([-t[1], t[0]])
            mid = (a + b) / 2
            if inside(mid + nrm * 0.3, poly)[0]:
                nrm = -nrm
            probe = np.array([mid + nrm * s for s in np.arange(0.2, 3.0, 0.2)])
            if not self.on_road(probe).any():
                continue
            across = self._ray_hit(mid, nrm, {n})                # a street: a fence faces it from across
            if across is not None and across < 16.0:
                out[i] = nrm
        return out

    def _ray_hit(self, o, d, exclude, facing=0.75):
        """Distance along d from o to the first fence of a lot not in `exclude`, or None. A fence hit at a
        slant (|cos| < `facing` between the ray and that fence's normal: across a junction) counts as None."""
        best, best_cos = None, 1.0
        for m, L in self.lots.items():
            if m in exclude:
                continue
            poly = L["outline"]
            for i in range(len(poly)):
                a, b = np.array(poly[i]), np.array(poly[(i + 1) % len(poly)])
                e = b - a
                den = d[0] * e[1] - d[1] * e[0]
                if abs(den) < 1e-9:
                    continue
                w = a - o
                t = (w[0] * e[1] - w[1] * e[0]) / den
                u = (w[0] * d[1] - w[1] * d[0]) / den
                if t > 0.05 and 0 <= u <= 1 and (best is None or t < best):
                    best = t
                    best_cos = abs(e[0] * d[1] - e[1] * d[0]) / (np.linalg.norm(e) * np.linalg.norm(d) or 1)
        return best if best is not None and best_cos >= facing else None

    def push_fences(self, target=STREET, max_move=3.5, log=print):
        """Street-facing fences move toward the road until the fences either side of a street are about
        `target` m apart (user: 6 - 7 m fence to fence; the dirt may end up inside the lots). Each front corner
        looks straight across the street; both sides move half the extra, so they meet at `target`.
        Shared corners move once for both lots; corners facing open ground (park, junctions) stay."""
        groups = {}
        for n, L in self.lots.items():
            for i, p in enumerate(L["outline"]):
                groups.setdefault((round(p[0], 2), round(p[1], 2)), []).append((n, i))
        facing = {n: self._street_edges(n) for n in self.lots}
        corners = []                                           # (members, outward normal, drawn position)
        for key, members in groups.items():
            nrms = []
            for n, i in members:
                k = len(self.lots[n]["outline"])
                for e in (i, (i - 1) % k):                     # the two edges that meet at this corner
                    if e in facing[n]:
                        nrms.append(facing[n][e])
            if not nrms:
                continue
            nrm = np.mean(nrms, axis=0)
            nrm /= np.linalg.norm(nrm) or 1
            corners.append((members, nrm, np.array(key)))

        def across(members, nrm):
            n, i = members[0]
            p = np.array(self.lots[n]["outline"][i])
            return p, self._ray_hit(p, nrm, {m for m, _ in members})

        lo, hi = target - 0.5, target + 0.5                    # 6 - 7 m
        moved = set()
        for _ in range(8):                                     # both sides move, so a few damped passes
            changed = False
            for k, (members, nrm, p0) in enumerate(corners):
                p, D = across(members, nrm)
                if D is None or D >= 16.0 or lo <= D <= hi:
                    continue
                if D < lo and k not in moved:
                    continue                                   # drawn narrower than that: leave it
                step = (D - target) / 2 * 0.8
                done = float(np.dot(p - p0, nrm))
                new_done = min(max(done + step, 0.0), max_move)   # never behind the drawn line
                if abs(new_done - done) < 0.02:
                    continue
                new = p0 + nrm * new_done
                for n, i in members:
                    self.lots[n]["outline"][i] = tuple(new)
                moved.add(k)
                changed = True
            if not changed:
                break
        after = []
        for k in sorted(moved):
            members, nrm, p0 = corners[k]
            p, D = across(members, nrm)
            if D is None or D >= 16:
                continue
            after.append(D)
            if not lo - 0.3 <= D <= hi + 0.3:
                log("  corner of lots %s: %.1f m across, moved %.1f m" % (
                    sorted({n for n, _ in members}), D, float(np.dot(p - p0, nrm))))
        after.sort()
        if after:
            log("fences: %d corners pushed toward the road; fence to fence now %.1f - %.1f m (median %.1f)"
                % (len(moved), after[0], after[-1], after[len(after) // 2]))
        else:
            log("fences: no corners pushed")

    # ------------------------------------------------------------ the road surface
    def road_mesh(self, terrain, name, mat, coll, uv_scale, mask=None, cell=0.5, lift=0.05):
        """Terrain-following quads where the drawn road is (cells of `cell` m), with the outline smoothed."""
        m = self.road if mask is None else mask
        k = max(1, int(round(cell * self.S)))
        H, W = m.shape
        h2, w2 = H // k, W // k
        frac = m[:h2 * k, :w2 * k].reshape(h2, k, w2, k).mean((1, 3))
        keep = frac >= 0.5
        rows, cols = np.nonzero(keep)
        if not len(rows):
            return None
        bm = bmesh.new()
        uvl = bm.loops.layers.uv.new("UVMap")
        verts = {}

        def vert(r, c):
            v = verts.get((r, c))
            if v is None:
                x, y = self.to_world(np.array([c * k, r * k], float))
                v = bm.verts.new((x, y, 0.0))
                verts[(r, c)] = v
            return v

        for r, c in zip(rows, cols):
            bm.faces.new((vert(r + 1, c), vert(r + 1, c + 1), vert(r, c + 1), vert(r, c)))
        # smooth the staircase outline: boundary verts move toward their boundary neighbours
        for _ in range(4):
            new = {}
            for v in bm.verts:
                if not v.is_boundary:
                    continue
                nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
                if len(nb) == 2:
                    new[v] = (v.co * 2 + nb[0].co + nb[1].co) / 4
            for v, co in new.items():
                v.co = co
        pts = np.array([v.co[:2] for v in bm.verts])
        z = terrain.height(pts) + lift
        for v, zz in zip(bm.verts, z):
            v.co.z = float(zz)
        for f in bm.faces:
            for lp in f.loops:
                lp[uvl].uv = (lp.vert.co.x * uv_scale, lp.vert.co.y * uv_scale)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for p in me.polygons:
            p.use_smooth = True
        me.materials.append(mat)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        return ob


class DrawnLot:
    """A drawn lot in the frame the yard builder (lots.LotBuilder) works in: origin at the gate on the fence,
    d into the lot, u = d turned -90 deg; wl / wr / v0 / v1 = the lot's bounding box in that frame."""

    def __init__(self, num, rec, house):
        self.idx = num
        self.poly = np.array(rec["outline"], float)
        self.rec, self.house_rec = rec, house
        self.infill = False
        self.hero = False
        self.ok = True
        self.skip = {s["side"] for s in rec["shared"] if s["with_lot"] < num}
        gate = rec["gates"][0] if rec["gates"] else None
        n = len(self.poly)
        if gate:
            a, b = self.poly[gate["side"] - 1], self.poly[gate["side"] % n]
            tm = (gate["t0"] + gate["t1"]) / 2
            self.gate = gate
        else:                                   # no gate found: the edge nearest the house door
            door = np.array(house["door"])
            i = min(range(n), key=lambda i: np.linalg.norm((self.poly[i] + self.poly[(i + 1) % n]) / 2 - door))
            a, b, tm = self.poly[i], self.poly[(i + 1) % n], 0.5
            self.gate = dict(side=i + 1, t0=0.4, t1=0.6, width=3.2)
        self.edge = (a, b)
        self.j = a + (b - a) * tm
        t = (b - a) / np.linalg.norm(b - a)
        nrm = np.array([-t[1], t[0]])
        if not inside(self.j + nrm * 0.5, self.poly)[0]:
            nrm = -nrm
        self.d = nrm
        self.u = np.array([self.d[1], -self.d[0]])
        uv = self.local(self.poly)
        self.wl, self.wr = float(-uv[:, 0].min()), float(uv[:, 0].max())
        self.v0, self.v1 = 0.0, float(uv[:, 1].max())
        self.path = np.array([self.j - self.d * 3, self.j])

    @property
    def angle(self):
        return math.atan2(-self.d[0], self.d[1])

    @property
    def depth(self):
        return self.v1 - self.v0

    def world(self, u, v):
        return self.j + self.u * u + self.d * v

    def local(self, p):
        q = np.asarray(p, float) - self.j
        return np.array([q @ self.u, q @ self.d]) if q.ndim == 1 else np.stack([q @ self.u, q @ self.d], -1)

    def corners(self):
        return self.poly

    def path_u(self, v):
        return 0.0

    @property
    def drive_end_v(self):
        return 3.0
