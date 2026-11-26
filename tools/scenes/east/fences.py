"""Lot fences of the east side: the add-on's Modern fence (concrete plinth, masonry pillars, slat panels) along each
lot's outline (east_plan.json, which already starts at the sidewalk's outer edge).

- a side shared with a neighbour is built once, by the lot listed first;
- the street sides are the ones along a road; a parking gate where the driveway crosses one, a wicket door where
  the walk from the front door crosses it (user, 2026-11-25: in line with the house's door), with the mailbox
  pillar (the lot's number) on its side away from the gate; without such a walk the door goes beside the gate;
  the sides are straight already (east_lots.py), a short gate side is joined with its neighbours so a gate fits;
- villas: 1.8 m, a pillar at every panel; houses: 1.4 m, pillars at corners and openings, slim posts between.
"""
import math
import random

import bpy
import numpy as np

from cs_environment_elements.buildings import fence_build as fb
from old_neighborhood.lots import adopt


def seg_dist(p, a, b):
    d = b - a
    t = max(0.0, min(1.0, float(np.dot(p - a, d) / (np.dot(d, d) or 1e-9))))
    return float(np.linalg.norm(p - a - t * d)), t


def poly_dist(p, poly):
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)])[0] for i in range(len(poly)))


def road_dist(p, roads):
    """Distance from p to the nearest road edge's centreline, less that road's reach (0 = on its edge line)."""
    best = math.inf
    for pts, reach in roads:
        for a, b in zip(pts, pts[1:]):
            best = min(best, seg_dist(p, a, b)[0] - reach)
    return best


def cross(p0, p1, a, b):
    """Where segment p0-p1 crosses segment a-b: t along a-b, or None."""
    d, e = p1 - p0, b - a
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    w = a - p0
    s = (w[0] * e[1] - w[1] * e[0]) / den
    t = (w[0] * d[1] - w[1] * d[0]) / den
    return t if 0 <= s <= 1 and 0 <= t <= 1 else None


