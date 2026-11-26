"""The clean redraw of the user's east-side drawing (read_east_drawing.py builds the data, this draws it).

Pale shapes = what the drawing shows (the roof of each pasted picture, the shop blocks as drawn); solid shapes = the
add-on generator at its real size (east_type_sizes.json), centred where the picture is and turned the same way, so
the user can compare the scale; red arrow = the front (door) side.
"""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LOT = (194, 26, 26)
ROAD_KEPT, ROAD_NEW, ROAD_GONE = (128, 128, 128), (70, 100, 160), (245, 175, 175)
FLAT, WATER, GROUND = (250, 246, 232), (196, 222, 244), (255, 255, 255)
PAD, PAD_LINE = (214, 214, 208), (150, 150, 145)
SOLID = {"villa": (140, 80, 170), "house": (150, 150, 150), "shop": (40, 90, 200)}
GHOST = {"villa": (226, 208, 236), "house": (214, 218, 228), "shop": (196, 212, 240)}
FRONT = (220, 20, 20)

# the user's label positions on the drawing (drawing pixels), reused for the lot captions
LABELS = {"Villa 1": (638, 401), "Villa 2": (1582, 295), "Villa 3": (2174, 223), "Villa 4": (2742, 228),
          "Villa 5": (3235, 295), "Villa 6": (3785, 564), "House 11": (2171, 1163), "House 10": (2547, 1186),
          "House 9": (2887, 1271), "House 8": (3191, 1398), "House 7": (3730, 1639), "House 6": (4319, 1902),
          "House 1": (2261, 2010), "House 2": (2590, 2079), "House 3": (2931, 2231), "House 4": (3253, 2397),
          "House 5": (3949, 2648)}
BRIDGE = (430, 1690)


