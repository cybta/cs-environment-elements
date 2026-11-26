"""Road graph + lot fitting for the old neighbourhood (pure Python + numpy, no bpy).

Input: poor_quarter_layout.json (extract_poor_quarter.py): road and driveway centre-line segments in Blender
world metres. Every driveway end gets one lot: a rectangle in the driveway's own frame

    origin J = where the driveway leaves the road,  d = from J to the driveway end (into the lot),
    u = d turned -90 deg (lot "right"),  lot = u in [-wl, wr], v in [FRONT, v1]

Lots start small and grow round-robin (fair to neighbours) while they keep clear of the roads, the
other driveways, each other, the water and steep ground.
"""
import json
import math
from collections import defaultdict

import numpy as np

ROAD_HALF = 3.5          # 7 m roads
SHOULDER = 1.2           # gravel strip beside the road, 3.5 .. 4.7 m off the centre line
FRONT = 3.85             # lot front (fence line) off the road centre: 35 cm past the 3.5 m road edge (user)
FRONT_TOL = 0.05         # the front may come this much closer on curves (30 cm from the road edge)
DRIVE_HALF = 1.5         # 3 m driveways
LOT_GAP = 0.9            # min distance between two lots' fences
START_W, START_D = 4.5, 13.0
MAX_W, MAX_D = 8.0, 20.0             # driveway lots: <= 16 x 20 m (crowded old quarter)
INFILL_W, INFILL_D = 6.0, 14.0       # road-facing lots without a driveway, between the others (start size)
INFILL_MAX_W, INFILL_MAX_D = 7.0, 18.0
INFILL_STEP = 1.0                    # metres between tries along the road
MIN_W_TOTAL, MIN_D = 11.0, 13.0


def key(p):
    return (round(float(p[0]), 2), round(float(p[1]), 2))


class Network:
    def __init__(self, path, scale=1.0):
        """`scale` < 1 shrinks the quarter about its centre like the terrain bake's POOR_SHRINK does:
        every node moves except the anchor (the river crossing), so the approach road keeps its far end."""
        data = json.load(open(path))
        self.data = data
        self.scale = scale
        centre, anchor = np.array(data["center"], float), np.array(data["anchor"], float)

        def sc(p):
            p = np.array(p, float)
            return p if np.linalg.norm(p - anchor) < 0.5 else centre + (p - centre) * scale

        self.shrink = sc
        self.roads = [(sc(a), sc(b)) for a, b in data["roads"]]
        self.drives = [(sc(a), sc(b)) for a, b in data["drives"]]
        self.adj = defaultdict(set)          # all segments
        self.road_adj = defaultdict(set)     # roads only
        for segs, kind in ((self.roads, "road"), (self.drives, "drive")):
            for a, b in segs:
                ka, kb = key(a), key(b)
                if ka == kb:
                    continue
                self.adj[ka].add(kb)
                self.adj[kb].add(ka)
                if kind == "road":
                    self.road_adj[ka].add(kb)
                    self.road_adj[kb].add(ka)
        self.road_seg = np.array([[a, b] for a, b in self.roads])       # (n, 2, 2)
        self.drive_seg = np.array([[a, b] for a, b in self.drives])

    # ------------------------------------------------------------ chains (polylines between junctions)
    def road_chains(self):
        """Road polylines between nodes of degree != 2 (a closed loop with no junction is one chain)."""
        adj, seen, chains = self.road_adj, set(), []
        ends = [n for n, ns in adj.items() if len(ns) != 2]

        def walk(a, b):
            line = [a, b]
            seen.add(frozenset((a, b)))
            while len(adj[line[-1]]) == 2:
                nxt = [n for n in adj[line[-1]] if n != line[-2]]
                if not nxt or frozenset((line[-1], nxt[0])) in seen:
                    break
                seen.add(frozenset((line[-1], nxt[0])))
                line.append(nxt[0])
            return line

        for a in ends:
            for b in adj[a]:
                if frozenset((a, b)) not in seen:
                    chains.append(walk(a, b))
        for a in adj:                                   # pure loops
            for b in adj[a]:
                if frozenset((a, b)) not in seen:
                    chains.append(walk(a, b))
        return [np.array(c, float) for c in chains]

    def driveways(self):
        """[(end E, junction J, path from J to E)] for every driveway dead end."""
        out = []
        for e, ns in self.adj.items():
            if len(ns) != 1 or e in self.road_adj:
                continue
            path, prev, cur = [e], None, e
            while cur not in self.road_adj:
                nxt = [n for n in self.adj[cur] if n != prev]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                path.append(cur)
            if cur in self.road_adj:
                out.append((np.array(e, float), np.array(cur, float), np.array(path[::-1], float)))
        return out


