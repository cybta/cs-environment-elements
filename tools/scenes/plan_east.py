"""Shrink the user's east-side drawing to the size they want, place it on the real terrain, and redraw it.

    "C:/Program Files/Inkscape/bin/python.exe" plan_east.py ["House 10" 650]     (lot name + its area in m2)

The user liked the layout but drew it far too big (2026-11-25: "make it ~7 times smaller, House 10's land 650 m2,
keep the streets and the shapes"). Everything in out/east_drawn.json (read_east_drawing.py) is scaled by one factor F
about a centre C, except what has a real size: roads stay 7 m wide, driveways 3 m, and the bridge end of the bridge
road stays where the bridge is.
- F: the named lot, once trimmed back from the 7 m road (the drawn lot lines ran along the road edges, which come
  closer after scaling), comes out at the asked area.
- C: on the bridge road, as close to the bridge as the flat land allows (the user keeps the east side near the
  river): every lot and parking pad 99 % on flat land and out of the water, every building fully on flat land. The
  bridge road keeps its line and simply gets longer.
- Buildings: the pictures' roof rectangles scaled the same (at this scale the pictures' cars are life size), nudged
  off the road where the wider road now touches them. The drawn driveway stubs are dropped: every house and villa
  gets a 3 m driveway from its front straight to the road. The house / villa rectangles here are the user's pictures;
  make_east.py builds smaller ones 4 m behind the gate and redraws out/east_plan.png with what it built.
- Lots: straight sides between their real corners, shared exactly with the neighbours, clear of the sidewalks, and
  on the sidewalk's edge along a straight street (east_lots.py; user, 2026-11-25: "fences should be completely
  straight", "aligned with the sidewalk").
- Cul-de-sacs (CUL_DE_SACS, user 2026-11-25): the road ending by House 5 runs straight and stops square where its
  curled end reached ("flat_ends"); a fountain spot in front of it on a paved plaza; the no-build lane runs on straight
  ("cul_de_sacs": cut, dir, fountain, plaza, lane).
- Shop rows: SHOP_W x SHOP_D shops; a row faces its parking (keeping the drawn back line) or, listed in FACE_STREET,
  the street (turned round, its own sidewalk meeting the street's at the edge of its pad).
Writes out/east_plan.json (Blender metres) and out/east_plan.png (6 px = 1 m, north up; east_plan_render.py).
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from east_lots import straighten
from east_plan_render import render
from east_raster import dp, outline, poly_area

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
D = json.load(open(os.path.join(OUT, "east_drawn.json")))
PROJECT = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
MASKS = os.path.join(PROJECT, "blender_src", "terrain", "out")
S = 6                                         # px per metre for the raster work and the sheet
ROAD_W, DRIVE_W = 7.0, 3.0
SIDEWALK_W = 1.8                              # each side of a street (not on parking accesses and back roads)
CORRIDOR_W = ROAD_W + 2 * SIDEWALK_W          # the lots and parking start at the sidewalk's outer edge
CLASSES = {"asphalt": 1, "sidewalk": 2, "parking": 3, "driveway": 4}     # out/east_plan_surfaces.png = class x 50
TARGET = (sys.argv[1], float(sys.argv[2])) if len(sys.argv) > 2 else ("House 10", 650.0)
SHOP_W, SHOP_D = 7.0, 8.0                     # each shop, wide x deep (user, 2026-11-25); a row keeps its back line
# the user's added roads (2026-11-25): from the main road up the west side of a shop row's parking, into its back
BACK_ROADS = ["Shops 1-3"]
VERGE = 1.0                                   # between a back road's edge and the parking
# shop rows that face the street, not their parking (user, 2026-11-25: "the shopping center near the river is facing
# the parking, it should face the road"): turned round, their own sidewalk meets the street's at the pad's edge
FACE_STREET = ["Shops 1-3"]
SHOP_WALK = 2.75                              # a row's own sidewalk in front of its walls (shop_extras 2.6 + half wall)
# the user's cul-de-sac (2026-11-25, screenshot of Houses 4-6): the road that ends by the named lot no longer curls
# round at its end; it runs straight on to where that end's asphalt reached and stops square, a fountain stands in
# front of it on its centreline (a placeholder now: "a small fountain later") on a paved plaza, and the street's
# no-build strip runs on straight LANE m, so the lots either side keep straight fences on the sidewalk's line
CUL_DE_SACS = ["House 5"]
FOUNTAIN_R = 3.8                              # m: the user's circle
FOUNTAIN_GAP = 2.5                            # m from the road's square end to the fountain's rim
LANE = 30.0                                   # m: how far the no-build strip goes on past the road's end

def merge_through(lines, tol=2.5):
    """Join polylines end to end wherever exactly two of them meet (dropping the 3 m stubs leaves such joints)."""
    lines = [[tuple(p) for p in pts] for pts in lines]
    while True:
        ends = [(i, j) for i in range(len(lines)) for j in (0, -1)]
        for i, j in ends:
            p = lines[i][j]
            near = [(k, m) for k, m in ends if (k, m) != (i, j) and math.dist(lines[k][m], p) < tol]
            if len(near) == 1 and near[0][0] != i:
                k, m = near[0]
                a = lines[i] if j == -1 else lines[i][::-1]          # a ends at the joint
                b = lines[k] if m == 0 else lines[k][::-1]           # b starts at it
                joint = ((a[-1][0] + b[0][0]) / 2, (a[-1][1] + b[0][1]) / 2)
                lines = [pts for n, pts in enumerate(lines) if n not in (i, k)] + [a[:-1] + [joint] + b[1:]]
                break
        else:
            return lines


def smooth(pts, step=2.0, half=6):
    """Resample every step m and average over +-half samples (ends fixed): irons out the kinks the traced
    centreline has where a (now dropped) driveway used to branch off; real curves are much wider than that."""
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(math.dist(a, b) / step))
        out += [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(1, n + 1)]
    sm = []
    for i in range(len(out)):
        h = min(half, i, len(out) - 1 - i)
        win = out[i - h:i + h + 1]
        sm.append((sum(p[0] for p in win) / len(win), sum(p[1] for p in win) / len(win)))
    return [tuple(round(v, 2) for v in p) for p in dp(sm, 0.1)]


_anchor = next(tuple(r["pts"][r["bridge_end"]]) for r in D["roads"] if "bridge_end" in r)
roads = [dict(pts=smooth(pts)) for pts in merge_through([r["pts"] for r in D["roads"] if r["width"] >= ROAD_W])]
bridge = min(roads, key=lambda r: min(math.dist(r["pts"][0], _anchor), math.dist(r["pts"][-1], _anchor)))
bridge["bridge_end"] = 0 if math.dist(bridge["pts"][0], _anchor) < math.dist(bridge["pts"][-1], _anchor) else -1
bridge["pts"][bridge["bridge_end"]] = _anchor
ANCHOR = _anchor
flat_t = np.asarray(Image.open(os.path.join(MASKS, "valley_flat_mask.png")).convert("L")) > 127
water_t = np.asarray(Image.open(os.path.join(MASKS, "valley_water_mask.png")).convert("L")) > 127
TR, TC = flat_t.shape


class Grid:
    """A raster over a world box, S px per metre, row 0 = north."""

    def __init__(self, pts, margin):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.x0, self.y1 = min(xs) - margin, max(ys) + margin
        self.w = int(math.ceil((max(xs) + margin - self.x0) * S))
        self.h = int(math.ceil((self.y1 - min(ys) + margin) * S))

    def px(self, p):
        return ((p[0] - self.x0) * S, (self.y1 - p[1]) * S)

    def world(self, q):
        return (round(self.x0 + q[0] / S, 2), round(self.y1 - q[1] / S, 2))

    def lines(self, polylines, width_m, caps=None):
        """Thick polylines, round-ended unless `caps[i]` = (round start?, round end?) says square."""
        img = Image.new("L", (self.w, self.h), 0)
        d, w = ImageDraw.Draw(img), width_m * S
        for i, pts in enumerate(polylines):
            q = [self.px(p) for p in pts]
            d.line(q, fill=255, width=int(round(w)), joint="curve")
            for (x, y), rnd in zip((q[0], q[-1]), caps[i] if caps else (True, True)):
                if rnd:
                    d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
        return np.asarray(img) > 0

    def poly(self, pts):
        img = Image.new("L", (self.w, self.h), 0)
        ImageDraw.Draw(img).polygon([self.px(p) for p in pts], fill=255)
        return np.asarray(img) > 0


def scaled(p, F, C):
    return (C[0] + F * (p[0] - C[0]), C[1] + F * (p[1] - C[1]))


def scaled_roads(F, C):
    out = []
    for r in roads:
        pts = [scaled(p, F, C) for p in r["pts"]]
        if r is bridge:
            pts[r["bridge_end"]] = ANCHOR                        # the bridge doesn't move
        out.append(pts)
    return out


def terrain_frac(poly):
    """Share of a world polygon on flat land, and in water (terrain masks: 1 px = 1 m, centred on the origin)."""
    cols, rows = [p[0] + TC / 2 for p in poly], [TR / 2 - p[1] for p in poly]
    c0, c1 = max(int(min(cols)) - 1, 0), min(int(max(cols)) + 2, TC)
    r0, r1 = max(int(min(rows)) - 1, 0), min(int(max(rows)) + 2, TR)
    img = Image.new("L", (c1 - c0, r1 - r0), 0)
    ImageDraw.Draw(img).polygon([(c - c0, r - r0) for c, r in zip(cols, rows)], fill=255)
    m = np.asarray(img) > 0
    if not m.any():
        return 1.0, 0.0
    return float(flat_t[r0:r1, c0:c1][m].mean()), float(water_t[r0:r1, c0:c1][m].mean())


# ------------------------------------------------------------------ F: the target lot's area after the road trim
target = next(L for L in D["lots"] if L["name"] == TARGET[0])


def trimmed_area(F):
    C = target["outline"][0]
    poly = [scaled(p, F, C) for p in target["outline"]]
    g = Grid(poly, 12)
    m = g.poly(poly) & ~g.lines(scaled_roads(F, C), CORRIDOR_W)
    return poly_area(outline(m, 1, eps=0.25 * S, min_gap=0.5 * S)) / S / S      # as the saved outline measures


lo, hi = 0.1, 1.0
for _ in range(30):
    F = (lo + hi) / 2
    lo, hi = (F, hi) if trimmed_area(F) < TARGET[1] else (lo, F)
F = round((lo + hi) / 2, 4)

# ------------------------------------------------------------------ C: closest to the bridge that stays on flat land
bp = bridge["pts"] if bridge["bridge_end"] == 0 else bridge["pts"][::-1]
cands = []
for a, b in zip(bp, bp[1:]):
    n = max(1, int(math.dist(a, b) / 2))
    cands += [(a[0] + (b[0] - a[0]) * t / n, a[1] + (b[1] - a[1]) * t / n) for t in range(n)]
cands.append(tuple(bp[-1]))
buildings = [(L["name"], L["drawn_building"]["corners"]) for L in D["lots"]] + \
            [(s["name"], s["corners"]) for s in D["shop_rows"]]
areas = [(L["name"] + " lot", L["outline"]) for L in D["lots"]] + \
        [("parking %d" % i, p["outline"]) for i, p in enumerate(D["parking"])]


def misfits(C):
    """What would sit off the flat land (or in water) with the shrink centred on C."""
    bad = []
    for name, poly in areas:
        f, w = terrain_frac([scaled(p, F, C) for p in poly])
        if f < 0.99 or w > 0:
            bad.append("%s %d%% flat" % (name, 100 * f))
    for name, poly in buildings:
        f, w = terrain_frac([scaled(p, F, C) for p in poly])
        if f < 0.999 or w > 0:
            bad.append("%s building %d%% flat" % (name, 100 * f))
    for i, (pts, r) in enumerate(zip(scaled_roads(F, C), roads)):    # roads on flat land too (not the bridge
        if r is bridge:                                                  # road: it crosses the river)
            continue
        off = 0
        for a, b in zip(pts, pts[1:]):
            n = max(1, int(math.dist(a, b) / 3))
            for t in range(n + 1):
                col = int(a[0] + (b[0] - a[0]) * t / n + TC / 2)
                row = int(TR / 2 - (a[1] + (b[1] - a[1]) * t / n))
                off += not flat_t[row, col] or water_t[row, col]
        if off:
            bad.append("road %d: %d points off flat land" % (i, off))
    return bad


C = next((c for c in cands if not misfits(c)), None)
if C is None:
    best = min(cands, key=lambda c: len(misfits(c)))
    raise SystemExit("no centre on the bridge road keeps everything on flat land; the best, (%.1f, %.1f), still "
                     "has: %s" % (best[0], best[1], "; ".join(misfits(best))))
C = (round(C[0], 2), round(C[1], 2))

# ------------------------------------------------------------------ the plan
def inside(p, poly):
    x, y, c = p[0], p[1], False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[i - 1]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            c = not c
    return c


def sidewalked(polylines):
    """Streets get sidewalks; a road that ends inside a parking pad is its access and gets none (a kerb ring
    round its end would close the entrance)."""
    pads_now = [[scaled(q, F, C) for q in p["outline"]] for p in D["parking"]]

    def near_pad(p, pad, reach=4.0):                  # (a traced centreline stops short of the drawn end)
        if inside(p, pad):
            return True
        for a, b in zip(pad, pad[1:] + pad[:1]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1e-9)))
            if math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy) < reach:
                return True
        return False
    ends = [(i, pts[j]) for i, pts in enumerate(polylines) for j in (0, -1)]

    def free(i, p):                                   # meets no other road (a junction end always does)
        return not any(k != i and math.dist(p, q) < 3.0 for k, q in ends)
    return [not any(free(i, end) and near_pad(end, pad) for end in (pts[0], pts[-1]) for pad in pads_now)
            for i, pts in enumerate(polylines)]


def cut_ends(sroads):
    """The user's cul-de-sacs (CUL_DE_SACS): the road whose free end is nearest the named lot runs straight (the line
    fitted through its straight run and on through the junction it starts from) to where its curled end's asphalt
    reached, and stops square there; the fountain stands FOUNTAIN_GAP further on, on that line, on a plaza the width
    of the street and its sidewalks; the no-build lane goes on LANE m. Returns the roads, their square ends
    {(road, 0 | -1)} and the cul-de-sacs (for the plan)."""
    sroads = [[tuple(p) for p in pts] for pts in sroads]
    ends = [(i, j) for i in range(len(sroads)) for j in (0, -1)]

    def free(i, j):
        return not any(k != i and math.dist(sroads[i][j], sroads[k][m]) < 3.0 for k, m in ends)
    flats, cds = set(), []
    for near in CUL_DE_SACS:
        lot = next(L for L in D["lots"] if L["name"] == near)
        c = np.mean([scaled(p, F, C) for p in lot["outline"]], axis=0)
        i, j = min(((i, j) for i, j in ends if free(i, j)), key=lambda e: math.dist(sroads[e[0]][e[1]], c))
        pts = np.array(sroads[i] if j == -1 else sroads[i][::-1], float)          # running toward the end
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        from_end = np.concatenate([np.cumsum(seg[::-1])[::-1], [0.0]])
        run = [p for p, s in zip(pts, from_end) if s >= 8.0]                       # the straight run before the curl
        J = pts[0]
        heading = run[-1] - run[0]
        for k, other in enumerate(sroads):                                         # and straight on through the
            for m in (0, -1):                                                      # junction it comes from
                if k == i or math.dist(other[m], J) >= 3.0:
                    continue
                o = np.array(other if m == 0 else other[::-1], float)
                far = [p for p in o if 3.0 < math.dist(p, J) < 22.0]
                if far and np.dot(far[-1] - J, -heading) > 0.97 * np.linalg.norm(far[-1] - J) * np.linalg.norm(heading):
                    run += far
        P = np.array(run)
        m0 = P.mean(0)
        d = np.linalg.svd(P - m0)[2][0]
        d = d if np.dot(d, heading) > 0 else -d
        reach = max(float(np.dot(p - m0, d)) for p in pts) + ROAD_W / 2         # how far the old end's asphalt went
        E = m0 + d * reach
        Ja = tuple(np.round(m0 + d * float(np.dot(J - m0, d)), 2))              # from the junction, on the line
        sroads[i] = [Ja, tuple(np.round(E, 2))] if j == -1 else [tuple(np.round(E, 2)), Ja]
        flats.add((i, j))
        fc = m0 + d * (reach + FOUNTAIN_GAP + FOUNTAIN_R)
        n, h = np.array([-d[1], d[0]]), CORRIDOR_W / 2
        plaza = [E + n * h] + [fc + h * (math.cos(a) * n + math.sin(a) * d) for a in np.linspace(0, math.pi, 13)] \
            + [E - n * h]
        r2 = lambda v: [round(float(v[0]), 2), round(float(v[1]), 2)]
        cds.append(dict(near=near, road=i, end=j, cut=r2(E), dir=[round(float(v), 4) for v in d],
                        fountain=dict(centre=r2(fc), r=FOUNTAIN_R), plaza=[r2(p) for p in plaza],
                        lane=[r2(E), r2(m0 + d * (reach + LANE))]))
    return sroads, flats, cds


def caps_of(flats, n):
    return [((i, 0) not in flats, (i, -1) not in flats) for i in range(n)]


def trim(poly):
    """A scaled polygon minus the road corridor, back as a polygon (world)."""
    m = g.poly(poly) & ~corridor
    return [g.world(q) for q in outline(m, 1, eps=0.25 * S, min_gap=0.5 * S)], m


def lay_out_lots():
    lots = []
    for L in D["lots"]:
        poly, m = trim([scaled(p, F, C) for p in L["outline"]])
        lots.append(dict(name=L["name"], kind=L["kind"], outline=poly, mask=m, label=scaled(L["label"], F, C),
                         drawn=L["drawn_building"]))
    # one line per shared fence: corners of neighbouring lots within 1 m become one corner
    groups = []
    for li, L in enumerate(lots):
        for i, p in enumerate(L["outline"]):
            for grp in groups:
                q = lots[grp[0][0]]["outline"][grp[0][1]]
                if math.dist(p, q) < 1.0 and all(m != li for m, _ in grp):
                    grp.append((li, i))
                    break
            else:
                groups.append([(li, i)])
    for grp in groups:
        if len(grp) > 1:
            ax = round(sum(lots[n]["outline"][i][0] for n, i in grp) / len(grp), 2)
            ay = round(sum(lots[n]["outline"][i][1] for n, i in grp) / len(grp), 2)
            for n, i in grp:
                lots[n]["outline"][i] = (ax, ay)
    return lots


tries = []                      # the final raster + shared corners move the area a little: correct F on it, and
for k in range(7):              # keep the closest try (the raster makes it jitter by a few m2)
    sroads, flats, cds = cut_ends(scaled_roads(F, C))
    everything = [p for pts in sroads for p in pts] + [scaled(p, F, C) for _, poly in areas for p in poly]
    g = Grid(everything, 25)
    walk = sidewalked(sroads)
    caps = caps_of(flats, len(sroads))
    asphalt = g.lines(sroads, ROAD_W, caps)
    paved = asphalt | g.lines([p for p, w in zip(sroads, walk) if w], CORRIDOR_W,
                              [c for c, w in zip(caps, walk) if w])
    for cd in cds:
        paved |= g.poly(cd["plaza"])
    corridor = paved | g.lines([cd["lane"] for cd in cds], CORRIDOR_W, [(False, False)] * len(cds))
    lots = lay_out_lots()
    got = poly_area(next(L for L in lots if L["name"] == TARGET[0])["outline"])
    tries.append((abs(got - TARGET[1]), F))
    best = min(tries)[1]
    if abs(got - TARGET[1]) <= 1.5 or (k == 6 and F == best):
        break
    F = best if k >= 5 else round(F * math.sqrt(TARGET[1] / got) + 0.0001 * (k % 2), 4)
left = misfits(C)
if left:
    print("WARNING, off the flat land after the last size correction:", "; ".join(left))
# straight sides between the real corners, neighbours sharing theirs, clear of the sidewalks (east_lots.py)
for L, o in zip(lots, straighten([L["outline"] for L in lots],
                                 [(p, ROAD_W / 2 + (SIDEWALK_W if w else 0.0)) for p, w in zip(sroads, walk)] +
                                 [(cd["lane"], CORRIDOR_W / 2) for cd in cds])):
    L["outline"], L["mask"] = o, g.poly(o)


def rect_of(corners_w, front_dir):
    """Scaled rectangle from 4 world corners: centre, width along the front side, depth, front direction."""
    cs = [scaled(p, F, C) for p in corners_w]
    cx, cy = sum(p[0] for p in cs) / 4, sum(p[1] for p in cs) / 4
    e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
    ux, uy = (cs[1][0] - cs[0][0]) / e1, (cs[1][1] - cs[0][1]) / e1      # along the first edge
    along_first = abs(ux * front_dir[0] + uy * front_dir[1]) < 0.5            # first edge runs along the front
    return dict(c=(cx, cy), width=e1 if along_first else e2, depth=e2 if along_first else e1, front=front_dir)


def rect_corners(r):
    fx, fy = r["front"]
    sx, sy = fy, -fx                                             # along the front side
    hw, hd = r["width"] / 2, r["depth"] / 2
    return [(r["c"][0] + a * hw * sx + b * hd * fx, r["c"][1] + a * hw * sy + b * hd * fy)
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def nudge(r, inside=None):
    """Move a rectangle the least it takes (along its axes, <= 6 m) to clear the 7 m roads and stay in its lot."""
    fx, fy = r["front"]
    for dist in np.arange(0, 6.01, 0.25):
        for dx, dy in ((0, 0),) if dist == 0 else ((-fx, -fy), (fx, fy), (fy, -fx), (-fy, fx)):
            t = dict(r, c=(r["c"][0] + dx * dist, r["c"][1] + dy * dist))
            m = g.poly(rect_corners(t))
            if not (m & corridor).any() and (inside is None or (m & ~inside).sum() < 0.5 * S * S):
                return t, float(dist)
    return r, None


for L in lots:
    r = rect_of(L["drawn"]["corners"], L["drawn"]["front_dir"])
    r, moved = nudge(r, L["mask"])
    L.update(building=r, moved=moved, area=poly_area(L["outline"]))
    # driveway: from the middle of the front straight out to the asphalt, across the sidewalk (or to the nearest
    # road if that misses)
    fx, fy = r["front"]
    start = (r["c"][0] + fx * r["depth"] / 2, r["c"][1] + fy * r["depth"] / 2)
    end = None
    for t in np.arange(0.5, 40, 0.25):
        p = (start[0] + fx * t, start[1] + fy * t)
        x, y = g.px(p)
        if 0 <= x < g.w and 0 <= y < g.h and asphalt[int(y), int(x)]:
            end = (p[0] + fx * 0.3, p[1] + fy * 0.3)
            break
    if end is None:
        ys, xs = np.nonzero(asphalt[::3, ::3])
        sx, sy = g.px(start)
        k = np.argmin((xs * 3 - sx) ** 2 + (ys * 3 - sy) ** 2)
        end = g.world((xs[k] * 3, ys[k] * 3))
    L["drive"] = [tuple(round(v, 2) for v in start), tuple(round(v, 2) for v in end)]

shop_rows = []
for s in D["shop_rows"]:
    r = rect_of(s["corners"], s["front_dir"])
    fx, fy = r["front"]
    back = (r["c"][0] - fx * r["depth"] / 2, r["c"][1] - fy * r["depth"] / 2)
    r = dict(r, width=s["shops"] * SHOP_W, depth=SHOP_D, c=(back[0] + fx * SHOP_D / 2, back[1] + fy * SHOP_D / 2))
    street = s["name"] in FACE_STREET
    if street:                                 # turned round where it stands; onto the street once its pad is known
        r["front"] = (-fx, -fy)
    r, moved = nudge(r)
    shop_rows.append(dict(name=s["name"], shops=s["shops"], first=s["first_number"], building=r, moved=moved,
                          axis=s["axis_dir"], faces="street" if street else "parking", away=(fx, fy)))
pads = []
for p in D["parking"]:
    poly, m = trim([scaled(q, F, C) for q in p["outline"]])
    row = max(shop_rows, key=lambda s: (m & g.poly(rect_corners(s["building"]))).sum())     # whose parking it is
    b = row["building"]
    pads.append(dict(outline=poly, area=poly_area(poly) - b["width"] * b["depth"], label=scaled(p["label"], F, C),
                     shops=row["name"]))


def ray_to_edge(p, d, poly):
    """How far from p along d to the polygon's boundary (inf if it never gets there)."""
    best = math.inf
    for a, b in zip(poly, poly[1:] + poly[:1]):
        ex, ey = b[0] - a[0], b[1] - a[1]
        den = d[0] * ey - d[1] * ex
        if abs(den) < 1e-9:
            continue
        wx, wy = a[0] - p[0], a[1] - p[1]
        t, u = (wx * ey - wy * ex) / den, (wx * d[1] - wy * d[0]) / den
        if t > 0 and 0 <= u <= 1:
            best = min(best, t)
    return best


