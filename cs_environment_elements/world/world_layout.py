"""World layout: where everything goes. Pure Python + numpy (no bpy), so it can be
planned (and drawn as a debug map) before anything is built.

The map is a square, -HALF..HALF metres on X (east) and Y (north), after the user's
reference in ref/: a poor district of old cottages round a dirt loop road (south-west),
a river winding from the west edge down to the south edge, a concrete road bridge, a
mid-range district of new houses on asphalt streets, three shops with parking by the
bridge, villas along the north road, a lake with a beach in the north-east (the
reference's sea, kept inside the map), and a mountain in the north-west whose summit
holds the hero Lebanese cedar, reached by a trail that winds up round it. A rim of
mountains closes the map on every side.
"""

import math
import random

import numpy as np

HALF = 700.0            # the map runs from -HALF to +HALF on X and Y
PLAY = 590.0            # invisible boundary wall: |x|, |y| (superellipse) stays inside this
WATER_Z = -1.2          # one water level for the river and the lake
TOWN_Z = 0.0            # the flattened town ground

# Road kinds: carriageway half width, sidewalk width, plot setback from the centre line
ROAD_KINDS = {
    "NEW": dict(hw=3.5, sidewalk=2.0),
    "OLD": dict(hw=3.2, sidewalk=0.0),
    "PATH": dict(hw=1.1, sidewalk=0.0),
    "TRAIL": dict(hw=1.0, sidewalk=0.0),
}
# Plot sizes per district: width along the road, depth, gap range, house setback
DISTRICTS = {
    "POOR": dict(w=21.0, d=24.0, gap=(1.5, 6.0), empty=0.1, row=0.8),
    "MID": dict(w=30.0, d=36.0, gap=(2.0, 6.0), empty=0.05, row=0.85),
    "VILLA": dict(w=56.0, d=60.0, gap=(3.0, 8.0), empty=0.0, row=0.0),
}
# row = chance that the next plot joins the one before it, side to side, sharing its fence


# --------------------------------------------------------------------------
# Polylines
# --------------------------------------------------------------------------

def catmull(ctrl, closed=False, step=2.0):
    """A smooth curve through the control points, resampled every `step` metres -> (N, 2)."""
    p = [np.asarray(c, float) for c in ctrl]
    if closed:
        p = [p[-1]] + p + [p[0], p[1]]
    else:
        p = [2 * p[0] - p[1]] + p + [2 * p[-1] - p[-2]]
    dense = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        n = max(4, int(np.linalg.norm(p2 - p1) / 0.5))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                                (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    dense.append(p[-2] if not closed else p[1])
    return resample(np.array(dense), step)


def resample(pts, step):
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    n = max(2, int(round(s[-1] / step)) + 1)
    t = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(t, s, pts[:, 0]), np.interp(t, s, pts[:, 1])], axis=1)


def tangents(pts, closed=False):
    if closed:
        d = np.roll(pts, -1, 0) - np.roll(pts, 1, 0)
    else:
        d = np.gradient(pts, axis=0)
    return d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)


def seg_dist(q, poly):
    """Distance from each point q (M, 2) to the polyline poly (N, 2) -> (M,)."""
    a, b = poly[:-1], poly[1:]
    ab = b - a
    L2 = np.maximum((ab ** 2).sum(1), 1e-12)
    ap = q[:, None, :] - a[None, :, :]
    t = np.clip((ap * ab[None]).sum(2) / L2[None], 0.0, 1.0)
    proj = a[None] + t[..., None] * ab[None]
    return np.sqrt(((q[:, None, :] - proj) ** 2).sum(2)).min(1)


def length(pts):
    return float(np.linalg.norm(np.diff(pts, axis=0), axis=1).sum())


def edge_r(x, y):
    """Superellipse 'radius' used for the rim and the boundary: square-ish with round corners."""
    p = 5.0
    return (np.abs(x) ** p + np.abs(y) ** p) ** (1.0 / p)


# --------------------------------------------------------------------------
# Layout pieces
# --------------------------------------------------------------------------

