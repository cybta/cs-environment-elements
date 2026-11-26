"""One lot of the user's drawn plan: the cottage on the drawn footprint (veranda toward the drawn door side),
the fence along the drawn outline (shared sides built once, by the lower-numbered lot), the gate where the
driveway comes in, a wicket door + path beside it when there's room, and the yard (lots.LotBuilder's).
"""
import math
import random

import bpy
import numpy as np

from cs_environment_elements.buildings import fence_build as fb, house, paint_edit
from cs_environment_elements.buildings.fence_paint import PALETTE, quiet as fence_quiet
from cs_environment_elements.core import library, naming
from cs_environment_elements.core import neighborhood_materials as nm
from cs_environment_elements.core.paint import quiet as paint_quiet

from . import terrain as tr
from .drawn import inside
from .layout import densify
from .lots import LotBuilder, Occupancy, adopt

# The user's palette (2026-11-24): (light: walls + the lot's fence, dark: roof), sRGB; 40 % blue, 40 % teal,
# 20 % red houses
SCHEMES = {"blue": ("6389a6", "153752"), "teal": ("7ba3a1", "225855"), "red": ("a66363", "3a1414")}
SHARE = (("blue", 0.4), ("teal", 0.4), ("red", 0.2))
WALL_PEEL, TRIM_PEEL, ROOF_PEEL = (0.03, 0.05), (0.03, 0.06), (0.03, 0.08)
N_LOTS = 20


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def scheme(idx, seed):
    """The colour scheme of lot `idx` (1..N_LOTS): the shares exactly, shuffled by the seed."""
    names = [n for n, f in SHARE for _ in range(round(f * N_LOTS))]
    random.Random(seed * 7717 + 5).shuffle(names)
    light, dark = SCHEMES[names[(idx - 1) % len(names)]]
    return _rgb(light), _rgb(dark)


PILE_SINK = 0.03        # the cottage sits this far below the lowest ground under it: its piles bed in


class PolyOccupancy(Occupancy):
    """Occupancy whose free space is the lot polygon (in the lot's u, v frame), kept `margin` off the fence."""

    def __init__(self, bounds, poly_uv, margin=0.4):
        super().__init__(bounds)
        self.poly_uv, self.margin = poly_uv, margin

    def free(self, u0, u1, v0, v1):
        corners = np.array([(u0, v0), (u1, v0), (u1, v1), (u0, v1), ((u0 + u1) / 2, v0), ((u0 + u1) / 2, v1),
                            (u0, (v0 + v1) / 2), (u1, (v0 + v1) / 2)])
        if not inside(corners, self.poly_uv).all():
            return False
        p = self.poly_uv
        for c in corners:
            for i in range(len(p)):
                a, b = p[i], p[(i + 1) % len(p)]
                ab = b - a
                t = np.clip(np.dot(c - a, ab) / max(np.dot(ab, ab), 1e-9), 0, 1)
                if np.linalg.norm(c - (a + ab * t)) < self.margin:
                    return False
        return all(u1 <= r[0] or u0 >= r[1] or v1 <= r[2] or v0 >= r[3] for r in self.rects)