class LotFence:
    def __init__(self, idx, L, lots, roads, info, seed):
        self.idx, self.L, self.info = idx, L, info
        self.rng = random.Random(seed * 77 + idx)
        self.poly = [np.array(p, float) for p in L["outline"]]
        self.others = [(j, [np.array(p, float) for p in M["outline"]]) for j, M in enumerate(lots) if j != idx]
        self.roads = roads
        if info.get("drive_start") is not None:
            self._widen_for_gate()

    def side(self, i):
        return self.poly[i], self.poly[(i + 1) % len(self.poly)]

    def shared_with(self, i):
        a, b = self.side(i)
        for j, q in self.others:
            if all(poly_dist(a + (b - a) * t, q) < 0.35 for t in (0.15, 0.5, 0.85)):
                return j
        return None

    def street(self, i):
        a, b = self.side(i)
        return self.shared_with(i) is None and road_dist((a + b) / 2, self.roads) < 0.8

    def _drive(self):
        return np.array(self.info["drive_start"], float), np.array(self.info["drive_end"], float)

    def _door_side(self):
        """Where the walk from the front door (door_start -> door_end) crosses the outline: (side, t) or None."""
        if self.info.get("door_start") is None or self.info.get("door_end") is None:
            return None
        p0, p1 = np.array(self.info["door_start"], float), np.array(self.info["door_end"], float)
        for i in range(len(self.poly)):
            t = cross(p0, p1, *self.side(i))
            if t is not None:
                return i, t
        return None

    def _gate_side(self):
        p0, p1 = self._drive()
        for i in range(len(self.poly)):
            t = cross(p0, p1, *self.side(i))
            if t is not None:
                return i, t
        streets = [i for i in range(len(self.poly)) if self.street(i)]
        if not streets:
            return None, None
        i = min(streets, key=lambda i: np.linalg.norm((self.side(i)[0] + self.side(i)[1]) / 2 - p0))
        return i, 0.5

    def _corner(self, k):
        """A vertex another lot's outline runs through (a shared corner): never removed."""
        return any(poly_dist(self.poly[k], q) < 0.5 for _, q in self.others)

    def _widen_for_gate(self, need=None):
        """Join the gate side with its neighbours (dropping the vertex between) until a gate fits, while the
        outline moves less than 0.8 m."""
        need = need or (4.0 if self.L["kind"] == "villa" else 3.6) + 2.4
        for _ in range(12):
            i, _t = self._gate_side()
            if i is None:
                return
            a, b = self.side(i)
            if np.linalg.norm(b - a) >= need:
                return
            n = len(self.poly)
            options = []
            for k, (p, q) in ((i, (self.poly[i - 1], b)), ((i + 1) % n, (a, self.poly[(i + 2) % n]))):
                if not self._corner(k):
                    options.append((seg_dist(self.poly[k], p, q)[0], k))
            if not options or min(options)[0] > 0.8:
                return
            del self.poly[min(options)[1]]

    def build(self, ctx, terrain, outlines, coll):
        L, rng, n = self.L, self.rng, len(self.poly)
        skip = [i for i in range(n) if (j := self.shared_with(i)) is not None and j < self.idx]
        if len(skip) >= n:
            return None
        terrain_z = terrain.height(np.array(self.poly))
        me = bpy.data.meshes.new("%s_lot" % self.info["name"])
        me.from_pydata([(p[0], p[1], float(z)) for p, z in zip(self.poly, terrain_z)],
                       [(i, (i + 1) % n) for i in range(n)], [])
        outline = bpy.data.objects.new("%s-outline" % self.info["name"], me)
        outlines.objects.link(outline)
        g = ctx.scene.house_gen.fence
        g.style, g.seed, g.flip, g.shared_posts = "MODERN", 300 + self.idx, False, False
        g.skip_sides = ", ".join(str(i + 1) for i in sorted(set(skip)))
        villa = L["kind"] == "villa"
        g.height, g.plinth_h = (1.8, 0.5) if villa else (1.4, 0.4)
        g.pillars = "EVERY" if villa else "ENDS"
        g.pillar_mat = rng.choice(("CONCRETE", "RENDER"))
        g.infill = rng.choice(("METAL", "CEDAR") if villa else ("CEDAR", "WEATHERED", "METAL"))
        g.house_number = "".join(ch for ch in L["name"] if ch.isdigit()) or "1"
        g.gate = g.door = g.mailbox = False
        if self.info.get("drive_start") is not None:
            i, t = self._gate_side()
            if i is not None and i not in skip:
                a, b = self.side(i)
                ln = float(np.linalg.norm(b - a))
                gw = max(2.4, min(4.0 if villa else 3.6, ln - 1.0))
                half = (gw / 2 + 0.2) / ln
                t = min(max(t, half), 1 - half)
                g.gate, g.gate_side, g.gate_width, g.gate_pos = True, i + 1, gw, t
                g.gate_leaves = 2 if villa else rng.choice((1, 2))
                door = self._door_side()
                if door is not None and door[0] not in skip:      # in line with the house's door
                    j, u = door
                    g.door, g.door_side, g.door_pos, g.door_width = True, j + 1, u, 1.0
                    away = ("RIGHT" if t < u else "LEFT") if j == i else rng.choice(("LEFT", "RIGHT"))
                    g.mailbox, g.mailbox_side = True, away                # the mailbox pillar away from the gate
                else:                                             # beside the gate, on the roomier side
                    off = (gw / 2 + 0.3 + 1.6) / ln
                    for dt, side in ((off, "RIGHT"), (-off, "LEFT")) if t < 0.5 else ((-off, "LEFT"), (off, "RIGHT")):
                        if 0.6 / ln < t + dt < 1 - 0.6 / ln:
                            g.door, g.door_side, g.door_pos, g.door_width = True, i + 1, t + dt, 1.0
                            g.mailbox, g.mailbox_side = True, side
                            break
        g.outline = outline
        name = "%s-fence" % self.info["name"]
        res = fb.build(ctx, g, outline, fb.outline_chains(outline, ctx, sync_edit=False), name=name)
        fc = res[0] if isinstance(res, tuple) else res
        if fc is not None:
            adopt(fc, coll)
            for w in (res[1] if isinstance(res, tuple) else []):
                print("fence %s: %s" % (name, w))
        return name