class Road:
    def __init__(self, name, kind, ctrl, closed=False, district=None, sides=(1, -1), z_bias=0.0,
                 plots=True, step=2.0):
        self.name, self.kind, self.closed = name, kind, closed
        self.pts = catmull(ctrl, closed, step)
        if closed:
            self.pts = self.pts[:-1]
        k = ROAD_KINDS[kind]
        self.hw, self.sidewalk = k["hw"], k["sidewalk"]
        self.district, self.sides, self.z_bias, self.with_plots = district, sides, z_bias, plots

    @property
    def outer(self):
        """Half width of everything the road owns (carriageway + sidewalk)."""
        return self.hw + self.sidewalk

    def loop_pts(self):
        return np.vstack([self.pts, self.pts[:1]]) if self.closed else self.pts


class Box:
    """An oriented rectangle: centre, unit axis u (width), half sizes. v = u turned +90°."""

    def __init__(self, center, u, hw, hd):
        self.c = np.asarray(center, float)
        self.u = np.asarray(u, float) / np.linalg.norm(u)
        self.v = np.array([-self.u[1], self.u[0]])
        self.hw, self.hd = hw, hd

    def corners(self):
        c, u, v = self.c, self.u * self.hw, self.v * self.hd
        return np.array([c - u - v, c + u - v, c + u + v, c - u + v])

    def samples(self, n=5):
        g = np.linspace(-1, 1, n)
        uu, vv = np.meshgrid(g, g)
        return self.c + uu.ravel()[:, None] * self.u * self.hw + vv.ravel()[:, None] * self.v * self.hd

    def overlaps(self, other, pad=0.0):
        for axis in (self.u, self.v, other.u, other.v):
            pa = self.corners() @ axis
            pb = other.corners() @ axis
            if pa.max() + pad <= pb.min() or pb.max() + pad <= pa.min():
                return False
        return True

    def local(self, p):
        d = np.asarray(p, float) - self.c
        return float(d @ self.u), float(d @ self.v)

    def world(self, u, v):
        return self.c + self.u * u + self.v * v

    @property
    def angle(self):
        return math.atan2(self.u[1], self.u[0])


class Plot(Box):
    """A house plot. u runs along the street, v from the street into the plot, so the
    street edge is at v = -hd ('front') and local (s, t) = (u, v + hd) is measured from it."""

    def __init__(self, center, along, w, d, district, road):
        super().__init__(center, along, w / 2, d / 2)
        self.w, self.d, self.district, self.road = w, d, district, road
        self.trees = []          # garden tree spots, filled in by world_sites
        self.shared = None       # "-u" / "+u": that side's fence belongs to the neighbour

    def at(self, s, t):
        """World point at s along the front (from the plot centre line) and t back from it."""
        return self.world(s, t - self.hd)

    @property
    def facing(self):
        """Angle of the direction from the plot to its street."""
        return math.atan2(-self.v[1], -self.v[0])


class Zone(Box):
    def __init__(self, name, kind, center, u, hw, hd, **extra):
        super().__init__(center, u, hw, hd)
        self.name, self.kind = name, kind
        self.extra = extra


class Layout:
    def __init__(self, seed):
        self.seed = seed
        self.roads, self.plots, self.zones = [], [], []
        self.river = None
        self.river_hw = 9.0
        self.lake = None          # (cx, cy, a, b, angle)
        self.lake_wave = ()       # (k, amplitude, phase): shoreline bays and points
        self.mountain = None      # (cx, cy, height, radius)
        self.summit = None        # (x, y)
        self.bridges = []         # filled by world_roads: (road, i0, i1)

    def road(self, name):
        return next(r for r in self.roads if r.name == name)

    def lake_q(self, x, y):
        """Normalised ellipse radius (1 on the shore) of the lake at x, y."""
        cx, cy, a, b, ang = self.lake
        dx, dy = x - cx, y - cy
        ca, sa = math.cos(ang), math.sin(ang)
        u = dx * ca + dy * sa
        v = -dx * sa + dy * ca
        th = np.arctan2(v / b, u / a)
        m = 1.0
        for k, amp, ph in self.lake_wave:
            m = m + amp * np.sin(k * th + ph)
        return np.sqrt((u / a) ** 2 + (v / b) ** 2) / m

    def mountain_h(self, x, y):
        cx, cy, h, r = self.mountain
        d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        return h * np.exp(-(np.maximum(d - 16.0, 0.0) / r) ** 2)


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------