def font(n, bold=True):
    for f in (("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


def arrow(d, p, n, length, col, width=6):
    q = (p[0] + n[0] * length, p[1] + n[1] * length)
    d.line(p + q, fill=col, width=width)
    head = length * 0.45
    for s in (1, -1):
        a = math.atan2(n[1], n[0]) + math.pi + s * 0.5
        d.line(q + (q[0] + math.cos(a) * head, q[1] + math.sin(a) * head), fill=col, width=width)


def render(path, size, lots, shops, pads, flat, water, kept, new, removed, park_label, S, real, sides,
           corners, origin, frame):
    W, H = size
    px = np.empty((H, W, 3), np.uint8)
    px[:] = GROUND
    px[flat] = FLAT
    px[water] = WATER
    px[removed] = ROAD_GONE
    px[kept] = ROAD_KEPT
    px[new] = ROAD_NEW
    for L in lots.values():                                   # the pictures' roofs, pale
        roof, x0, y0 = L["roof"]
        view = px[y0:y0 + roof.shape[0], x0:x0 + roof.shape[1]]
        view[roof] = GHOST[L["kind"]]
    out = Image.fromarray(px)
    d = ImageDraw.Draw(out)
    F, FS, FB, FL = font(30), font(26, False), font(44), font(64)

    # grid: 10 m, darker every 50 m, on world multiples (as on the sheet)
    OX, OY = origin
    X0, Y1 = frame                                              # the sheet's world frame (east_roads_sizes.json)
    gx = math.ceil((X0 - OX / S) / 10) * 10
    while OX + (gx - X0) * S < W:
        x = OX + (gx - X0) * S
        d.line((x, 0, x, H), fill=(214, 214, 214) if gx % 50 == 0 else (238, 238, 238))
        gx += 10
    gy = math.floor((Y1 + OY / S) / 10) * 10
    while OY + (Y1 - gy) * S < H:
        y = OY + (Y1 - gy) * S
        d.line((0, y, W, y), fill=(214, 214, 214) if gy % 50 == 0 else (238, 238, 238))
        gy -= 10
    # the grid went over the roads and roofs: put them back on top
    top = Image.fromarray(px)
    keep = np.zeros((H, W), bool)
    keep |= removed | kept | new
    for L in lots.values():
        roof, x0, y0 = L["roof"]
        keep[y0:y0 + roof.shape[0], x0:x0 + roof.shape[1]] |= roof
    out.paste(top, (0, 0), Image.fromarray(keep.astype(np.uint8) * 255))
    d = ImageDraw.Draw(out)

    for p in pads:
        d.polygon(p["poly"], fill=PAD, outline=PAD_LINE, width=4)
        d.text(p["label_at"], "parking", fill=(110, 110, 105), font=F, anchor="mm")

    for name, sr in shops.items():
        r = sr["rect"]
        d.polygon(corners(r["c"], r["a"], r["w"], r["h"]), fill=GHOST["shop"], outline=(120, 140, 190), width=3)
        spec = next(x for x in real["shops"] if x["shops"] == sr["n"])
        rw, rd = spec["walls"][0] * S, spec["walls"][1] * S
        (nx, ny), half_len, half_dep = sides(r)[sr["front"]]
        # the real row: centred, its front on the drawn block's front side
        c = (r["c"][0] + nx * (half_dep - rd / 2), r["c"][1] + ny * (half_dep - rd / 2))
        d.polygon(corners(c, r["a"], rw, rd), fill=SOLID["shop"], outline=(20, 40, 90), width=3)
        ca, sa = math.cos(r["a"]), math.sin(r["a"])
        for k in range(sr["n"]):
            t = (k + 0.5) / sr["n"] - 0.5                       # along the drawn block: the user's shop numbers
            p = (r["c"][0] + t * r["w"] * ca - nx * half_dep * 0.5, r["c"][1] + t * r["w"] * sa - ny * half_dep * 0.5)
            d.text((p[0], p[1] - 18), "Shop %d" % (sr["first"] + k), fill=(40, 60, 120), font=F, anchor="mm")
            d.text((p[0], p[1] + 18), "%.0f x %.0f m" % (r["w"] / S / sr["n"], r["h"] / S), fill=(40, 60, 120),
                   font=FS, anchor="mm")
            if k:
                q0 = (r["c"][0] + (k / sr["n"] - 0.5) * r["w"] * ca, r["c"][1] + (k / sr["n"] - 0.5) * r["w"] * sa)
                d.line((q0[0] - nx * half_dep, q0[1] - ny * half_dep, q0[0] + nx * half_dep, q0[1] + ny * half_dep),
                       fill=(120, 140, 190), width=3)
        mid = (c[0] + nx * rd / 2, c[1] + ny * rd / 2)
        arrow(d, mid, (nx, ny), 7 * S, FRONT)

    for name, L in lots.items():
        d.line(L["poly"] + [L["poly"][0]], fill=LOT, width=6, joint="curve")
    for name, L in lots.items():
        r = L["rect"]
        spec = real[L["kind"]]
        (nx, ny), half_len, half_dep = sides(r)[L["front"]]
        a = math.atan2(ny, nx) - math.pi / 2                    # u along the front side, v toward the back
        rw, rd = spec["walls"][0] * S, spec["walls"][1] * S
        d.polygon(corners(r["c"], a, rw, rd), fill=SOLID[L["kind"]], outline=(35, 35, 35), width=3)
        arrow(d, (r["c"][0] + nx * rd / 2, r["c"][1] + ny * rd / 2), (nx, ny), 8 * S, FRONT)
        lx, ly = LABELS[name]
        d.text((lx, ly), name, fill=(40, 40, 40), font=FB, anchor="mm")
        lines = ["lot %s m2" % format(round(L["area"], -1), ",.0f"),
                 "picture %.0f x %.0f m" % L["drawn_wd"]]
        warn = []
        if L["flat"] < 0.97:
            warn.append("%d%% off flat land" % round(100 * (1 - L["flat"])))
        if L["water"] > 0.003:
            warn.append("%d%% in water" % max(1, round(100 * L["water"])))
        for i, t in enumerate(lines + warn):
            d.text((lx, ly + 44 + 32 * i), t, fill=(70, 70, 70) if i < len(lines) else FRONT, font=FS, anchor="mm")

    d.text(park_label, "PARK", fill=(40, 120, 40), font=FL, anchor="mm")
    d.text(BRIDGE, "bridge (to the old neighbourhood)", fill=(60, 60, 60), font=FS, anchor="lm")

    # key
    ky = H - 330
    d.rectangle((0, ky - 30, W, H), fill=(255, 255, 255))
    d.line((40, ky, 40 + 50 * S, ky), fill="black", width=5)
    d.text((40 + 25 * S, ky - 22), "50 m (grid 10 m)", fill="black", font=F, anchor="mm")
    d.text((W - 40, ky - 10), "Valley east side, read from east_roads_sizes-with-houses.png. North up, 6 px = 1 m",
           fill="black", font=F, anchor="rm")
    v, h = real["villa"], real["house"]
    items = [
        (LOT, "lot / fence", "line"), (ROAD_KEPT, "road kept from the old sheet", "box"),
        (ROAD_NEW, "road new in your drawing", "box"), (ROAD_GONE, "old road you removed", "box"),
        (PAD, "parking", "box"), (FLAT, "flat land", "box"), (WATER, "water", "box"),
        (GROUND, "not flat (hills / banks)", "box"),
        (GHOST["villa"], "pale = the roof in your picture / the shop block as drawn", "box"),
        (SOLID["villa"], "gable villa 260 m2 at real size: %.1f x %.1f m" % tuple(v["walls"]), "box"),
        (SOLID["house"], "house 200 m2 at real size: %.1f x %.1f m" % tuple(h["walls"]), "box"),
        (SOLID["shop"], "shopping row, 3 shops, real size: %.1f x %.1f m" % tuple(real["shops"][0]["walls"]), "box"),
        (FRONT, "front / door side", "arrow"),
    ]
    x, y = 40, ky + 60
    for col, text, kind in items:
        tw = int(d.textlength(text, font=FS))
        if x + 70 + tw > W - 40:
            x, y = 40, y + 56
        if kind == "line":
            d.line((x, y, x + 44, y), fill=col, width=6)
        elif kind == "arrow":
            arrow(d, (x, y), (1, 0), 40, col, 5)
        else:
            d.rectangle((x, y - 16, x + 44, y + 16), fill=col, outline=(90, 90, 90))
        d.text((x + 56, y), text, fill="black", font=FS, anchor="lm")
        x += 56 + tw + 50
    out.save(path)