# ------------------------------------------------------------------ geometry helpers
def seg_dist(pts, segs):
    """Distance from each point (m, 2) to the nearest segment (n, 2, 2) -> (m,)."""
    if len(segs) == 0:
        return np.full(len(pts), 1e9)
    a, b = segs[:, 0][None], segs[:, 1][None]               # (1, n, 2)
    p = pts[:, None]                                        # (m, 1, 2)
    ab = b - a
    t = np.clip(((p - a) * ab).sum(-1) / np.maximum((ab * ab).sum(-1), 1e-9), 0, 1)
    d = np.linalg.norm(p - (a + ab * t[..., None]), axis=-1)
    return d.min(1)


def polys_overlap(p, q, gap=0.0):
    """Separating-axis test for two convex polygons (k, 2); `gap` = they must be at least this far apart."""
    for poly in (p, q):
        for i in range(len(poly)):
            e = poly[(i + 1) % len(poly)] - poly[i]
            n = np.array([-e[1], e[0]]) / (np.linalg.norm(e) + 1e-12)
            a, b = p @ n, q @ n
            if a.max() + gap <= b.min() or b.max() + gap <= a.min():
                return False
    return True


def perimeter(poly, step=1.0):
    pts = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        n = max(1, int(np.linalg.norm(b - a) / step))
        pts += [a + (b - a) * k / n for k in range(n)]
    return np.array(pts)


# ------------------------------------------------------------------ lots
class Lot:
    def __init__(self, idx, end, junction, path, road_nbrs=()):
        self.idx, self.end, self.j, self.path = idx, end, junction, path
        d = end - junction
        self.length = float(np.linalg.norm(d))
        d = d / max(self.length, 1e-9)
        # square to the road (fences parallel to it) unless the driveway leaves at a steep angle
        if len(road_nbrs) >= 2:
            t = road_nbrs[0] - road_nbrs[1]
            n = np.array([-t[1], t[0]]) / max(np.linalg.norm(t), 1e-9)
            n = n if n @ d > 0 else -n
            if n @ d > math.cos(math.radians(30)):
                d = n
        self.d = d
        self.u = np.array([self.d[1], -self.d[0]])
        self.v0 = FRONT
        self.wl = self.wr = START_W
        self.v1 = FRONT + START_D
        self.hero = False
        self.ok = True
        self.infill = False         # a road-facing lot without a driveway
        self.quad = None            # set when a side is shared: the lot is then this quad, not the rectangle
        self.skip = set()           # fence sides (1-based, side n = corner n -> n+1) a neighbour builds

    def local(self, p):
        """World (x, y) -> lot (u, v)."""
        q = np.asarray(p, float) - self.j
        return np.array([q @ self.u, q @ self.d]) if q.ndim == 1 else np.stack([q @ self.u, q @ self.d], -1)

    def path_u(self, v):
        """u of the driveway centre line at depth v (straight on past its end)."""
        uv = self.local(self.path)
        if v >= uv[-1, 1]:
            return float(uv[-1, 0])
        for a, b in zip(uv[:-1], uv[1:]):
            if a[1] <= v <= b[1] and b[1] > a[1]:
                return float(a[0] + (b[0] - a[0]) * (v - a[1]) / (b[1] - a[1]))
        return float(uv[0, 0])

    @property
    def drive_end_v(self):
        return float(self.local(self.end)[1])

    @property
    def angle(self):
        """Z rotation that turns local +Y into d (local +X into u)."""
        return math.atan2(-self.d[0], self.d[1])

    def world(self, u, v):
        return self.j + self.u * u + self.d * v

    def corners(self, wl=None, wr=None, v1=None):
        if self.quad is not None and wl is None and wr is None and v1 is None:
            return self.quad
        wl = self.wl if wl is None else wl
        wr = self.wr if wr is None else wr
        v1 = self.v1 if v1 is None else v1
        return np.array([self.world(-wl, self.v0), self.world(wr, self.v0), self.world(wr, v1),
                         self.world(-wl, v1)])

    @property
    def depth(self):
        return self.v1 - self.v0

    def set_front(self, net, w=START_W):
        """The first depth where the lot's front edge clears every road."""
        self.v0 = FRONT
        while self.v0 < FRONT + 8:
            front = perimeter(self.corners(w, w, self.v0 + 0.01)[:2][[0, 1, 1, 0]], 0.5)
            if seg_dist(front, net.road_seg).min() >= FRONT - FRONT_TOL:
                break
            self.v0 += 0.25