def _jitter(rng, pts, amount):
    return [(x + rng.uniform(-amount, amount), y + rng.uniform(-amount, amount)) for x, y in pts]


def make_layout(seed=1, density=1.0):
    rng = random.Random(seed)
    L = Layout(seed)

    # ---- landscape ---------------------------------------------------------
    river = [(-780, 70), (-640, 90), (-560, 45), (-460, 70), (-360, 45), (-270, 35), (-205, -20),
             (-172, -95), (-130, -170), (-50, -235), (50, -262), (150, -290), (215, -350),
             (250, -440), (265, -560), (275, -780)]
    river = [river[0]] + _jitter(rng, river[1:-1], 6) + [river[-1]]
    L.river = catmull(river, step=6.0)
    L.lake = (455.0, 262.0, 82.0, 135.0, 0.22)
    L.lake_wave = tuple((k, rng.uniform(0.6, 1.0) * 0.2 / k ** 0.8, rng.uniform(0, 2 * math.pi))
                        for k in (2, 3, 4, 5, 7, 9))
    L.mountain = (-385.0, 365.0, 92.0, 98.0)
    L.summit = (-385.0, 365.0)

    # ---- roads ---------------------------------------------------------------
    pc = (-338.0, -192.0)                 # poor loop centre
    LA, LB = 158.0, 102.0                 # its half sizes
    loop = [(pc[0] + LA * math.cos(a), pc[1] + LB * math.sin(a))
            for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]
    L.roads.append(Road("Old Loop", "OLD", _jitter(rng, loop, 7), closed=True, district="POOR"))
    a = math.radians(40)
    joint = (pc[0] + LA * math.cos(a), pc[1] + LB * math.sin(a))
    L.roads.append(Road("Old Lane", "OLD", [joint, (-234, -108), (-226, -94)], district="POOR",
                        z_bias=0.004))
    L.roads.append(Road("Old Cross", "OLD", [(-484, -160), (-400, -153), (-300, -150), (-192, -163)],
                        district="POOR", z_bias=0.004))
    main = [(-232, -93), (-150, -80), (-60, -72), (60, -62), (180, -56), (262, -35), (300, 15),
            (312, 100), (296, 190), (240, 250), (140, 282), (20, 292), (-100, 292), (-195, 286)]
    L.roads.append(Road("Main Street", "NEW", main, district="MID"))
    L.roads.append(Road("Cross Street", "NEW", [(-72, -73), (-76, 60), (-80, 291)], district="MID",
                        z_bias=0.004))
    L.roads.append(Road("South Lane", "NEW", [(180, -57), (186, -130), (204, -200), (214, -232)],
                        district="MID", z_bias=0.004))
    L.roads.append(Road("Elm Street", "NEW", [(-75, 118), (40, 124), (160, 118), (308, 112)],
                        district="MID", z_bias=0.006))

    # Footpath from the poor loop over the river to the mountain trail, then the trail itself
    mx, my, mh, mr = L.mountain
    a0 = math.atan2(-231.0, 41.0)
    turns, r0, r1 = 1.1, 200.0, 20.0
    trail = []
    n = 40
    ph = [rng.uniform(0, 2 * math.pi) for _ in range(4)]
    for i in range(n + 1):
        t = i / n
        # clockwise (keeps clear of the villas), wandering in and out like a walked path
        ang = a0 - (t + 0.035 * math.sin(9.0 * t + ph[0])) * turns * 2 * math.pi
        wob = (1 - t) ** 0.6 * (16.0 * math.sin(7.0 * t * math.pi + ph[1]) + 7.0 * math.sin(17.0 * t + ph[2]))
        r = r0 + (r1 - r0) * t ** 0.9 + wob
        if 0 < i < n:
            ang += rng.uniform(-0.02, 0.02)
        trail.append((mx + r * math.cos(ang), my + r * math.sin(ang)))
    top = math.sqrt(1 - ((-330 - pc[0]) / LA) ** 2)
    path = [(-330, pc[1] + LB * top - 1), (-322, -62), (-341, -20), (-329, 40), (-346, 82), (-340, 112), trail[0]]
    L.roads.append(Road("River Path", "PATH", path, plots=False, z_bias=0.002))
    L.roads.append(Road("Cedar Trail", "TRAIL", trail, plots=False, step=2.0))

    # ---- zones (kept free of plots) ------------------------------------------
    Z = L.zones
    Z.append(Zone("Shops", "SHOPS", (-12, -96), (1, 0), 13.0, 13.0))
    Z.append(Zone("Parking", "PARKING", (-47, -98), (1, 0), 17.0, 15.0))
    Z.append(Zone("Shop Playground", "PLAYGROUND", (22, -103), (1, 0), 15.0, 14.0, style="SAND"))
    Z.append(Zone("Town Park", "PARK", (105, 30), (1, 0), 80.0, 33.0, fountain=True, playground=True))
    Z.append(Zone("Green", "PARK", (110, 198), (1, 0), 80.0, 26.0, fountain=False, playground=False))
    Z.append(Zone("Lakeside Park", "PARK", (352, 165), (0.2, 1), 26.0, 75.0, fountain=False,
                  playground=True, beach=True))
    Z.append(Zone("Old Playground", "PLAYGROUND", (pc[0], pc[1] - 32), (1, 0), 15.0, 11.0, style="DIRT"))
    Z.append(Zone("Old Park", "PARK", (-470, -288), (1, 0.4), 26.0, 22.0, fountain=False,
                  playground=False, old=True))
    Z.append(Zone("Summit", "SUMMIT", L.summit, (1, 0), 14.0, 14.0))

    _place_plots(L, rng, density)
    return L