for row in shop_rows:                          # a street-facing row: its front SHOP_WALK in from its pad's edge
    if row["faces"] == "street":
        b = row["building"]
        reach = ray_to_edge(b["c"], b["front"], next(p for p in pads if p["shops"] == row["name"])["outline"])
        k = reach - SHOP_WALK - b["depth"] / 2
        b["c"] = (b["c"][0] + b["front"][0] * k, b["c"][1] + b["front"][1] * k)


def back_road(row, pad):
    """From the main road up the parking's west side (VERGE clear of it), then east into the back of the lot (the
    side away from the main road, whichever way the row faces)."""
    c, (ux, uy), (vx, vy) = row["building"]["c"], row["axis"], row["away"]
    if ux * vy - uy * vx < 0:                                   # u must run west -> east for the 'west' side
        ux, uy = -ux, -uy

    def uv(p):
        return ((p[0] - c[0]) * ux + (p[1] - c[1]) * uy, (p[0] - c[0]) * vx + (p[1] - c[1]) * vy)

    def xy(u, v):
        return (round(c[0] + u * ux + v * vx, 2), round(c[1] + u * uy + v * vy, 2))

    q = [uv(p) for p in pad["outline"]]
    u_road = min(u for u, _ in q) - ROAD_W / 2 - VERGE
    v_back = max(v for _, v in q)
    u_back = min(u for u, v in q if v > v_back - 1.0)             # where the back edge starts
    pts = [uv(p) for p in sroads[roads.index(bridge)]]
    for (u0, v0), (u1, v1) in zip(pts, pts[1:]):                  # meet the bridge road's centreline
        if (u0 - u_road) * (u1 - u_road) <= 0 and u0 != u1:
            v_start = v0 + (v1 - v0) * (u_road - u0) / (u1 - u0)
            break
    else:
        raise SystemExit("the %s back road doesn't meet the bridge road" % row["name"])
    v_turn = v_back - ROAD_W / 2
    return [xy(u_road, v_start), xy(u_road, v_turn), xy(u_back + ROAD_W / 2, v_turn)]