def fit_lots(net, hero=None, water=None, height=None, max_rise=1.2, log=print, share=1.0, seed=1,
             reserve=None, infill=True):
    """One Lot per driveway end, then road-facing infill lots in the gaps, all grown to fill the space.
    `water(pts) -> bool array` and `height(pts) -> array` are optional checks; `hero` = (x, y) of an existing
    house: that lot is kept (sized like the others) but marked hero, nothing is built on it.
    `reserve(live_lots) -> [polygon]`: areas kept free of infill lots (e.g. the playground)."""
    lots = [Lot(i, e, j, p, [np.array(n) for n in net.road_adj[key(j)]])
            for i, (e, j, p) in enumerate(net.driveways())]
    if hero is not None:
        h = np.array(hero, float)
        min(lots, key=lambda L: np.linalg.norm(L.end - h)).hero = True
    blocked = []

    def valid(lot, wl, wr, v1, others):
        return valid_poly(lot, lot.corners(wl, wr, v1), others)

    def valid_poly(lot, poly, others):
        per = perimeter(poly, 0.8)
        if seg_dist(per, net.road_seg).min() < FRONT - FRONT_TOL:
            return False
        own = [k for k, (a, b) in enumerate(net.drives)
               if any(np.allclose(a, q, atol=0.02) or np.allclose(b, q, atol=0.02) for q in lot.path)]
        other = np.delete(net.drive_seg, own, axis=0) if own else net.drive_seg
        if len(other) and seg_dist(per, other).min() < DRIVE_HALF + 0.6:
            return False
        for o in others:
            if polys_overlap(poly, o.corners(), LOT_GAP):
                return False
        if any(polys_overlap(poly, q, 1.5) for q in blocked):
            return False
        if water is not None and water(per).any():
            return False
        if height is not None:
            z = height(per)
            if z.max() - z.min() > max_rise:
                return False
        return True

    def grow(live):
        """Round-robin: width 0.5 m a side, depth 1 m, until nothing changes."""
        changed = True
        while changed:
            changed = False
            for L in live:
                others = [o for o in live if o is not L]
                mw, md = (INFILL_MAX_W, INFILL_MAX_D) if L.infill else (MAX_W, MAX_D)
                for side in ("wl", "wr", "v1"):
                    cur = getattr(L, side)
                    cap = L.v0 + md if side == "v1" else mw
                    step = 1.0 if side == "v1" else 0.5
                    if cur + step > cap:
                        continue
                    trial = dict(wl=L.wl, wr=L.wr, v1=L.v1)
                    trial[side] = cur + step
                    if valid(L, trial["wl"], trial["wr"], trial["v1"], others):
                        setattr(L, side, cur + step)
                        changed = True

    for L in lots:
        L.set_front(net)
        L.v1 = L.v0 + START_D
    # start small; lots that can't even start are dropped
    for L in lots:
        others = [o for o in lots if o is not L and o.ok and o.idx < L.idx]
        if not valid(L, L.wl, L.wr, L.v1, others):
            for w, dd in ((4.0, 12.0), (3.6, 11.0)):
                if valid(L, w, w, L.v0 + dd, others):
                    L.wl = L.wr = w
                    L.v1 = L.v0 + dd
                    break
            else:
                L.ok = False
                log("lot %d: no room at the end of its driveway, skipped" % L.idx)
    live = [L for L in lots if L.ok]
    grow(live)
    if reserve:
        blocked += reserve(live)
    if infill:
        added = _infill(net, live, valid, len(lots))
        log("%d infill lots facing the road" % len(added))
        lots += added
        live += added
        grow(live)
    if share:
        _share_borders(live, valid_poly, share, seed, log)
    for L in live:
        if L.wl + L.wr < MIN_W_TOTAL or L.depth < MIN_D:
            log("lot %d: small (%.1f x %.1f m)" % (L.idx, L.wl + L.wr, L.depth))
    return lots


