"""A roads-only sheet of the valley's east side for the user to draw lots, fences, houses, villas and shops on.

    python draw_east_roads.py [name]   (system Python + Pillow; needs east_layout.json from extract_east.py;
                                       name defaults to east_roads -> out/<name>.png + .json)

Like draw_old_neighborhood_roads.py: white ground, light 10 m grid (darker every 50 m), roads 7 m and driveways
3 m in grey, the flat building land faintly tinted, water in light blue, black corner marks, a colour key, and
below it the generators' footprints at the same scale (east_type_sizes.json from measure_building_sizes.py) + the
island's lot sizes. Writes out/<name>.png and out/<name>.json: the mapping back to the map
(world x = x0 + px / S, world y = y1 - py / S, Blender metres; Godot z = -y).
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
MASKS = os.path.join(PROJECT, "blender_src", "terrain", "out")
D = json.load(open(os.path.join(HERE, "east_layout.json")))
S = 6                     # px per metre
M = 40.0                  # margin round the roads (m)
KEY_H = 110 + 400          # the colour key, then the building sizes panel (draw_sizes)

pts = [p for s in D["roads"] + D["drives"] for p in s]
x0, x1 = min(p[0] for p in pts) - M, max(p[0] for p in pts) + M
y0, y1 = min(p[1] for p in pts) - M, max(p[1] for p in pts) + M
W, H = int((x1 - x0) * S), int((y1 - y0) * S)


def T(p):
    return ((p[0] - x0) * S, (y1 - p[1]) * S)


def map_layer(name):
    """A terrain mask (2560 x 1536, 1 px = 1 m, centred on the origin, row 0 = north) cut to the sheet, as a
    1-bit stencil (on above half)."""
    a = Image.open(os.path.join(MASKS, name)).convert("L")
    cols, rows = a.size
    box = (x0 + cols / 2, rows / 2 - y1, x1 + cols / 2, rows / 2 - y0)
    return a.resize((W, H), Image.NEAREST, box=box).point(lambda v: 255 if v > 127 else 0).convert("1")


im = Image.new("RGB", (W, H), (255, 255, 255))
im.paste((250, 246, 232), (0, 0), map_layer("valley_flat_mask.png"))      # flat building land
im.paste((196, 222, 244), (0, 0), map_layer("valley_water_mask.png"))     # river, streams, lake
canvas = Image.new("RGB", (W, H + KEY_H), (255, 255, 255))
canvas.paste(im, (0, 0))
d = ImageDraw.Draw(canvas)


def font(n):
    for f in ("arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


F, FB = font(14), font(20)
for gx in range(int(x0 // 10) * 10, int(x1) + 10, 10):
    d.line(T((gx, y0)) + T((gx, y1)), fill=(205, 205, 205) if gx % 50 == 0 else (234, 234, 234))
for gy in range(int(y0 // 10) * 10, int(y1) + 10, 10):
    d.line(T((x0, gy)) + T((x1, gy)), fill=(205, 205, 205) if gy % 50 == 0 else (234, 234, 234))


def strokes(segs, width_m, col):
    w = max(1, int(round(width_m * S)))
    for a, b in segs:
        d.line(T(a) + T(b), fill=col, width=w)
        for p in (a, b):
            x, y = T(p)
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)


strokes(D["drives"], D["drive_width"], (150, 150, 150))
strokes(D["roads"], D["road_width"], (128, 128, 128))
ax, ay = T(D["anchor"])
d.text((ax + 14, ay - 26), "bridge / to the old neighbourhood", fill=(60, 60, 60), font=F, anchor="lm")
for cx, cy in ((12, 12), (W - 12, 12), (12, H - 12), (W - 12, H - 12)):      # corner marks
    d.line((cx - 10, cy, cx + 10, cy), fill="black", width=2)
    d.line((cx, cy - 10, cx, cy + 10), fill="black", width=2)

ky = H + 30
d.line((20, ky, 20 + 50 * S, ky), fill="black", width=3)
d.text((20 + 25 * S, ky - 14), "50 m (grid 10 m)", fill="black", font=F, anchor="mm")
d.text((W - 20, ky), "Valley east side - roads only, road 7 m, driveway 3 m, north up", fill="black", font=FB,
       anchor="rm")
key = [((194, 26, 26), "lot / fence outline"), ((171, 171, 171), "house"), ((140, 80, 170), "villa"),
       ((40, 90, 200), "shop"), ((150, 150, 150), "road / driveway (existing)"),
       ((250, 246, 232), "flat land"), ((196, 222, 244), "water")]
x, y = 20, H + 70
for col, label in key:
    d.rectangle((x, y - 9, x + 20, y + 9), fill=col, outline=(90, 90, 90))
    d.text((x + 26, y), label, fill="black", font=F, anchor="lm")
    x += 46 + int(d.textlength(label, font=F))


def draw_sizes(top):
    """The generators' footprints (east_type_sizes.json, measure_building_sizes.py) at the sheet's scale, street side
    down: dark = the walls (what to draw as the footprint), pale = what comes with it (sidewalk, a villa's driveway +
    paving in front, a shop row's street sidewalk); then the island's lot sizes for reference."""
    path = os.path.join(HERE, "east_type_sizes.json")
    if not os.path.exists(path):
        return
    sizes = json.load(open(path))
    cols = {"HOUSE": (171, 171, 171), "VILLA_MODERN": (140, 80, 170), "VILLA_GABLE": (140, 80, 170),
            "SHOPS": (40, 90, 200)}
    names = {"HOUSE": "House", "VILLA_MODERN": "Modern villa", "VILLA_GABLE": "Gable villa", "SHOPS": "Shop row"}
    d.text((20, top), "Building sizes, same scale as the map (6 px = 1 m). Dark = the walls: draw THIS as the "
           "footprint. Pale = what comes with it (sidewalk; villas: driveway + paving in front; shops: street "
           "sidewalk). Street / front side is DOWN.", fill="black", font=FB, anchor="lm")
    base = top + 40 + int(max(r["overall"][1] for r in sizes) * S)
    x = 20
    for r in sizes:
        col = cols[r["type"]]
        pale = tuple(int(c + (255 - c) * 0.72) for c in col)
        ow, od = r["overall"][0] * S, r["overall"][1] * S
        ww, wd = r["walls"][0] * S, r["walls"][1] * S
        cell = max(ow, 150)
        ox = x + (cell - ow) / 2
        d.rectangle((ox, base - od, ox + ow, base), fill=pale, outline=col)
        side = (ow - ww) / 2                               # walls centred across, at the back (the extras go in front)
        wx, wy = ox + side, base - od + min(side, (od - wd) / 2)
        d.rectangle((wx, wy, wx + ww, wy + wd), fill=col, outline=(60, 60, 60))
        d.text((x + cell / 2, base + 6), "v street", fill=(90, 90, 90), font=F, anchor="mt")
        what = f"{r['shops']} shops" if r["type"] == "SHOPS" else f"{r['area']} m2"
        lines = [f"{names[r['type']]} {what}", f"walls {r['walls'][0]} x {r['walls'][1]} m",
                 f"all {r['overall'][0]} x {r['overall'][1]} m", f"{r['floors']} fl, {r['height']} m high"]
        for i, t in enumerate(lines):
            d.text((x + cell / 2, base + 28 + i * 18), t, fill="black", font=F, anchor="mt")
        x += cell + 40
    d.text((20, base + 120), "Island lots, for reference (fence area): houses 50 m2 ~570 m2 (about 20 x 28 m), "
           "70 m2 ~640 m2, 140 m2 ~1580 m2, the workshop 516 m2; villas: gable ~950 m2, modern ~1100 m2 (about "
           "30 x 35 m); the 3 shop sites 30 x 24 m each (with parking). Old neighbourhood cottage lots ~490 m2 (about 20 x 25 m).",
           fill=(60, 60, 60), font=F, anchor="lm")


draw_sizes(H + 110)
out = os.path.join(HERE, "out", (sys.argv[1] if len(sys.argv) > 1 else "east_roads") + ".png")
canvas.save(out)
json.dump(dict(x0=x0, y1=y1, px_per_m=S, size=[W, H], note="world x = x0 + px / S, world y = y1 - py / S "
               "(Blender metres; Godot x = x, z = -y); the key strip below row H is not map"),
          open(out[:-4] + ".json", "w"), indent=1)
print("drawn", out, canvas.size)
