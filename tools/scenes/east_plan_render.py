"""The drawing of the shrunken east-side plan (plan_east.py builds the plan, this draws it): terrain, 7 m roads,
3 m driveways, parking, shop rows, lots, buildings with their front side, captions and a key. 6 px = 1 m, north up.

plan_east.py draws the buildings as planned (the user's pictures, shrunk). make_east.py then runs this file on its
own, which redraws out/east_plan.png with the buildings, driveways and shop signs as built (out/east_built.json):

    "C:/Program Files/Inkscape/bin/python.exe" east_plan_render.py
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LOT = (194, 26, 26)
ROAD, DRIVE, WALK = (128, 128, 128), (165, 165, 165), (206, 203, 196)
FOUNTAIN = (150, 195, 225)
FLAT, WATER, GROUND = (250, 246, 232), (196, 222, 244), (255, 255, 255)
PAD, PAD_LINE = (214, 214, 208), (150, 150, 145)
FILL = {"villa": (140, 80, 170), "house": (150, 150, 150), "shop": (40, 90, 200)}
FRONT = (220, 20, 20)
KEY_H = 170


def font(n, bold=True):
    for f in (("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


def arrow(d, p, n, length, col, width=4):
    """An arrow from p along the screen direction n."""
    q = (p[0] + n[0] * length, p[1] + n[1] * length)
    d.line(p + q, fill=col, width=width)
    head = max(length * 0.45, 8)
    for s in (1, -1):
        a = math.atan2(n[1], n[0]) + math.pi + s * 0.5
        d.line(q + (q[0] + math.cos(a) * head, q[1] + math.sin(a) * head), fill=col, width=width)


def render(path, plan, g, S, flat_t, water_t, rect_corners, built=None):
    """`built` (east_built.json): draw its buildings, driveways and shop signs instead of the plan's."""
    TR, TC = flat_t.shape
    cols = np.clip((g.x0 + (np.arange(g.w) + 0.5) / S + TC / 2).astype(int), 0, TC - 1)
    rows = np.clip((TR / 2 - (g.y1 - (np.arange(g.h) + 0.5) / S)).astype(int), 0, TR - 1)
    px = np.empty((g.h + KEY_H, g.w, 3), np.uint8)
    px[:] = GROUND
    view = px[:g.h]
    view[flat_t[np.ix_(rows, cols)]] = FLAT
    view[water_t[np.ix_(rows, cols)]] = WATER
    out = Image.fromarray(px)
    d = ImageDraw.Draw(out)
    F, FS, FB, FL = font(22), font(19, False), font(26), font(48)

    gx = math.ceil(g.x0 / 10) * 10                              # grid: 10 m, darker every 50 m (world multiples)
    while g.px((gx, 0))[0] < g.w:
        x = g.px((gx, 0))[0]
        d.line((x, 0, x, g.h), fill=(214, 214, 214) if gx % 50 == 0 else (238, 238, 238))
        gx += 10
    gy = math.floor(g.y1 / 10) * 10
    while g.px((0, gy))[1] < g.h:
        y = g.px((0, gy))[1]
        d.line((0, y, g.w, y), fill=(214, 214, 214) if gy % 50 == 0 else (238, 238, 238))
        gy -= 10

    def P(p):
        return g.px(p)

    def stroke(pts, width_m, col, caps=(True, True)):
        q = [P(p) for p in pts]
        w = width_m * S
        d.line(q, fill=col, width=int(round(w)), joint="curve")
        for (x, y), rnd in zip((q[0], q[-1]), caps):
            if rnd:
                d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)

    square = {(i, -1 if j == -1 else 0) for i, j in plan.get("flat_ends", [])}      # the user's cul-de-sac
    caps = [((i, 0) not in square, (i, -1) not in square) for i in range(len(plan["roads"]))]
    sw = plan.get("sidewalk_width_m", 0)
    for i, (pts, walk) in enumerate(zip(plan["roads"], plan.get("road_sidewalks", [False] * len(plan["roads"])))):
        if walk and sw:
            stroke(pts, plan["road_width_m"] + 2 * sw, WALK, caps[i])
    for c in plan.get("cul_de_sacs", []):                        # its plaza, paved like the sidewalks
        d.polygon([P(q) for q in c["plaza"]], fill=WALK)
    for p in plan["parking"]:
        d.polygon([P(q) for q in p["outline"]], fill=PAD, outline=PAD_LINE, width=3)
    for L in (built or plan)["lots"]:
        if L["driveway"]:
            stroke(L["driveway"], plan["drive_width_m"], DRIVE)
        if L.get("walk"):                                       # front door -> fence door -> sidewalk
            stroke(L["walk"], 1.2, (190, 180, 165))
    for i, pts in enumerate(plan["roads"]):
        stroke(pts, plan["road_width_m"], ROAD, caps[i])
    for c in plan.get("cul_de_sacs", []):                        # the fountain's spot
        (x, y), r = P(c["fountain"]["centre"]), c["fountain"]["r"] * S
        d.ellipse((x - r, y - r, x + r, y + r), fill=FOUNTAIN, outline=(120, 120, 115), width=4)

    def screen_dir(v):
        return (v[0], -v[1])

    as_built = {b["name"]: b for b in built["shop_rows"]} if built else {}
    for s in plan["shop_rows"]:
        b = as_built.get(s["name"])
        if b:
            shop_row_built(d, P, b, FB, S)
            continue
        cs = [P(q) for q in s["corners"]]
        d.polygon(cs, fill=FILL["shop"], outline=(20, 40, 90), width=3)
        fx, fy = s["front_dir"]
        ax, ay = fy, -fx                                         # the long axis (along the front)
        if ax * s["axis_dir"][0] + ay * s["axis_dir"][1] < 0:    # numbered the user's way
            ax, ay = -ax, -ay
        c, L_, D_ = s["centre"], s["length_m"], s["depth_m"]
        for k in range(s["shops"]):
            t = (k + 0.5) / s["shops"] - 0.5
            d.text(P((c[0] + ax * t * L_, c[1] + ay * t * L_)), str(s["first_number"] + k), fill="white", font=FB,
                   anchor="mm")
            if k:
                t0 = k / s["shops"] - 0.5
                m = (c[0] + ax * t0 * L_, c[1] + ay * t0 * L_)
                d.line(P((m[0] - fx * D_ / 2, m[1] - fy * D_ / 2)) + P((m[0] + fx * D_ / 2, m[1] + fy * D_ / 2)),
                       fill="white", width=2)
        arrow(d, P((c[0] + fx * D_ / 2, c[1] + fy * D_ / 2)), screen_dir((fx, fy)), 4 * S, FRONT)
    rows = {s["name"]: s for s in plan["shop_rows"]}
    for p in plan["parking"]:                                   # the shop row's caption goes on its parking
        s = rows[p["for_shops"]]
        x, y = P(p["label"])                                    # the open tarmac (where the user wrote "parking")
        lines = [("%s" % s["name"], (30, 50, 110)),
                 ("%d shops of %.0f x %.0f m" % (s["shops"], s["length_m"] / s["shops"], s["depth_m"]), (30, 50, 110))]
        if s["name"] in as_built:
            lines.append((", ".join("%d %s" % (sh["number"], sh["sign"].title() if sh["sign"].isupper() else sh["sign"])
                                    for sh in as_built[s["name"]]["shops"]), (30, 50, 110)))
        lines.append(("parking %d m2" % p["area_m2"], (90, 90, 85)))
        for i, (t, col) in enumerate(lines):
            d.text((x, y - 22 + 22 * i), t, fill=col, font=FS, anchor="mm", stroke_width=3, stroke_fill="white")

    for L in plan["lots"]:
        d.line([P(q) for q in L["outline"]] + [P(L["outline"][0])], fill=LOT, width=4, joint="curve")
    lots_built = {b["name"]: b for b in built["lots"]} if built else {}
    for L in plan["lots"]:
        b = lots_built.get(L["name"])
        if b:
            w = b["walls"]
            d.polygon([P(q) for q in w], fill=FILL[L["kind"]], outline=(35, 35, 35), width=2)
            front_mid = ((w[0][0] + w[1][0]) / 2, (w[0][1] + w[1][1]) / 2)
            arrow(d, P(front_mid), screen_dir(b["front_dir"]), 3.5 * S, FRONT)
            what = ["%s %.0f x %.0f m" % ("%s villa" % b["style"].lower() if L["kind"] == "villa" else "house",
                                         b["width_m"], b["depth_m"]),
                    "%d m2%s" % (b["area_m2"], ", %d floor%s" % (b["floors"], "s" * (b["floors"] > 1))
                                 if L["kind"] != "villa" else "")]
        else:
            b = L["building"]
            d.polygon([P(q) for q in b["corners"]], fill=FILL[L["kind"]], outline=(35, 35, 35), width=2)
            fx, fy = b["front_dir"]
            arrow(d, P((b["centre"][0] + fx * b["depth_m"] / 2, b["centre"][1] + fy * b["depth_m"] / 2)),
                  screen_dir((fx, fy)), 3.5 * S, FRONT)
            what = ["%s %.0f x %.0f m" % (L["kind"], b["width_m"], b["depth_m"])]
        x, y = P(L["label"])
        halo = dict(anchor="mm", stroke_width=3, stroke_fill="white")
        d.text((x, y), L["name"], fill=(40, 40, 40), font=FB, **halo)
        d.text((x, y + 26), "lot %d m2" % L["area_m2"], fill=(70, 70, 70), font=FS, **halo)
        for i, t in enumerate(what):
            d.text((x, y + 48 + 22 * i), t, fill=(70, 70, 70), font=FS, **halo)

    d.text(P(plan["park_label"]), "PARK", fill=(40, 120, 40), font=FL, anchor="mm")
    bx, by = P(plan["anchor"])
    d.text((bx + 10, by - 30), "bridge (to the old neighbourhood)", fill=(60, 60, 60), font=FS, anchor="lm")

    ky = g.h + 30                                               # the key
    d.line((g.h * 0 + 20, ky, 20 + 50 * S, ky), fill="black", width=4)
    d.text((20 + 25 * S, ky - 16), "50 m (grid 10 m)", fill="black", font=FS, anchor="mm")
    d.text((g.w - 20, ky), "Valley east side, shrunk x%.3f (areas x%.3f): %s lot = %d m2. %s North up, 6 px = 1 m"
           % (plan["factor"], plan["factor"] ** 2, plan["target"]["lot"], plan["target"]["m2"],
              "Buildings as built (make_east.py)." if built else "Buildings as drawn (not built yet)."),
           fill="black", font=F, anchor="rm")
    items = [(LOT, "lot / fence", "line"), (ROAD, "road 7 m", "box"),
             (WALK, "sidewalk %.1f m" % plan.get("sidewalk_width_m", 0), "box"), (DRIVE, "driveway 3 m", "box"),
             (PAD, "parking", "box"), (FILL["villa"], "villa", "box"), (FILL["house"], "house", "box"),
             (FILL["shop"], "shops", "box"), (FRONT, "front / door side", "arrow"),
             (FOUNTAIN, "fountain (spot)", "box"), (FLAT, "flat land", "box"),
             (WATER, "water", "box"), (GROUND, "not flat (hills / banks)", "box")]
    x, y = 20, ky + 50
    for col, text, kind in items:
        tw = int(d.textlength(text, font=FS))
        if x + 60 + tw > g.w - 20:
            x, y = 20, y + 40
        if kind == "line":
            d.line((x, y, x + 36, y), fill=col, width=5)
        elif kind == "arrow":
            arrow(d, (x, y), (1, 0), 30, col, 4)
        else:
            d.rectangle((x, y - 12, x + 36, y + 12), fill=col, outline=(90, 90, 90))
        d.text((x + 46, y), text, fill="black", font=FS, anchor="lm")
        x += 46 + tw + 36
    out.save(path)