def _infill(net, live, valid, first_idx):
    """Road-facing lots (no driveway) wherever the verge between the other lots has room for one."""
    added = []
    anchor = np.array(net.data["anchor"], float)
    for line in net.road_chains():
        if np.linalg.norm(line - anchor, axis=1).min() < 1.0:
            continue                                     # the approach road to the bridge stays open (user)
        pts, tans, _ = resample(densify(line, 0.5), INFILL_STEP)
        for side in (1, -1):
            i = 0
            while i < len(pts):
                p, t = pts[i], tans[i]
                n = np.array([-t[1], t[0]]) * side
                L = Lot(first_idx + len(added), p + n * FRONT, p, np.array([p, p + n * FRONT]), [p + t, p - t])
                L.infill = True
                L.set_front(net, INFILL_W)
                L.wl = L.wr = INFILL_W
                L.v1 = L.v0 + INFILL_D
                if L.v0 < FRONT + 1.5 and valid(L, L.wl, L.wr, L.v1, live + added):
                    added.append(L)
                    i += int(2 * INFILL_W / INFILL_STEP)
                else:
                    i += 1
    return added


def place_house(L, hw_l, hw_r, front, back, front_yard):
    """Where the cottage goes in lot L -> (u, v of its origin, beside_driveway). The house's local extents:
    hw_l / hw_r across, `front` (veranda + steps side, toward the road) and `back` from its origin.
    Driveway lots: beside the driveway on the side with more room, else straight at the driveway's end.
    Infill lots: in the middle, the door to the road."""
    if not L.infill:
        fits = _house_beside(L, hw_l, hw_r, front, back, front_yard)
        if fits is None:                    # no room beside the driveway: no driveway, the house in the middle
            L.infill = True
            L.no_drive = True
        else:
            return fits
    if L.infill:
        slack = max(0.0, (L.wl + L.wr) / 2 - max(hw_l, hw_r) - 1.2)
        u = (L.wr - L.wl) / 2 + (slack * 0.4 if L.idx % 2 else -slack * 0.4)
        v = L.v0 + front_yard + front
        return u, min(v, max(L.v0 + 1.0 + front, L.v1 - 1.5 - back)), False


def _house_beside(L, hw_l, hw_r, front, back, front_yard):
    """Beside the driveway (side with more room) or at its end -> (u, v, beside), or None if neither fits."""
    v_front = L.v0 + front_yard
    span = [L.path_u(v) for v in np.linspace(L.v0, v_front + front + back, 6)]
    options = []
    u_right = max(span) + DRIVE_HALF + 0.9 + hw_l
    if u_right + hw_r + 1.0 <= L.wr:
        options.append((L.wr - (u_right + hw_r), u_right))
    u_left = min(span) - DRIVE_HALF - 0.9 - hw_r
    if u_left - hw_l - 1.0 >= -L.wl:
        options.append((u_left - hw_l + L.wl, u_left))
    u_end = L.path_u(L.drive_end_v)
    v_end_front = max(v_front, L.drive_end_v + DRIVE_HALF + 1.5)
    if not options and v_end_front + front + back <= L.v1 - 1.5:
        options.append((0.0, None))
    if not options:
        return None
    best = max(options, key=lambda o: o[0])
    if best[1] is not None:
        u, beside = best[1], True
    else:
        u, beside, v_front = u_end, False, v_end_front
    v = v_front + front
    if v + back > L.v1 - 1.5:                                   # short lot: smaller front yard
        v = max(L.v0 + 1.0 + front, L.v1 - 1.5 - back)
    return u, v, beside


def find_playground(net, polys, w, d, road_gap=6.0, lot_gap=1.5):
    """Centre of a free w x d (world-aligned) rectangle inside the loop, nearest its middle, or None."""
    loop = max(net.road_chains(), key=len)
    lo, hi = loop.min(0), loop.max(0)
    centre = loop.mean(0)
    best = None
    for x in np.arange(lo[0] + w / 2, hi[0] - w / 2, 1.0):
        for y in np.arange(lo[1] + d / 2, hi[1] - d / 2, 1.0):
            c = np.array([x, y])
            rect = np.array([c + (-w / 2, -d / 2), c + (w / 2, -d / 2), c + (w / 2, d / 2), c + (-w / 2, d / 2)])
            per = perimeter(rect, 1.0)
            if seg_dist(per, net.road_seg).min() < road_gap:
                continue
            if len(net.drive_seg) and seg_dist(per, net.drive_seg).min() < 2.5:
                continue
            if any(polys_overlap(rect, q, lot_gap) for q in polys):
                continue
            score = np.linalg.norm(c - centre)
            if best is None or score < best[0]:
                best = (score, c, rect)
    return best[1:] if best else None


