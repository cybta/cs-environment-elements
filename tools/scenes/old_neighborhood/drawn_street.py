"""The street furniture for the drawn plan: old electric poles at the edge of the dirt roads (every other one
with a lamp) with sagging wires and a service cable to each cottage, Jagged rocks (Nature > Rocks), the
Gravel & Rubble props (Props > Gravel & Rubble) along the road edges, and a few trees in the open ground.
Reuses street.Street for the pole / wire / rock / tree mechanics.
"""
import math

import numpy as np

from cs_environment_elements.props import CATALOG as PROPS

from .drawn import inside
from .layout import densify, resample, seg_dist
from .lots import place
from .street import R0, SPACING, Street, tube_mesh, wire_material

POLE_GAP = 0.20             # pole surface to the fence's outside face (user, 2026-11-23)
FENCE_HALF = 0.06           # fence line to its outside face (posts + boards)


class DrawnStreet(Street):
    def __init__(self, ctx, terrain, net, lots, colls, seed, plan):
        super().__init__(ctx, terrain, net, lots, colls, seed)
        self.plan = plan
        self.polys = [L.poly for L in lots]

    def _clear(self, p, lot_gap=0.15, road_gap=False, taken_gap=1.0):
        """Free ground at p: off the road (or allowed near it), outside every lot, clear of what's placed."""
        p = np.asarray(p, float)
        if self.plan.on_road([p])[0]:
            return False
        if road_gap and self.plan.near_road([p])[0]:
            return False
        ring = p[None] + lot_gap * np.array([[1, 0], [-1, 0], [0, 1], [0, -1], [0.7, 0.7], [-0.7, -0.7],
                                             [0.7, -0.7], [-0.7, 0.7], [0, 0]])
        if any(inside(ring, q).any() for q in self.polys):
            return False
        if self.t.water(p[None])[0]:
            return False
        return all(np.hypot(p[0] - x, p[1] - y) >= r + taken_gap for x, y, r in self.taken)

    def _edge(self, c, n, reach=10.0):
        """From a road centre point c along n: the road's edge = the first point off the road surface, or
        just before a fence (the fences stand on the dirt where the street was narrowed)."""
        for t in np.arange(1.5, reach, 0.1):
            q = c + n * t
            ahead = (q + n * 0.3)[None]
            if any(inside(ahead, poly)[0] for poly in self.polys):
                return q - n * 0.12, t                       # the caller adds 0.12 again: right at the fence
            if not self.plan.on_road([q])[0]:
                return q, t
        return None, None

    # ------------------------------------------------------------ poles + wires along the dirt roads
    def _fence_spot(self, c, nrm, reach=8.0):
        """Look from road centre point c along nrm to the first fence: the pole spot just outside it (its
        surface POLE_GAP from the fence) and the pole's facing (away from the road), or None when there is no
        street fence there, it is seen end-on, or the spot is at a corner, a gate or the wicket door beside it."""
        best = None
        for L in self.lots:
            poly, k = L.poly, len(L.poly)
            for i in range(k):
                a, b = poly[i], poly[(i + 1) % k]
                e = b - a
                den = nrm[0] * e[1] - nrm[1] * e[0]
                if abs(den) < 1e-9:
                    continue
                w = a - c
                t = (w[0] * e[1] - w[1] * e[0]) / den
                u = (w[0] * nrm[1] - w[1] * nrm[0]) / den
                if 0 < t < reach and 0 <= u <= 1 and (best is None or t < best[0]):
                    best = (t, L, i, u)
        if best is None:
            return None
        t, L, i, u = best
        a, b = L.poly[i], L.poly[(i + 1) % len(L.poly)]
        ln = float(np.linalg.norm(b - a))
        if ln < 1.5:
            return None
        tan = (b - a) / ln
        out = np.array([-tan[1], tan[0]])
        if inside((a + b) / 2 + out * 0.3, L.poly)[0]:
            out = -out
        if out @ nrm > -0.6:                          # from inside the lot, or a side fence seen at a slant
            return None
        along = u * ln
        if along < 0.6 or along > ln - 0.6:           # not on a corner post
            return None
        g = L.gate
        if g["side"] == i + 1:                        # the gate + the wicket door beside it stay free
            gw = max(2.4, min(g["width"], 4.0, ln - 1.0))
            if abs(along - (g["t0"] + g["t1"]) / 2 * ln) < gw / 2 + 2.2:
                return None
        return a + tan * along + out * (FENCE_HALF + POLE_GAP + R0), -out

    def _open_spot(self, pts, tans, on, i0, segs, fence_free=4.0):
        for shift in (0, 1.5, -1.5, 3, -3, 4.5, -4.5, 6, -6):
            i = min(max(i0 + int(shift / 0.5), 0), len(pts) - 1)
            if not on[i]:
                continue
            for sd in (1, -1):
                nrm = np.array([-tans[i][1], tans[i][0]]) * sd
                edge, dist = self._edge(pts[i], nrm)
                if edge is None or dist > 6.5:
                    continue
                p = edge + nrm * 0.25
                if seg_dist(p[None], segs)[0] > fence_free and self._clear(p, lot_gap=0.14, taken_gap=0.5):
                    return p, nrm
        return None

    def poles_and_wires(self, nudges=()):
        """nudges: ((x, y), (dx, dy)) hand moves, for the pole that lands within 2 m of (x, y)."""
        chains = self.net.road_chains()
        anchor_x = self.net.data["anchor"][0]
        per_chain = []
        segs = np.array([(L.poly[i], L.poly[(i + 1) % len(L.poly)]) for L in self.lots for i in range(len(L.poly))])
        for ci, line in enumerate(chains):
            pts, tans, total = resample(densify(line, 0.5), 0.5)
            on = self.plan.on_road(pts)
            if on.mean() < 0.5 or total < 25:
                per_chain.append([])
                continue
            key = "pole_old_3arm" if line[:, 0].max() > anchor_x - 60 else \
                ("pole_old_1arm" if total < 70 else "pole_old_2arm")
            n = max(1, round((total - 12) / SPACING))
            made = []
            side = 1
            for s in [6 + k * (total - 12) / n for k in range(n + 1)]:
                i0 = int(round(s / 0.5))
                got = None
                for shift in (0, 1.5, -1.5, 3, -3, 4.5, -4.5, 6, -6, 7.5, -7.5, 9, -9):
                    i = min(max(i0 + int(shift / 0.5), 0), len(pts) - 1)
                    if not on[i]:
                        continue
                    for sd in (side, -side):                  # stay on one side of the street along a run
                        nrm = np.array([-tans[i][1], tans[i][0]]) * sd
                        spot = self._fence_spot(pts[i], nrm)
                        if spot and self._clear(spot[0], lot_gap=0.14, taken_gap=0.5):
                            got, side = spot, sd
                            break
                    if got:
                        break
                if not got:                                   # no fences here (the road to the bridge, the park):
                    got = self._open_spot(pts, tans, on, i0, segs)    # at the road edge, far from any fence
                if got:
                    for at, by in nudges:
                        if np.linalg.norm(got[0] - np.array(at)) < 2.0:
                            got = (got[0] + np.array(by), got[1])
                    made.append(self._pole(key, *got, lamp=len(self.poles) % 2 == 0, chain=ci))
            per_chain.append(made)
        spans = []
        for made in per_chain:
            spans += list(zip(made[:-1], made[1:]))
        ends = [m for made in per_chain if made for m in (made[0], made[-1])]
        for a in ends:
            cands = [b for b in self.poles if b["chain"] != a["chain"]]
            if not cands:
                continue
            b = min(cands, key=lambda b: np.linalg.norm(a["pos"] - b["pos"]))
            if np.linalg.norm(a["pos"] - b["pos"]) < 45 and not any({id(a), id(b)} == {id(x), id(y)}
                                                                     for x, y in spans):
                spans.append((a, b))
        lines = []
        for a, b in spans:
            lines += self._span(a, b)
        tube_mesh("power-lines", lines, 0.007, wire_material(), self.c["street"])
        gaps = sorted(float(seg_dist(np.array([p["pos"]]), segs)[0]) - FENCE_HALF - R0 for p in self.poles)
        near = [g for g in gaps if g < 1.0]
        print("poles: %d (%d by a fence, surface to fence %.2f - %.2f m; %d on fence-free road edges), spans: %d, "
              "wires: %d" % (len(self.poles), len(near), min(near, default=0), max(near, default=0),
                             len(gaps) - len(near), len(spans), len(lines)))

    # ------------------------------------------------------------ gravel & rubble along the road edges
    def gravel(self, count=18):
        rng = self.rng
        chains = [c for c in self.net.road_chains()]
        made = tries = 0
        while made < count and tries < 1500:
            tries += 1
            line = rng.choice(chains)
            pts, tans, _ = resample(densify(line, 1.0), 1.0)
            i = rng.randrange(len(pts))
            if not self.plan.on_road(pts[i:i + 1])[0]:
                continue
            nrm = np.array([-tans[i][1], tans[i][0]]) * rng.choice((1, -1))
            edge, dist = self._edge(pts[i], nrm)
            if edge is None or dist > 6.5:
                continue
            key, r, into = rng.choice((("gravel_spill", 1.2, 0.3), ("gravel_spill", 1.2, 0.3),
                                       ("gravel_pile_small", 0.8, 0.6), ("gravel_pile_large", 1.5, 1.4)))
            p = edge + nrm * into                         # half on the road edge, half on the verge
            ring = p[None] + r * np.array([[math.cos(a), math.sin(a)] for a in np.linspace(0, math.tau, 9)])
            if any(inside(ring, q).any() for q in self.polys):
                continue
            if self.t.water(np.vstack([p[None], ring])).any():   # the bridge road crosses the river
                continue
            if any(np.hypot(p[0] - x, p[1] - y) < rr + r + 0.6 for x, y, rr in self.taken):
                continue
            rot = math.atan2(tans[i][1], tans[i][0]) + rng.uniform(-0.3, 0.3)
            place(PROPS, "RUBBLE", key, self.at(p), rot, self.c["street"])
            self.taken.append((p[0], p[1], r))
            made += 1
        print("gravel & rubble on the road edges: %d" % made)

    # ------------------------------------------------------------ jagged rocks
    def jagged_rocks(self, infos, count=22):
        from cs_environment_elements.nature import rocks as rk
        rng = self.rng
        for info in infos:
            for b in info.get("bins", []):
                self.taken.append((b[0], b[1], 0.6))
        for info in infos:                                    # one or two in some yards
            for p in info.get("rock_spots", []):
                self._rock(rk, p, "JAGGED", rng.uniform(0.3, 0.6))
        allp = np.vstack(self.polys)
        lo, hi = allp.min(0) - 25, allp.max(0) + 25
        made = tries = 0
        while made < count and tries < 2000:
            tries += 1
            p = np.array([rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])])
            if not self._clear(p, lot_gap=0.6, taken_gap=1.2):
                continue
            # most by the roads, the rest out in the open (the verges are mostly inside the lots now, so
            # after a while any free spot will do)
            if made < count * 0.5 and tries < 1000 and not self.plan.near_road([p])[0]:
                continue
            for k in range(rng.choice((1, 1, 2, 3))):
                q = p + (np.array([rng.uniform(-0.8, 0.8), rng.uniform(-0.8, 0.8)]) if k else 0)
                if k and not self._clear(q, lot_gap=0.6, taken_gap=0.0):
                    continue
                self._rock(rk, q, "JAGGED", rng.uniform(0.35, 0.7) if k else rng.uniform(0.5, 1.1))
            self.taken.append((p[0], p[1], 1.0))
            made += 1
        print("jagged rocks: %d groups" % made)

    # ------------------------------------------------------------ trees in the open
    def open_trees(self, count=10, bushes=14):
        from cs_environment_elements.nature import core as tree_core
        rng = self.rng
        ts = self.ctx.scene.treegen
        allp = np.vstack(self.polys)
        lo, hi = allp.min(0) - 25, allp.max(0) + 25
        for n, (want, species, gap) in enumerate(((count, ("OAK", "MAPLE", "PINE", "PINE", "MAPLE_AUTUMN"), 6.0),
                                                  (bushes, ("BUSH",), 1.0))):
            made = tries = 0
            while made < want and tries < 1500:
                tries += 1
                p = np.array([rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])])
                if not self._clear(p, lot_gap=gap, road_gap=True, taken_gap=gap):
                    continue
                if n == 0 and self.plan.near_road([p + (4, 0), p - (4, 0), p + (0, 4), p - (0, 4)]).any():
                    continue
                ts.species = rng.choice(species)
                values = {k: getattr(ts, k) for k in tree_core.COPIED_PROPS}
                values["seed"] = rng.randrange(1, 10 ** 5)
                ob = tree_core.create_tree(self.ctx, values, self.at(p, -0.05))
                for c in list(ob.users_collection):
                    c.objects.unlink(ob)
                self.c["trees"].objects.link(ob)
                ob.rotation_euler.z = rng.uniform(0, math.tau)
                if n == 1:
                    s = rng.uniform(1.8, 3.0)
                    ob.scale = (s, s, s * rng.uniform(0.8, 1.1))
                self.taken.append((p[0], p[1], gap))
                made += 1
