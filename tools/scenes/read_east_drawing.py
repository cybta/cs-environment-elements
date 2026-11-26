"""Read the user's east-side drawing into map data, and redraw it cleanly so we can check we read it the same way.

    "C:/Program Files/Inkscape/bin/python.exe" read_east_drawing.py
    (needs numpy + Pillow: Inkscape's bundled Python has both, the system Python has no numpy; ~3 min)

The drawing (out/east_roads_sizes-with-houses.png) is the sheet out/east_roads_sizes.png pasted on a bigger canvas at
the same scale (found by its black corner marks). On it the user drew:
- lot outlines in red (194, 26, 26); the roads redrawn in grey 128 (7 m), driveway stubs grey 150;
- top-down PICTURES of a villa and a house (one of each, copied and rotated) instead of filled footprints. They are
  not to scale: their cars are ~2.3x real size. The roof (dark pixels) is read as the drawn building;
- shop rows as grey 128 blocks with black dividers, on light grey parking pads (183, 184, 178);
- text labels: the lot names (seeds below, read by eye in drawing pixels), "Shop n", "parking", "Park".
Writes out/east_drawn.json (Blender metres; road centrelines included) and out/east_drawn.png.
plan_east.py then shrinks this to the size the user wants.
"""
import json
import math
import os

import numpy as np
from PIL import Image

from east_drawn_render import render                       # the redraw lives in its own module
from east_raster import centerlines, corners, dilate, dp, erode, label, min_rect, outline, poly_area, sides

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SRC = os.path.join(OUT, "east_roads_sizes-with-houses.png")
SHEET = os.path.join(OUT, "east_roads_sizes.png")
MAP = json.load(open(os.path.join(OUT, "east_roads_sizes.json")))
SIZES = json.load(open(os.path.join(HERE, "east_type_sizes.json")))
ANCHOR = json.load(open(os.path.join(HERE, "east_layout.json")))["anchor"]      # the bridge end of the bridge road
PROJECT = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
MASKS = os.path.join(PROJECT, "blender_src", "terrain", "out")
S, X0, Y1 = MAP["px_per_m"], MAP["x0"], MAP["y1"]
K = 3                                      # coarse grid for region work (3 px = 0.5 m)

# a point inside each lot (drawing pixels), read off the drawing; the name is the user's label
LOTS = {"Villa 1": (691, 576), "Villa 2": (1796, 530), "Villa 3": (2326, 507), "Villa 4": (2855, 530),
        "Villa 5": (3316, 576), "Villa 6": (3730, 875),
        "House 1": (2256, 1842), "House 2": (2648, 1911), "House 3": (2993, 2003), "House 4": (3339, 2187),
        "House 5": (3799, 2441), "House 6": (4052, 2095), "House 7": (3684, 1819), "House 8": (3270, 1612),
        "House 9": (2809, 1474), "House 10": (2510, 1382), "House 11": (2141, 1382)}
# the user's label for each lot (drawing pixels), reused for captions
LABELS = {"Villa 1": (638, 401), "Villa 2": (1582, 295), "Villa 3": (2174, 223), "Villa 4": (2742, 228),
          "Villa 5": (3235, 295), "Villa 6": (3785, 564), "House 11": (2171, 1163), "House 10": (2547, 1186),
          "House 9": (2887, 1271), "House 8": (3191, 1398), "House 7": (3730, 1639), "House 6": (4319, 1902),
          "House 1": (2261, 2010), "House 2": (2590, 2079), "House 3": (2931, 2231), "House 4": (3253, 2397),
          "House 5": (3949, 2648)}
# a point inside each shop block, and the axis its shops are numbered along (+x = west to east, +y = north to south)
SHOP_ROWS = {"Shops 1-3": ((967, 1542), 1, (1, 0)), "Shops 4-6": ((1842, 1703), 4, (0, 1))}
PARK_LABEL = (4260, 1174)

