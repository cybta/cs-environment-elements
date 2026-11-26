"""Read the user's drawing on the roads-only sheet (out/old_neighborhood_Edit.png) into map data, and redraw it
cleanly so we can check we read it the same way.

    python read_old_neighborhood_drawing.py        (system Python + Pillow)

Colours (the user's): fences red (194, 26, 26), houses grey (171), dirt roads + driveways beige-brown
(145, 135, 125); the old grey road (128) is left only where the drawing kept it (the road to the bridge).
Lot numbers are the user's labels (their positions are listed below, in sheet pixels).
Writes out/old_neighborhood_drawn.json (Blender metres) and out/old_neighborhood_drawn.png.
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SRC = os.path.join(OUT, "old_neighborhood_Edit.png")
MAP = json.load(open(os.path.join(OUT, "old_neighborhood_roads.json")))
S, X0, Y1 = MAP["px_per_m"], MAP["x0"], MAP["y1"]

# the user's lot numbers, read off the drawing (sheet pixels)
LABELS = {1: (902, 377), 2: (768, 350), 3: (627, 337), 4: (387, 327), 5: (202, 456), 6: (145, 674),
          7: (137, 842), 8: (536, 984), 9: (732, 1020), 10: (1041, 1047), 11: (1230, 1057),
          12: (1369, 1002), 13: (1415, 977), 14: (1125, 810), 15: (1160, 666), 16: (1002, 795),
          17: (1020, 639), 18: (775, 649), 19: (657, 582), 20: (503, 569)}
EXISTING = 3                               # the existing cottage (Cottage_70m2) is lot 3
PARK_LABEL, EMPTY_LABEL = (322, 1071), (563, 808)


def world(px, py):
    return (X0 + px / S, Y1 - py / S)


im = Image.open(SRC).convert("RGB")
W, H = im.size
px = im.load()


def is_red(c):
    return c[0] > 150 and c[0] - c[1] > 70 and c[0] - c[2] > 70


def is_house(c):
    return 160 <= c[0] <= 182 and abs(c[0] - c[1]) <= 3 and abs(c[0] - c[2]) <= 3


def is_dirt(c):
    return abs(c[0] - 145) <= 6 and abs(c[1] - 135) <= 6 and abs(c[2] - 125) <= 6


def mask(test):
    m = Image.new("L", im.size, 0)
    m.putdata([255 if test(c) else 0 for c in im.getdata()])
    return m


red, house, dirt = mask(is_red), mask(is_house), mask(is_dirt)
dirt_px = dirt.load()

# ------------------------------------------------------------------ houses: grey blobs -> rectangles
houses = []
hm = house.copy()
hp = hm.load()
for y in range(0, H, 3):
    for x in range(0, W, 3):
        if hp[x, y] != 255:
            continue
        ImageDraw.floodfill(hm, (x, y), 100)
        blob = hm.point(lambda v: 255 if v == 100 else 0)
        bx0, by0, bx1, by1 = blob.getbbox()
        bp = blob.load()
        pts = [(i, j) for j in range(by0, by1) for i in range(bx0, bx1) if bp[i, j]]
        ImageDraw.floodfill(hm, (x, y), 50)
        if len(pts) < 400:
            continue
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        sxx = sum((p[0] - cx) ** 2 for p in pts) / len(pts)
        syy = sum((p[1] - cy) ** 2 for p in pts) / len(pts)
        sxy = sum((p[0] - cx) * (p[1] - cy) for p in pts) / len(pts)
        a = 0.5 * math.atan2(2 * sxy, sxx - syy)
        ca, sa = math.cos(a), math.sin(a)
        us = [(p[0] - cx) * ca + (p[1] - cy) * sa for p in pts]
        vs = [-(p[0] - cx) * sa + (p[1] - cy) * ca for p in pts]
        houses.append(dict(c=(cx, cy), a=a, w=max(us) - min(us) + 1, h=max(vs) - min(vs) + 1,
                           du=(max(us) + min(us)) / 2, dv=(max(vs) + min(vs)) / 2, n=len(pts)))

# ------------------------------------------------------------------ lots: regions closed by the red lines
barrier = red.filter(ImageFilter.MaxFilter(5))
bar = Image.new("L", im.size, 255)
bar.paste(0, mask=barrier)


def region(seed, value):
    work = bar.copy()
    ImageDraw.floodfill(work, seed, value)
    reg = work.point(lambda v: 255 if v == value else 0)
    return reg


def ring(reg):
    """The region's outline as an ordered polygon (angle about its centre), simplified."""
    edge = reg.filter(ImageFilter.FIND_EDGES)
    ep = edge.load()
    bx0, by0, bx1, by1 = reg.getbbox()
    pts = [(i, j) for j in range(by0, by1) for i in range(bx0, bx1) if ep[i, j]]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    pts.sort(key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
    return _simplify_closed(pts, 6.0)


def _dp(pts, eps):
    if len(pts) < 3:
        return pts
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1e-9
    far, k = -1, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - x0) - dx * (pts[i][1] - y0)) / n
        if d > far:
            far, k = d, i
    if far <= eps:
        return [pts[0], pts[-1]]
    return _dp(pts[:k + 1], eps)[:-1] + _dp(pts[k:], eps)


