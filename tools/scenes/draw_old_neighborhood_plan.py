"""Draw out/old_neighborhood_plan.json (plan_old_neighborhood.py) as a top-down site plan PNG.

    python draw_old_neighborhood_plan.py        (system Python + Pillow)

Up = north (Blender +Y). Grid every 10 m. Fences green; a shared fence is drawn once, thick, in orange.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "out", "old_neighborhood_plan.json")))
S = 8                                              # px per metre
M = 20.0

pts = [p for s in D["roads"] + D["drives"] for p in s] + [p for L in D["lots"] for p in L["corners"]]
x0, x1 = min(p[0] for p in pts) - M, max(p[0] for p in pts) + M
y0, y1 = min(p[1] for p in pts) - M, max(p[1] for p in pts) + M
W, H = int((x1 - x0) * S), int((y1 - y0) * S) + 60
im = Image.new("RGB", (W, H), (236, 233, 222))
d = ImageDraw.Draw(im)


def font(n):
    for f in ("arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(f, n)
        except OSError:
            pass
    return ImageFont.load_default()


F, FB = font(13), font(18)


def T(p):
    return ((p[0] - x0) * S, (y1 - p[1]) * S)


for gx in range(int(x0 // 10) * 10, int(x1) + 10, 10):
    d.line(T((gx, y0)) + T((gx, y1)), fill=(222, 218, 205))
for gy in range(int(y0 // 10) * 10, int(y1) + 10, 10):
    d.line(T((x0, gy)) + T((x1, gy)), fill=(222, 218, 205))

if D.get("playground"):
    d.polygon([T(p) for p in D["playground"]], fill=(196, 172, 128), outline=(140, 110, 70))
    c = [sum(p[k] for p in D["playground"]) / 4 for k in (0, 1)]
    d.text(T(c), "PLAYGROUND", fill=(90, 60, 30), font=FB, anchor="mm")

for L in D["lots"]:                                # yards
    d.polygon([T(p) for p in L["corners"]], fill=(214, 224, 190) if not L["hero"] else (205, 215, 235))
road_w = int(2 * D["road_half"] * S)
for a, b in D["roads"]:                            # roads (round joints)
    d.line(T(a) + T(b), fill=(125, 120, 115), width=road_w)
    for p in (a, b):
        x, y = T(p)
        d.ellipse((x - road_w / 2, y - road_w / 2, x + road_w / 2, y + road_w / 2), fill=(125, 120, 115))
for L in D["lots"]:                                # each lot's own driveway (straight in from the road)
    if L.get("drive") and not L["hero"]:
        d.line(T(L["drive"][0]) + T(L["drive"][-1]), fill=(176, 150, 112), width=int(2 * D["drive_half"] * S))

for L in D["lots"]:                                # fences: own sides thin green, shared ones thick orange
    c = L["corners"]
    for i in range(4):
        a, b = c[i], c[(i + 1) % 4]
        if L["hero"]:
            d.line(T(a) + T(b), fill=(90, 110, 170), width=1)
        elif i + 1 not in L["skip"]:
            d.line(T(a) + T(b), fill=(40, 120, 40), width=2)
for L in D["lots"]:                                # shared fences on top
    c = L["corners"]
    for i in range(4):
        if i + 1 in L["skip"]:
            d.line(T(c[i]) + T(c[(i + 1) % 4]), fill=(230, 130, 20), width=5)
for L in D["lots"]:                                # houses
    h = L.get("house")
    if h:
        d.polygon([T(p) for p in h["veranda"]], fill=(235, 225, 205), outline=(120, 90, 60))
        d.polygon([T(p) for p in h["walls"]], fill=(150, 70, 55) if not L["infill"] else (95, 105, 125),
                  outline=(60, 30, 20))
        x, y = T(h["door"])
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(200, 30, 30))
        cx = sum(p[0] for p in h["walls"]) / 4
        cy = sum(p[1] for p in h["walls"]) / 4
        d.text(T((cx, cy)), str(L["idx"]), fill="white", font=F, anchor="mm")
    else:
        cx = sum(p[0] for p in L["corners"]) / 4
        cy = sum(p[1] for p in L["corners"]) / 4
        d.text(T((cx, cy)), "existing\ncottage", fill=(50, 60, 120), font=F, anchor="mm", align="center")

# legend + scale bar
ly = H - 45
items = [((150, 70, 55), "cottage (driveway lot)"), ((95, 105, 125), "cottage (no driveway)"),
         ((40, 120, 40), "fence"), ((230, 130, 20), "shared fence (one fence, two lots)"),
         ((200, 30, 30), "front door / steps")]
x = 20
for col, label in items:
    d.rectangle((x, ly, x + 18, ly + 14), fill=col)
    d.text((x + 24, ly), label, fill="black", font=F)
    x += 30 + int(d.textlength(label, font=F))
d.line((W - 20 - 20 * S, ly + 7, W - 20, ly + 7), fill="black", width=3)
d.text((W - 20 - 10 * S, ly - 12), "20 m", fill="black", font=F, anchor="mm")
d.text((20, 12), "Old neighbourhood - site plan (%.0f %% of the current map layout), fences %.2f m from the road "
       "edge, %d m of fence" % (D["scale"] * 100, D["front"] - D["road_half"], D["fence_m"]),
       fill="black", font=FB)
out = os.path.join(HERE, "out", "old_neighborhood_plan.png")
im.save(out)
print("drawn", out, im.size)