# the generator each building type maps to (east_type_sizes.json), drawn at its real size to show the scale
REAL = {"villa": next(r for r in SIZES if r["type"] == "VILLA_GABLE" and r["area"] == 260),
        "house": next(r for r in SIZES if r["type"] == "HOUSE" and r["area"] == 200),
        "shops": [r for r in SIZES if r["type"] == "SHOPS"]}

im = Image.open(SRC).convert("RGB")
A = np.asarray(im).astype(np.int16)
H, W = A.shape[:2]
R, G, B = A[:, :, 0], A[:, :, 1], A[:, :, 2]


def near(rgb, t):
    return (np.abs(R - rgb[0]) <= t) & (np.abs(G - rgb[1]) <= t) & (np.abs(B - rgb[2]) <= t)


def down(m):
    h, w = H // K * K, W // K * K
    return m[:h, :w].reshape(h // K, K, w // K, K).any(axis=(1, 3))


def up(mk):
    full = np.zeros((H, W), bool)
    big = np.repeat(np.repeat(mk, K, 0), K, 1)
    full[:big.shape[0], :big.shape[1]] = big
    return full


def band_count(r, ys, xs, reach):
    """Per side: how many of the given pixels lie just outside it (within reach px)."""
    dx, dy = xs - r["c"][0], ys - r["c"][1]
    out = []
    for (nx, ny), half_len, half_dep in sides(r):
        d = dx * nx + dy * ny - half_dep
        t = np.abs(-dx * ny + dy * nx)
        out.append(int(((d > 0) & (d < reach) & (t < half_len + 3 * S)).sum()))
    return out


def world(px, py):
    return (round(X0 + (px - OX) / S, 2), round(Y1 - (py - OY) / S, 2))


# ------------------------------------------------------------------ where the sheet sits on the canvas
def find_cross(img, quad):
    blk = img.max(axis=2) < 40
    x0, x1, y0, y1 = quad
    sub = blk[y0:y1, x0:x1]
    for y in np.nonzero(sub.sum(axis=1) >= 15)[0]:
        row = sub[y].astype(np.int8)
        d = np.diff(np.concatenate(([0], row, [0])))
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        for s, e in zip(starts, ends):
            if 18 <= e - s <= 26:
                cx = (s + e) // 2
                if sub[max(0, y - 12):y + 12, cx].sum() >= 18:
                    return x0 + cx, y0 + y
    return None


sheet = np.asarray(Image.open(SHEET).convert("RGB")).astype(np.int16)
sh, sw = sheet.shape[:2]
c0 = find_cross(sheet, (0, sw // 4, 0, sh // 2))
c1 = find_cross(sheet, (3 * sw // 4, sw, 0, sh // 2))
d0 = find_cross(A, (0, W // 4, 0, H // 2))
d1 = find_cross(A, (3 * W // 4, W, 0, H // 2))
OX, OY = d0[0] - c0[0], d0[1] - c0[1]
assert abs((d1[0] - d0[0]) - (c1[0] - c0[0])) <= 2, "the drawing was rescaled: corner marks %s %s" % (d0, d1)

# ------------------------------------------------------------------ colour masks
red = (R > 150) & (R - G > 70) & (R - B > 70)
grey128 = near((128, 128, 128), 2)
drive = near((150, 150, 150), 2)
park = near((183, 184, 178), 4)
KEY_TOP = OY + MAP["size"][1]               # the sheet's key strip (its grey swatches) is not map
for m in (grey128, drive, park):
    m[KEY_TOP:] = False

# shop blocks vs the road network (both grey 128): components on the coarse grid
lab128 = label(down(grey128))
blocks = {}
for name, (seed, first, axis) in SHOP_ROWS.items():
    v = lab128[seed[1] // K, seed[0] // K]
    blocks[name] = grey128 & up(lab128 == v)
shop_px = np.zeros((H, W), bool)
for m in blocks.values():
    shop_px |= m
road = grey128 & ~dilate(shop_px, 3)

# ------------------------------------------------------------------ lots: regions closed by red lines and roads
free = ~down(dilate(red, 5) | road)
lab_lots = label(free)
lots = {}
for name, seed in LOTS.items():
    v = lab_lots[seed[1] // K, seed[0] // K]
    assert v, "%s: seed on a line" % name
    mk = lab_lots == v
    assert mk.sum() < 0.05 * mk.size, "%s: its outline isn't closed (the fill leaked out)" % name
    mk = erode(dilate(mk, 11), 11)                   # fill the notches a road stub cuts into a lot
    lots[name] = dict(kind="villa" if name.startswith("Villa") else "house", mk=mk, poly=outline(mk, K))

# one line per shared fence: corners of different lots closer than SNAP px become one corner
SNAP = 20
groups = []
for n, L in lots.items():
    for i, p in enumerate(L["poly"]):
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

# terrain: flat building land and water (1 px = 1 m, centred on the origin, row 0 = north)
flat_t = np.asarray(Image.open(os.path.join(MASKS, "valley_flat_mask.png")).convert("L")) > 127
water_t = np.asarray(Image.open(os.path.join(MASKS, "valley_water_mask.png")).convert("L")) > 127
TR, TC = flat_t.shape
cols_of_x = np.clip((X0 + (np.arange(W) - OX) / S + TC / 2).astype(int), 0, TC - 1)
rows_of_y = np.clip((TR / 2 - (Y1 - (np.arange(H) - OY) / S)).astype(int), 0, TR - 1)
flat_full = flat_t[np.ix_(rows_of_y, cols_of_x)]
water_full = water_t[np.ix_(rows_of_y, cols_of_x)]
road_ys, road_xs = np.nonzero(road[::4, ::4])
road_ys, road_xs = road_ys * 4, road_xs * 4

# ------------------------------------------------------------------ buildings: the roof in each lot's picture
for name, L in lots.items():
    full = up(L["mk"])
    ys, xs = np.nonzero(full)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    reg = full[y0:y1, x0:x1]
    r_, g_, b_ = R[y0:y1, x0:x1], G[y0:y1, x0:x1], B[y0:y1, x0:x1]
    mx = np.maximum(np.maximum(r_, g_), b_)
    dark = reg & (mx < 150) & (r_ - b_ < 12) & ~grey128[y0:y1, x0:x1] & ~drive[y0:y1, x0:x1]
    dark = erode(dilate(dark, 5), 5)
    lab = label(dark)
    ids, counts = np.unique(lab[lab > 0], return_counts=True)
    roof = lab == ids[np.argmax(counts)]
    rect = min_rect(roof, x0, y0)
    # front: the side the picture's paving (driveway, parking court) is on
    light = reg & (np.abs(r_ - g_) <= 5) & (np.abs(g_ - b_) <= 7) & (r_ >= 185) & (r_ <= 225)
    light = dilate(erode(light, 3), 3)                       # drop the 1 px grid lines
    py_, px_ = np.nonzero(light)
    counts_pave = band_count(rect, py_ + y0, px_ + x0, 14 * S)
    front = int(np.argmax(counts_pave))
    k = np.argmin((road_xs - rect["c"][0]) ** 2 + (road_ys - rect["c"][1]) ** 2)
    (nx, ny), half_len, half_dep = sides(rect)[front]
    L.update(rect=rect, roof=(roof, x0, y0), front=front, normal=(nx, ny),
             drawn_wd=(2 * half_len / S, 2 * half_dep / S),
             road_dist=math.hypot(road_xs[k] - rect["c"][0], road_ys[k] - rect["c"][1]) / S,
             area=poly_area(L["poly"]) / S / S, flat=float(flat_full[full].mean()),
             water=float(water_full[full].mean()))

# ------------------------------------------------------------------ shops, parking pads
shops = {}
for name, (seed, first, axis) in SHOP_ROWS.items():
    m = blocks[name]
    rect = min_rect(m)
    if rect["h"] > rect["w"]:                                   # u = the long axis
        rect = dict(c=rect["c"], a=rect["a"] + math.pi / 2, w=rect["h"], h=rect["w"])
    ca, sa = math.cos(rect["a"]), math.sin(rect["a"])
    if ca * axis[0] + sa * axis[1] < 0:                        # u runs the way the shops are numbered
        rect["a"] += math.pi
        ca, sa = -ca, -sa
    ys, xs = np.nonzero(m)
    bx0, by0 = xs.min(), ys.min()
    sub = A[by0:ys.max() + 1, bx0:xs.max() + 1]
    dys, dxs = np.nonzero(sub.max(axis=2) < 70)
    u = (dxs + bx0 - rect["c"][0]) * ca + (dys + by0 - rect["c"][1]) * sa
    v = -(dxs + bx0 - rect["c"][0]) * sa + (dys + by0 - rect["c"][1]) * ca
    inner = (np.abs(u) < rect["w"] / 2 - 2 * S) & (np.abs(v) < rect["h"] / 2 - S)
    hist = np.bincount(((u[inner] + rect["w"] / 2) // S).astype(int), minlength=int(rect["w"] / S) + 2)
    above = np.concatenate(([0], (hist > 0.4 * rect["h"]).astype(np.int8)))
    n = int((np.diff(above) == 1).sum()) + 1                    # each run of strong bins = one divider line
    pys, pxs = np.nonzero(park)
    cnt = band_count(rect, pys, pxs, 10 * S)
    front = 2 if cnt[2] >= cnt[3] else 3                       # a long side: toward the parking
    shops[name] = dict(rect=rect, n=n, first=first, front=front, park_band=cnt[2:])

lab_park = label(down(park))
ids, counts = np.unique(lab_park[lab_park > 0], return_counts=True)
pads = []
for i, c in zip(ids, counts):
    if c * K * K / S / S > 300:
        mk = lab_park == i
        for m in blocks.values():
            mk |= down(m)
        mk = erode(dilate(mk, 9), 9)
        lb = label(mk)
        mk = lb == lb[np.nonzero(lab_park == i)][0]
        py_, px_ = np.nonzero(lab_park == i)                       # its label goes on the open tarmac
        pads.append(dict(mk=mk, poly=outline(mk, K), area=float(mk.sum() * K * K / S / S),
                         label_at=(float(px_.mean() * K), float(py_.mean() * K))))

# ------------------------------------------------------------------ roads: kept / new / removed vs the sheet
orig = np.zeros((H, W), bool)
sm = (np.abs(sheet[:2100] - 128).max(axis=2) <= 2) | (np.abs(sheet[:2100] - 150).max(axis=2) <= 2)
orig[OY:OY + 2100, OX:OX + sm.shape[1]] = sm
now = road | drive
now &= dilate(erode(now, 5), 5)                           # drop thin bits (anti-aliased text in road greys)
removed = dilate(erode(orig & ~dilate(now, 9), 9), 9) & orig
kept = now & dilate(orig, 9)
new = now & ~kept

# centrelines (coarse grid): 7 m roads survive an erosion that wipes out the 3 m driveways
now_k = down(now)
wide_k = dilate(erode(now_k, 9), 5)
roads = []
for line in centerlines(now_k, min_spur=6 * S / K):
    on = np.mean([wide_k[y, x] for x, y in line])
    pts = dp([(x * K + K / 2, y * K + K / 2) for x, y in line], 0.4 * S)
    roads.append(dict(width=7.0 if on > 0.5 else 3.0, pts=[world(*p) for p in pts]))
# the free end nearest the bridge IS the bridge end: snap it there exactly
ends = [(r, i) for r in roads if r["width"] == 7.0 for i in (0, -1)]
r, i = min(ends, key=lambda e: math.dist(e[0]["pts"][e[1]], ANCHOR))
r["pts"][i] = tuple(ANCHOR)
r["bridge_end"] = i

data = dict(source=os.path.basename(SRC), sheet_offset_px=[int(OX), int(OY)], px_per_m=S,
            note="world x = x0 + (px - offset x) / S, y = y1 - (py - offset y) / S (Blender metres; Godot z = -y)",
            lots=[], shop_rows=[], parking=[], roads=roads, park_label=world(*PARK_LABEL))
for name, L in lots.items():
    r = L["rect"]
    data["lots"].append(dict(
        name=name, kind=L["kind"], outline=[world(*p) for p in L["poly"]], area_m2=round(L["area"]),
        label=world(*LABELS[name]), flat_pct=round(100 * L["flat"]), water_pct=round(100 * L["water"]),
        drawn_building=dict(corners=[world(*p) for p in corners(r["c"], r["a"], r["w"], r["h"])],
                            centre=world(*r["c"]), width_m=round(L["drawn_wd"][0], 1),
                            depth_m=round(L["drawn_wd"][1], 1),
                            front_dir=(round(L["normal"][0], 3), round(-L["normal"][1], 3)),
                            centre_to_road_m=round(L["road_dist"], 1))))
for name, sr in shops.items():
    r = sr["rect"]
    (nx, ny), _, _ = sides(r)[sr["front"]]
    data["shop_rows"].append(dict(name=name, shops=sr["n"], first_number=sr["first"],
                                  corners=[world(*p) for p in corners(r["c"], r["a"], r["w"], r["h"])],
                                  centre=world(*r["c"]), length_m=round(r["w"] / S, 1), depth_m=round(r["h"] / S, 1),
                                  axis_dir=(round(math.cos(r["a"]), 3), round(-math.sin(r["a"]), 3)),
                                  front_dir=(round(nx, 3), round(-ny, 3)), front="toward the parking"))
for p in pads:
    data["parking"].append(dict(outline=[world(*q) for q in p["poly"]], area_m2=round(p["area"]),
                                label=world(*p["label_at"])))
json.dump(data, open(os.path.join(OUT, "east_drawn.json"), "w"), indent=1)

render(os.path.join(OUT, "east_drawn.png"), (W, H), lots=lots, shops=shops, pads=pads, flat=flat_full,
       water=water_full, kept=kept, new=new, removed=removed, park_label=PARK_LABEL, S=S,
       real=REAL, sides=sides, corners=corners, origin=(OX, OY), frame=(X0, Y1))

print("sheet offset on the canvas: (%d, %d) px" % (OX, OY))
for name, L in lots.items():
    print("%-9s lot %6d m2  flat %3d%%  water %2d%%  drawn building %4.1f x %4.1f m  front (%.2f, %.2f)  road %.0f m"
          % (name, L["area"], 100 * L["flat"], 100 * L["water"], L["drawn_wd"][0], L["drawn_wd"][1],
             L["normal"][0], -L["normal"][1], L["road_dist"]))
for name, sr in shops.items():
    r = sr["rect"]
    print("%s: %d shops, block %.1f x %.1f m (each %.1f m wide), parking band per long side %s" % (
        name, sr["n"], r["w"] / S, r["h"] / S, r["w"] / S / sr["n"], sr["park_band"]))
for p in pads:
    print("parking pad %d m2, %d corners" % (p["area"], len(p["poly"])))
print("roads px: kept %d, new %d, removed %d" % (kept.sum(), new.sum(), removed.sum()))
print("centrelines: %d roads (7 m), %d driveways (3 m), %.0f m in all" % (
    sum(r["width"] == 7.0 for r in roads), sum(r["width"] == 3.0 for r in roads),
    sum(math.dist(a, b) for r in roads for a, b in zip(r["pts"], r["pts"][1:]))))