def _simplify_closed(pts, eps):
    i = max(range(len(pts)), key=lambda k: (pts[k][0] - pts[0][0]) ** 2 + (pts[k][1] - pts[0][1]) ** 2)
    a = _dp(pts[:i + 1], eps)
    b = _dp(pts[i:] + [pts[0]], eps)
    poly = a[:-1] + b[:-1]
    # drop near-duplicate corners
    out = []
    for p in poly:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > 8:
            out.append(p)
    return out


def inside(p, poly):
    x, y, c = p[0], p[1], False
    for i in range(len(poly)):
        (x0, y0), (x1, y1) = poly[i], poly[i - 1]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            c = not c
    return c


lots = {}
for num, seed in LABELS.items():
    if bar.getpixel(seed) == 0:
        seed = (seed[0] + 12, seed[1] + 12)
    reg = region(seed, 77)
    area_px = sum(1 for v in reg.getdata() if v)
    if area_px > 0.25 * W * H:
        print("lot %d: its outline isn't closed (the fill leaked out)" % num)
        continue
    poly = ring(reg)
    lots[num] = dict(poly=poly, area_px=area_px)

# one line per shared fence: corners of different lots closer than SNAP px become one corner (their average)
SNAP = 14
corners = [(n, i) for n, L in lots.items() for i in range(len(L["poly"]))]
groups = []
for n, i in corners:
    p = lots[n]["poly"][i]
    for g in groups:
        q = lots[g[0][0]]["poly"][g[0][1]]
        if math.hypot(p[0] - q[0], p[1] - q[1]) < SNAP and all(m != n for m, _ in g):
            g.append((n, i))
            break
    else:
        groups.append([(n, i)])
for g in groups:
    if len(g) > 1:
        ax = sum(lots[n]["poly"][i][0] for n, i in g) / len(g)
        ay = sum(lots[n]["poly"][i][1] for n, i in g) / len(g)
        for n, i in g:
            lots[n]["poly"][i] = (ax, ay)


def seg_d(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ((dx * dx + dy * dy) or 1e-9)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy), t


# houses into lots
for h in houses:
    h["lot"] = next((n for n, L in lots.items() if inside(h["c"], L["poly"])), None)