# --------------------------------------------------------------------------
# Plots along the roads
# --------------------------------------------------------------------------

def _district_for(L, road, side_center, road_pt):
    if road.district == "POOR":
        return "POOR"
    if road.name == "Main Street":
        # the outer side of the big loop, north of the block: villas
        block = np.array([115.0, 110.0])
        outward = (side_center - road_pt) @ (road_pt - block) > 0
        if outward and road_pt[1] > 200 and road_pt[0] < 260:
            return "VILLA"
    return "MID"


def plot_ok(L, box, neighbor=None):
    q = box.samples(5)
    if np.any(edge_r(q[:, 0], q[:, 1]) > PLAY - 40):
        return False
    if np.any(L.mountain_h(q[:, 0], q[:, 1]) > 3.0):
        return False
    if seg_dist(q, L.river).min() < L.river_hw + 16:
        return False
    if np.min(L.lake_q(q[:, 0], q[:, 1])) < 1.45:
        return False
    for r in L.roads:
        clear = r.outer + 0.6
        d = seg_dist(q, r.loop_pts())
        if d.min() < clear:
            return False
    for z in L.zones:
        if box.overlaps(z, pad=3.0):
            return False
    for p in L.plots:
        if box.overlaps(p, pad=-0.05 if p is neighbor else 0.5):
            return False
    return True


def _place_plots(L, rng, density):
    for road in L.roads:
        if not road.with_plots:
            continue
        pts = road.pts
        tang = tangents(pts, road.closed)
        cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(road.loop_pts(), axis=0), axis=1))])
        total = cum[-1]
        for side in road.sides:
            s = 10.0
            prev = None
            while s < total - 10.0:
                if prev is not None and rng.random() < DISTRICTS[prev.district]["row"] * min(density, 1.0):
                    box = _next_in_row(L, rng, road, prev, side)
                    if box is not None:
                        L.plots.append(box)
                        s += box.w
                        prev = box
                        continue
                prev = None
                i = min(int(np.searchsorted(cum, s)), len(pts) - 1)
                p, t = pts[i], tang[i]
                nrm = np.array([-t[1], t[0]]) * side            # from the road into the plot
                probe = p + nrm * 20.0
                dist = _district_for(L, road, probe, p)
                spec = DISTRICTS[dist]
                w = spec["w"] * rng.uniform(0.92, 1.1)
                d = spec["d"] * rng.uniform(0.95, 1.08)
                setback = road.outer + 0.8
                center = p + nrm * (setback + d / 2) + t * 0.0
                # the plot's u axis must point so that v (u turned +90°) runs into the plot
                along = np.array([nrm[1], -nrm[0]])
                box = Plot(center, along, w, d, dist, road)
                if plot_ok(L, box):
                    if rng.random() < spec["empty"] / max(density, 0.05):
                        s += w + rng.uniform(*spec["gap"])          # an empty lot
                        continue
                    L.plots.append(box)
                    prev = box
                    s += w + rng.uniform(*spec["gap"]) / max(density, 0.2)
                else:
                    s += 3.0
    _cul_de_sacs(L)