added = []
for name in BACK_ROADS:
    row = next(s for s in shop_rows if s["name"] == name)
    added.append(dict(for_shops=name, pts=back_road(row, next(p for p in pads if p["shops"] == name))))
for a in added:                                                  # it must stay on flat land (its full width)
    pts, off = a["pts"], 0
    for p, q in zip(pts, pts[1:]):
        n = max(1, int(math.dist(p, q) / 2))
        for t in range(n + 1):
            x, y = p[0] + (q[0] - p[0]) * t / n, p[1] + (q[1] - p[1]) * t / n
            h = ROAD_W / 2
            off += terrain_frac([(x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h)])[0] < 0.99
    if off:
        print("WARNING: the %s back road runs off the flat land (%d of its points)" % (a["for_shops"], off))
sroads = sroads + [a["pts"] for a in added]
walk = walk + [False] * len(added)                              # a back road is an access: no sidewalks
back = g.lines([a["pts"] for a in added], ROAD_W)
asphalt |= back
corridor |= back
paved |= back

# the surfaces for the scene builder (make_east.py): one class per pixel, the later class wins (the lane past a
# cul-de-sac's plaza is no-build but not paved)
cls = np.zeros(asphalt.shape, np.uint8)
cls[paved] = CLASSES["sidewalk"]
cls[g.lines([L["drive"] for L in lots], DRIVE_W)] = CLASSES["driveway"]
for p in pads:
    cls[g.poly(p["outline"])] = CLASSES["parking"]