# gates: the driveway dirt that comes INTO a lot marks where it crosses the fence (one gate per edge it enters
# through; 2.6 - 4 m wide, centred on that dirt)
dirt_pts = [(x, y) for y in range(0, H, 2) for x in range(0, W, 2) if dirt_px[x, y]]
for n, L in lots.items():
    poly = L["poly"]
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    near = {}
    for x, y in dirt_pts:
        if not (min(xs) <= x <= max(xs) and min(ys) <= y <= max(ys)) or not inside((x, y), poly):
            continue
        best = min((seg_d((x, y), poly[i], poly[(i + 1) % len(poly)]) + (i,) for i in range(len(poly))))
        dist, t, i = best
        if 4 <= dist <= 40:                       # inside the lot, within 5 m of the fence
            near.setdefault(i, []).append((t, dist))
    gates = []
    biggest = max((len(h) for h in near.values()), default=0)
    for i, hits in near.items():
        # the main driveway, plus a second one only if it's a real driveway (>= ~9 m2 of dirt inside),
        # not the road's ragged edge poking in
        if len(hits) < 60 or (len(hits) < biggest and (len(hits) < 150 or len(hits) < 0.4 * biggest)):
            continue
        a, b = poly[i], poly[(i + 1) % len(poly)]
        ln = math.hypot(b[0] - a[0], b[1] - a[1])
        close = sorted(t for t, dist in hits if dist <= 20) or sorted(t for t, _ in hits)
        mid = close[len(close) // 2]
        width = min(max((close[-1] - close[0]) * ln / S, 2.6), 4.0)
        half = width * S / 2 / ln
        gates.append(dict(side=i + 1, t0=max(mid - half, 0.02), t1=min(mid + half, 0.98), width=round(width, 1),
                          dirt_px=len(hits)))
    L["gates"] = sorted(gates, key=lambda g: -g["dirt_px"])

# door side: the house side whose outward normal points most toward the lot's (main) gate
for h in houses:
    cx, cy, a = h["c"][0], h["c"][1], h["a"]
    ca, sa = math.cos(a), math.sin(a)
    L = lots.get(h["lot"])
    target = None
    if L and L["gates"]:
        g = L["gates"][0]
        p0, p1 = L["poly"][g["side"] - 1], L["poly"][g["side"] % len(L["poly"])]
        tm = (g["t0"] + g["t1"]) / 2
        target = (p0[0] + (p1[0] - p0[0]) * tm, p0[1] + (p1[1] - p0[1]) * tm)
    best = None
    for su, sv, side in ((1, 0, "u+"), (-1, 0, "u-"), (0, 1, "v+"), (0, -1, "v-")):
        du = h["du"] + su * h["w"] / 2
        dv = h["dv"] + sv * h["h"] / 2
        mx, my = cx + du * ca - dv * sa, cy + du * sa + dv * ca
        nx, ny = su * ca - sv * sa, su * sa + sv * ca
        if target:
            tx, ty = target[0] - cx, target[1] - cy
            score = (nx * tx + ny * ty) / (math.hypot(tx, ty) or 1)
        else:
            score = 0
        if best is None or score > best[0]:
            best = (score, side, (mx, my))
    h["door_side"], h["door_px"] = best[1], best[2]

# shared fences: an edge that runs along another lot's outline (both ends and its middle within 8 px)
for n, L in lots.items():
    L["shared"] = []
    poly = L["poly"]
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        probe = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t) for t in (0.0, 0.25, 0.5, 0.75, 1.0)]
        for m, L2 in lots.items():
            q = L2["poly"]
            if m != n and all(min(seg_d(p, q[j], q[(j + 1) % len(q)])[0] for j in range(len(q))) < 8
                              for p in probe):
                L["shared"].append(dict(side=i + 1, with_lot=m))
                break

for n, L in lots.items():
    shared_sides = {x["side"] for x in L["shared"]}
    L["gates"] = [g for g in L["gates"] if g["side"] not in shared_sides]

# ------------------------------------------------------------------ save (map coordinates) + redraw
def poly_area_m2(poly):
    return abs(sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))) / 2 / S / S


data = dict(source=os.path.basename(SRC), lots=[], houses=[])
for n in sorted(lots):
    L = lots[n]
    data["lots"].append(dict(lot=n, existing=n == EXISTING, outline=[world(*p) for p in L["poly"]],
                             area_m2=round(poly_area_m2(L["poly"])), gates=L["gates"], shared=L["shared"]))
for h in houses:
    ca, sa = math.cos(h["a"]), math.sin(h["a"])
    corners = []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        du, dv = h["du"] + su * h["w"] / 2, h["dv"] + sv * h["h"] / 2
        corners.append(world(h["c"][0] + du * ca - dv * sa, h["c"][1] + du * sa + dv * ca))
    data["houses"].append(dict(lot=h["lot"], corners=corners, size_m=(round(h["w"] / S, 1), round(h["h"] / S, 1)),
                               door=world(*h["door_px"])))
data["park_label"], data["empty_label"] = world(*PARK_LABEL), world(*EMPTY_LABEL)
json.dump(data, open(os.path.join(OUT, "old_neighborhood_drawn.json"), "w"), indent=1)

# the clean redraw
out = Image.new("RGB", im.size, (246, 244, 238))
d = ImageDraw.Draw(out)
for gx in range(0, W, 80):
    d.line((gx, 0, gx, H), fill=(232, 229, 221))