def _next_in_row(L, rng, road, prev, side):
    """The next plot along the street, side to side with `prev` (same depth and turn).
    None when the street bends away or something is in the way: the row ends there."""
    spec = DISTRICTS[prev.district]
    w = spec["w"] * rng.uniform(0.92, 1.1)
    step = prev.u * side                                # along the street
    c = prev.c + step * (prev.hw + w / 2)
    box = Plot(c, prev.u, w, prev.d, prev.district, road)
    front = box.c - box.v * box.hd
    if seg_dist(front[None], road.loop_pts())[0] > road.outer + 3.0:
        return None                                     # the street curves away
    if not plot_ok(L, box, neighbor=prev):
        return None
    box.shared = "-u" if side > 0 else "+u"
    return box


def _cul_de_sacs(L):
    # Cul-de-sac estates at the dead ends of the main street and the south lane
    for road_name, dist in (("Main Street", "VILLA"), ("South Lane", "MID")):
        r = L.road(road_name)
        end, t = r.pts[-1], tangents(r.pts)[-1]
        spec = DISTRICTS[dist]
        w, d = spec["w"], spec["d"]
        center = end + t * (r.outer + 0.8 + d / 2)
        box = Plot(center, np.array([t[1], -t[0]]), w, d, dist, r)
        if plot_ok(L, box):
            L.plots.append(box)


# --------------------------------------------------------------------------
# Debug map (numpy RGB image, north up)
# --------------------------------------------------------------------------

def debug_map(L, size=700, heights=None):
    img = np.zeros((size, size, 3), np.float32)
    g = np.linspace(-HALF, HALF, size)
    X, Y = np.meshgrid(g, g)
    if heights is not None:
        h = heights
        img[..., 0] = img[..., 1] = img[..., 2] = np.clip(h / 120.0, 0, 1)
        img[..., 1] += 0.25
    else:
        img[...] = (0.55, 0.7, 0.45)
        m = L.mountain_h(X, Y) / L.mountain[2]
        img *= (1 - 0.5 * m)[..., None]
    rim = edge_r(X, Y) > PLAY
    img[rim] *= 0.6
    q = np.stack([X.ravel(), Y.ravel()], 1)

    def paint(mask, col):
        img[mask.reshape(size, size)] = col

    paint(L.lake_q(q[:, 0], q[:, 1]) < 1.0, (0.2, 0.4, 0.8))
    paint(_near(q, L.river, L.river_hw), (0.2, 0.4, 0.8))
    for z in L.zones:
        paint(_inside(q, z), {"PARK": (0.3, 0.6, 0.3), "PLAYGROUND": (0.85, 0.75, 0.5),
                              "SHOPS": (0.8, 0.4, 0.4), "PARKING": (0.5, 0.5, 0.5),
                              "SUMMIT": (0.9, 0.9, 0.2)}.get(z.kind, (1, 0, 1)))
    for p in L.plots:
        paint(_inside(q, p), {"POOR": (0.6, 0.45, 0.3), "MID": (0.75, 0.75, 0.6), "VILLA": (0.9, 0.9, 0.95)}[p.district])
    for r in L.roads:
        col = {"NEW": (0.15, 0.15, 0.15), "OLD": (0.45, 0.32, 0.2), "PATH": (0.7, 0.6, 0.4),
               "TRAIL": (0.7, 0.55, 0.3)}[r.kind]
        paint(_near(q, r.loop_pts(), max(r.outer, 1.5)), col)
    return img[::-1]                       # row 0 = north


def _near(q, poly, d):
    out = np.zeros(len(q), bool)
    lo, hi = poly.min(0) - d, poly.max(0) + d
    sel = np.all((q >= lo) & (q <= hi), axis=1)
    idx = np.nonzero(sel)[0]
    for k in range(0, len(idx), 3000):
        part = idx[k:k + 3000]
        out[part] = seg_dist(q[part], poly) < d
    return out


def _inside(q, box):
    d = q - box.c
    return (np.abs(d @ box.u) <= box.hw) & (np.abs(d @ box.v) <= box.hd)