def shop_row_built(d, P, b, font_num, S):
    """A shop row as built: its walls, the shop numbers behind their doors, the front arrow."""
    w = b["walls"]
    d.polygon([P(q) for q in w], fill=FILL["shop"], outline=(20, 40, 90), width=3)
    fx, fy = b["front_dir"]
    depth = math.dist(w[1], w[2])
    for sh in b["shops"]:
        c = (sh["door"][0] - fx * depth / 2, sh["door"][1] - fy * depth / 2)
        d.text(P(c), str(sh["number"]), fill="white", font=font_num, anchor="mm")
    front_mid = ((w[0][0] + w[1][0]) / 2, (w[0][1] + w[1][1]) / 2)
    arrow(d, P(front_mid), (fx, -fy), 4 * S, FRONT)


class _Grid:
    """The plan's raster frame, from what east_plan.json saved about its surface map."""

    def __init__(self, sf, out):
        self.x0, self.y1, self.S = sf["x0"], sf["y1"], sf["px_per_m"]
        self.w, self.h = Image.open(os.path.join(out, sf["png"])).size

    def px(self, p):
        return ((p[0] - self.x0) * self.S, (self.y1 - p[1]) * self.S)


if __name__ == "__main__":                       # redraw out/east_plan.png with out/east_built.json
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "out")
    project = os.environ.get("CS_PROJECT", r"C:/cybta/carpentry simulator")
    masks = os.path.join(project, "blender_src", "terrain", "out")
    plan = json.load(open(os.path.join(out, "east_plan.json")))
    built = json.load(open(os.path.join(out, "east_built.json")))
    if sorted(L["name"] for L in built["lots"]) != sorted(L["name"] for L in plan["lots"]):
        raise SystemExit("east_built.json doesn't match east_plan.json: run make_east.py again")
    flat_t = np.asarray(Image.open(os.path.join(masks, "valley_flat_mask.png")).convert("L")) > 127
    water_t = np.asarray(Image.open(os.path.join(masks, "valley_water_mask.png")).convert("L")) > 127
    g = _Grid(plan["surfaces"], out)
    render(os.path.join(out, "east_plan.png"), plan, g, g.S, flat_t, water_t, None, built)
    print("redrew", os.path.join(out, "east_plan.png"))