def _convex(poly):
    cr = [np.cross(poly[(i + 1) % 4] - poly[i], poly[(i + 2) % 4] - poly[(i + 1) % 4]) for i in range(4)]
    return all(c > 1e-6 for c in cr)


def _share_borders(live, valid_poly, share, seed, log, max_gap=24.0):
    """Side-by-side lots on the same road (nearly parallel, close) get ONE border: both move onto the
    line half-way between them; the left lot of the pair keeps that fence side, the right one skips it.
    `share` = the fraction of candidate pairs that are joined."""
    import random
    rng = random.Random(seed)
    pairs = []
    for A in live:
        if A.hero:
            continue
        best = None
        for B in live:
            if B is A or B.hero or float(A.d @ B.d) < math.cos(math.radians(15)):
                continue
            u, v = A.local(B.j)
            if u <= 0 or abs(v) > 12:
                continue
            ca, cb = A.corners(), B.corners()
            gf, gb = np.linalg.norm(ca[1] - cb[0]), np.linalg.norm(ca[2] - cb[3])
            if gf < max_gap and gb < max_gap + 4 and (best is None or gf < best[0]):
                best = (gf, B)
        if best:
            pairs.append((A, best[1]))
    rng.shuffle(pairs)
    joined = 0
    for A, B in pairs:
        if rng.random() > share or hasattr(A, "shared_right") or hasattr(B, "shared_left"):
            continue
        ca, cb = A.corners(), B.corners()
        fm0, bm = (ca[1] + cb[0]) / 2, (ca[2] + cb[3]) / 2
        others = [o for o in live if o is not A and o is not B]
        along = (bm - fm0) / max(np.linalg.norm(bm - fm0), 1e-9)
        for shift in np.arange(0.0, 5.01, 0.5):      # on a curve the mid front corner can be too near the road
            fm = fm0 + along * shift
            qa = np.array([ca[0], fm, bm, ca[3]])
            qb = np.array([fm, cb[1], cb[2], bm])
            if _convex(qa) and _convex(qb) and valid_poly(A, qa, others) and valid_poly(B, qb, others):
                break
        else:
            log("lots %d | %d can't share a border (not clear of roads / driveways / other lots)" % (A.idx, B.idx))
            continue
        A.quad, B.quad = qa, qb
        B.skip.add(4)
        A.shared_right, B.shared_left = B.idx, A.idx
        # the rectangle the yard is laid out in stays inside the quad
        A.wr = min(A.local(fm)[0], A.local(bm)[0])
        B.wl = min(-B.local(fm)[0], -B.local(bm)[0])
        A.v1 = min(A.v1, A.local(bm)[1])
        B.v1 = min(B.v1, B.local(bm)[1])
        joined += 1
        log("lots %d | %d share a border" % (A.idx, B.idx))
    log("%d shared borders" % joined)


# ------------------------------------------------------------------ polyline helpers
def resample(line, step):
    """Points every `step` metres along a polyline (n, 2), with their tangents."""
    seg = np.diff(line, axis=0)
    ln = np.linalg.norm(seg, axis=1)
    total = ln.sum()
    s = np.arange(0.0, total + 1e-6, step)
    cum = np.concatenate([[0], np.cumsum(ln)])
    pts, tans = [], []
    for x in s:
        i = min(np.searchsorted(cum, x, side="right") - 1, len(seg) - 1)
        t = (x - cum[i]) / max(ln[i], 1e-9)
        pts.append(line[i] + seg[i] * t)
        tans.append(seg[i] / max(ln[i], 1e-9))
    return np.array(pts), np.array(tans), total


def offset_line(line, off):
    """The polyline moved `off` metres to its left (mitred joints, capped for sharp turns)."""
    n = len(line)
    out = []
    for i in range(n):
        ts = []
        if i > 0:
            ts.append(line[i] - line[i - 1])
        if i < n - 1:
            ts.append(line[i + 1] - line[i])
        ts = [t / max(np.linalg.norm(t), 1e-9) for t in ts]
        nrm = [np.array([-t[1], t[0]]) for t in ts]
        m = sum(nrm)
        m = m / max(np.linalg.norm(m), 1e-9)
        scale = 1.0 / max(float(np.dot(m, nrm[0])), 0.5)
        out.append(line[i] + m * off * scale)
    return np.array(out)


def densify(line, step=2.0):
    pts, _, _ = resample(line, step)
    if np.linalg.norm(pts[-1] - line[-1]) > 1e-3:
        pts = np.vstack([pts, line[-1]])
    return pts