class DrawnLotBuilder(LotBuilder):
    def __init__(self, ctx, terrain, lot, seed, colls, plan, poles=()):
        super().__init__(ctx, terrain, lot, seed, colls, poles)
        self.plan = plan
        L = lot
        self.occ = PolyOccupancy((-L.wl, L.wr, 0.0, L.v1), L.local(L.poly))
        self.gate_u = 0.0
        self.info["rock_spots"] = []

    def build(self):
        self._drawn_cottage()
        self._driveway_space()
        self._door_and_path()
        self._drawn_fence()
        self._yard()
        if self.rng.random() < 0.4:
            spot = self.occ.find(self.rng, 1.0, 1.0)
            if spot:
                self.info["rock_spots"].append(self.L.world(*spot))
        return self.info

    # ------------------------------------------------------------ the cottage on the drawn footprint
    def _drawn_cottage(self):
        ctx, rng, L, hr = self.ctx, self.rng, self.L, self.L.house_rec
        s = ctx.scene.house_gen
        s.building_type = "COTTAGE"
        s.add_labels, s.add_lights, s.add_inserts = False, False, True
        s.cottage_style = "PAINTED" if rng.random() < 0.6 else "TIMBER"
        s.total_area = rng.uniform(52, 72)
        s.bedrooms = 2 if s.total_area > 60 else 1
        s.bathrooms = 0
        s.seed = 2000 + self.seed * 37 + L.idx
        with paint_quiet():
            for k in ("cottage_roof", "cottage_paint", "cottage_siding"):
                setattr(s, k, "RANDOM")
            s.cottage_peel = rng.uniform(0.10, 0.18)          # walls 10 - 18 % peeled (user, 2026-11-23: less sad)
            s.cottage_roof_peel = rng.uniform(0.10, 0.20)     # roofs 10 - 20 %
        s.cottage_chimney = rng.random() < 0.75
        s.sidewalk = False            # no gravel bed under the house (user, 2026-11-23: ground cover is Godot's job)
        name = naming.next_name("cottage-%s" % s.cottage_style.lower())
        ctx.scene.cursor.location = (0, 0, 0)
        plan = house._build(ctx, s, lambda *a: print("cottage:", a), name=name, site=True)
        root = bpy.data.objects[name]
        light, dark = scheme(L.idx, self.seed)
        prng = random.Random(self.seed * 991 + L.idx)        # own stream: the rest of the lot stays as it was
        changes = {"trim": (None, prng.uniform(*TRIM_PEEL)), "roof": (dark, prng.uniform(*ROOF_PEEL))}
        wall_peel = prng.uniform(*WALL_PEEL)
        if s.cottage_style == "PAINTED":
            changes["wall"] = (light, wall_peel)
        paint_edit.update(root, changes)
        ctx.view_layer.update()
        lo, hi = library.bounds(root)
        corners = np.array(hr["corners"])
        centre = corners.mean(0)
        front = np.array(hr["door"]) - centre
        front /= np.linalg.norm(front)
        theta = math.atan2(front[0], -front[1])            # the cottage's -Y (veranda) toward the drawn door
        ct, st = math.cos(theta), math.sin(theta)

        def rot(v):
            return np.array([v[0] * ct - v[1] * st, v[0] * st + v[1] * ct])

        c_local = np.array([(lo.x + hi.x) / 2, (lo.y + hi.y) / 2])
        foot = [np.array(p) for p in ((lo.x, lo.y), (hi.x, lo.y), (hi.x, hi.y), (lo.x, hi.y),
                                      ((lo.x + hi.x) / 2, lo.y), ((lo.x + hi.x) / 2, hi.y),
                                      (lo.x, (lo.y + hi.y) / 2), (hi.x, (lo.y + hi.y) / 2))]
        pos = centre - rot(c_local)
        lot_centre = L.poly.mean(0)
        for _ in range(30):                                   # keep the whole house (veranda, steps) in the lot
            pts = np.array([pos + rot(f) for f in foot])
            out = ~inside(pts, L.poly)
            if not out.any():
                break
            pos = pos + (lot_centre - pos) / (np.linalg.norm(lot_centre - pos) or 1) * 0.25
        # on the lowest ground under it: no pile hangs in the air on a slope (uphill ones go into the ground)
        under = np.array([pos + rot(f) for f in foot] + [pos])
        root.location = (pos[0], pos[1], float(self.t.height(under).min()) - PILE_SINK)
        root.rotation_euler.z = theta
        adopt(bpy.data.collections[name], self.c["cottages"])
        uv = L.local(np.array([pos + rot(f) for f in foot]))
        hu, hv = L.local(pos)
        self.occ.add(uv[:, 0].min() - 0.3, uv[:, 0].max() + 0.3, uv[:, 1].min() - 0.3, uv[:, 1].max() + 0.3)
        door_w = pos + rot(np.array([0.0, lo.y]))
        self.house = dict(u=hu, v=hv, front=hv - uv[:, 1].min(), back=uv[:, 1].max() - hv,
                          hw_l=hu - uv[:, 0].min(), hw_r=uv[:, 0].max() - hu, door_u=L.local(door_w)[0],
                          beside=True)
        self.steps = door_w
        self.info.update(name=name, root=root, W=plan.W, D=plan.D, lift=s.ground_lift, angle=theta,
                         center=(pos[0], pos[1]), u=hu, v=hv)

    def _driveway_space(self):
        """Keep the drawn driveway (road surface inside the lot) and the gate swing free of yard things."""
        L = self.L
        us = np.arange(-L.wl, L.wr, 0.5)
        vs = np.arange(0.0, L.v1, 0.5)
        uu, vv = np.meshgrid(us, vs)
        pts = np.array([L.world(u, v) for u, v in zip(uu.ravel(), vv.ravel())])
        on = self.plan.on_road(pts)
        for (u, v) in np.stack([uu.ravel(), vv.ravel()], -1)[on]:
            self.occ.add(u - 0.5, u + 0.5, v - 0.5, v + 0.5)
        g = L.gate
        self.occ.add(-g["width"] / 2 - 0.4, g["width"] / 2 + 0.4, -0.5, g["width"] * 0.6)

    def _door_and_path(self):
        """A wicket door in the gate's fence side, on the house's side of the gate, and a path to the steps."""
        L, rng = self.L, self.rng
        a, b = L.edge
        ln = float(np.linalg.norm(b - a))
        g = L.gate
        tm = (g["t0"] + g["t1"]) / 2
        steps_t = float(np.dot(self.steps - a, b - a) / ln ** 2)
        off = (min(max(g["width"], 2.4), 4.0) / 2 + 1.2) / ln
        self.door_t = None
        for t in sorted((tm - off, tm + off), key=lambda t: abs(t - steps_t)):
            if 0.08 < t < 0.92:
                p = a + (b - a) * t
                if not self.plan.on_road([p + L.d * 0.6])[0]:
                    self.door_t = t
                    break
        self.door = self.door_t is not None
        if not self.door:
            return
        p_fence = a + (b - a) * self.door_t
        pts = np.array([p_fence - L.d * 0.2, self.steps])
        if np.linalg.norm(pts[1] - pts[0]) < 1.0:
            return
        mat = nm.ensure("C_world_gravel" if rng.random() < 0.5 else "C_world_dirt")
        tr.ribbon("%s_Path" % self.info["name"], densify(pts, 1.0), self.t.height, -0.55, 0.55, 0.06, mat,
                  self.c["ground"], nm.uv_scale)
        uvp = L.local(pts)
        self.occ.add(uvp[:, 0].min() - 0.9, uvp[:, 0].max() + 0.9, uvp[:, 1].min(), uvp[:, 1].max())

    def _drawn_fence(self):
        ctx, L, rng = self.ctx, self.L, self.rng
        z = self.t.height(L.poly)
        me = bpy.data.meshes.new("%s_lot" % self.info["name"])
        n = len(L.poly)
        me.from_pydata([(p[0], p[1], zz) for p, zz in zip(L.poly, z)], [(i, (i + 1) % n) for i in range(n)], [])
        outline = bpy.data.objects.new("lot-%02d-outline" % L.idx, me)
        self.c["outlines"].objects.link(outline)
        g = ctx.scene.house_gen.fence
        g.style, g.seed, g.flip = "OLD", 100 + L.idx, False
        g.skip_sides = ", ".join(str(k) for k in sorted(L.skip))
        g.shared_posts = False
        g.height = rng.choice((1.2, 1.35, 1.5, 1.5, 1.6))
        g.uneven, g.gap = rng.uniform(0.025, 0.06), rng.uniform(0.05, 0.08)
        with fence_quiet():
            rng.random(), rng.choice(PALETTE)             # (old draws, kept so the rest stays as it was)
            g.paint, g.paint_color = True, scheme(L.idx, self.seed)[0]     # the house's light colour
            g.peel = rng.uniform(0.10, 0.20)          # 10 - 20 % peeled, like the houses (user, 2026-11-24)
        g.outline = outline
        gate = L.gate
        g.gate, g.gate_side = True, gate["side"]
        side_len = float(np.linalg.norm(L.edge[1] - L.edge[0]))
        g.gate_width = max(2.4, min(gate["width"], 4.0, side_len - 1.0))     # fits its side, posts included
        g.gate_pos = (gate["t0"] + gate["t1"]) / 2
        g.gate_leaves = rng.choice((1, 2))
        g.door = self.door
        if self.door:
            g.door_side, g.door_width, g.door_pos = gate["side"], 1.0, self.door_t
        name = naming.next_name("fence-old")
        res = fb.build(ctx, g, outline, fb.outline_chains(outline, ctx, sync_edit=False), name=name)
        fc = res[0] if isinstance(res, tuple) else res
        if fc is not None:
            adopt(fc, self.c["fences"])
            for w in (res[1] if isinstance(res, tuple) else []):
                print("fence %s (lot %d): %s" % (name, L.idx, w))
        self.info["fence"] = name