cls[asphalt] = CLASSES["asphalt"]
Image.fromarray(cls * 50).save(os.path.join(OUT, "east_plan_surfaces.png"))

# ------------------------------------------------------------------ save + redraw
plan = dict(source="east_drawn.json", factor=F, centre=C, anchor=ANCHOR, target=dict(lot=TARGET[0], m2=TARGET[1]),
            road_width_m=ROAD_W, drive_width_m=DRIVE_W, roads=[[tuple(round(v, 2) for v in p) for p in pts]
                                                               for pts in sroads],
            lots=[], shop_rows=[], parking=[], park_label=scaled(D["park_label"], F, C), added_roads=added,
            shop_size_m=[SHOP_W, SHOP_D], sidewalk_width_m=SIDEWALK_W, road_sidewalks=walk,
            flat_ends=sorted([i, j] for i, j in flats), cul_de_sacs=cds,
            surfaces=dict(png="east_plan_surfaces.png", x0=round(g.x0, 3), y1=round(g.y1, 3), px_per_m=S,
                          classes=CLASSES, note="pixel value = class x 50; world x = x0 + (col + 0.5) / px_per_m, "
                                                "y = y1 - (row + 0.5) / px_per_m"))
for L in lots:
    r = L["building"]
    f, w = terrain_frac(L["outline"])
    plan["lots"].append(dict(name=L["name"], kind=L["kind"], outline=L["outline"], area_m2=round(L["area"]),
                             flat_pct=round(100 * f), label=L["label"], driveway=L["drive"],
                             building=dict(centre=r["c"], width_m=round(r["width"], 1), depth_m=round(r["depth"], 1),
                                           front_dir=r["front"], corners=rect_corners(r), nudged_m=L["moved"])))