for gy in range(0, H, 80):
    d.line((0, gy, W, gy), fill=(232, 229, 221))
grey = mask(lambda c: abs(c[0] - 128) <= 3 and abs(c[1] - 128) <= 3 and abs(c[2] - 128) <= 3)
out.paste((150, 150, 150), mask=grey)
out.paste((176, 150, 112), mask=dirt.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.MinFilter(15)))


def font(n):
    for f in ("arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


F, FB, FL = font(15), font(22), font(30)
for n, L in lots.items():
    poly = L["poly"]
    shared = {s["side"]: s["with_lot"] for s in L["shared"]}
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if i + 1 in shared and shared[i + 1] < n:
            continue                                   # drawn by the other lot
        col, w = ((230, 130, 20), 5) if i + 1 in shared else ((30, 110, 30), 3)
        if n == EXISTING and i + 1 not in shared:
            col = (90, 110, 170)
        d.line(a + b, fill=col, width=w)
    for g in L["gates"]:
        a, b = poly[g["side"] - 1], poly[g["side"] % len(poly)]
        p0 = (a[0] + (b[0] - a[0]) * g["t0"], a[1] + (b[1] - a[1]) * g["t0"])
        p1 = (a[0] + (b[0] - a[0]) * g["t1"], a[1] + (b[1] - a[1]) * g["t1"])
        d.line(p0 + p1, fill=(255, 220, 0), width=7)
for h in houses:
    ca, sa = math.cos(h["a"]), math.sin(h["a"])
    pts = []
    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        du, dv = h["du"] + su * h["w"] / 2, h["dv"] + sv * h["h"] / 2
        pts.append((h["c"][0] + du * ca - dv * sa, h["c"][1] + du * sa + dv * ca))
    d.polygon(pts, fill=(150, 70, 55) if h["lot"] != EXISTING else (90, 110, 170), outline=(60, 30, 20))
    x, y = h["door_px"]
    d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(220, 20, 20))
for n, L in lots.items():
    lx, ly = LABELS[n]
    hh = next((h for h in houses if h["lot"] == n), None)
    tx, ty = hh["c"] if hh else (lx, ly)
    d.text((tx, ty - 8), str(n), fill="white", font=FB, anchor="mm")
    d.text((tx, ty + 14), "%d m2" % round(poly_area_m2(L["poly"])), fill="white", font=F, anchor="mm")
d.text(PARK_LABEL, "PARK", fill=(40, 110, 40), font=FL, anchor="mm")
d.text(EMPTY_LABEL, "EMPTY (later)", fill=(120, 110, 90), font=FL, anchor="mm")
ly = H - 40
items = [((150, 70, 55), "house"), ((90, 110, 170), "existing cottage"), ((30, 110, 30), "fence"),
         ((230, 130, 20), "shared fence (built once)"), ((255, 220, 0), "gate (driveway through the fence)"),
         ((220, 20, 20), "front door side (faces the nearest road / driveway)"), ((176, 150, 112), "dirt road")]
x = 20
for col, label in items:
    d.rectangle((x, ly, x + 20, ly + 16), fill=col)
    d.text((x + 26, ly), label, fill="black", font=F)
    x += 36 + int(d.textlength(label, font=F))
d.line((W - 20 - 20 * S, ly + 8, W - 20, ly + 8), fill="black", width=3)
d.text((W - 20 - 10 * S, ly - 10), "20 m", fill="black", font=F, anchor="mm")
out.save(os.path.join(OUT, "old_neighborhood_drawn.png"))

print("houses: %d, lots: %d" % (len(houses), len(lots)))
for n in sorted(lots):
    L = lots[n]
    hs = [h for h in houses if h["lot"] == n]
    print("lot %2d: %4d m2, %d corners, houses %d %s, gates %s, shared sides %s" % (
        n, round(poly_area_m2(L["poly"])), len(L["poly"]), len(hs),
        ["%.1fx%.1f m" % (h["w"] / S, h["h"] / S) for h in hs],
        [g["width"] for g in L["gates"]], [(s["side"], s["with_lot"]) for s in L["shared"]]))
print("houses outside any lot:", [tuple(round(v) for v in h["c"]) for h in houses if h["lot"] is None])