for s in shop_rows:
    r = s["building"]
    plan["shop_rows"].append(dict(name=s["name"], shops=s["shops"], first_number=s["first"], centre=r["c"],
                                  length_m=round(r["width"], 1), depth_m=round(r["depth"], 1), front_dir=r["front"],
                                  axis_dir=s["axis"], corners=rect_corners(r), nudged_m=s["moved"],
                                  faces=s["faces"]))
for p in pads:
    plan["parking"].append(dict(outline=p["outline"], area_m2=round(p["area"]), label=p["label"],
                                for_shops=p["shops"]))
json.dump(plan, open(os.path.join(OUT, "east_plan.json"), "w"), indent=1)
render(os.path.join(OUT, "east_plan.png"), plan, g, S, flat_t, water_t, rect_corners)

print("factor %.4f (lengths x%.3f, areas x%.3f), centre (%.1f, %.1f), bridge end (%.1f, %.1f)" % (
    F, F, F * F, C[0], C[1], ANCHOR[0], ANCHOR[1]))
for L in plan["lots"]:
    b = L["building"]
    print("%-9s lot %5d m2  flat %3d%%  building %4.1f x %4.1f m%s  driveway %.1f m" % (
        L["name"], L["area_m2"], L["flat_pct"], b["width_m"], b["depth_m"],
        "" if not b["nudged_m"] else "  (moved %.2f m off the road)" % b["nudged_m"]
        if b["nudged_m"] is not None else "  (STILL ON THE ROAD)", math.dist(*L["driveway"])))
for s in plan["shop_rows"]:
    print("%s: %.1f x %.1f m (%d shops of %.1f m)%s" % (s["name"], s["length_m"], s["depth_m"], s["shops"],
                                                         s["length_m"] / s["shops"],
                                                         "" if not s["nudged_m"] else ", moved %s m" % s["nudged_m"]))
for p in plan["parking"]:
    print("parking %d m2" % p["area_m2"])
print("roads: %.0f m of 7 m road" % sum(math.dist(a, b) for pts in sroads for a, b in zip(pts, pts[1:])))
