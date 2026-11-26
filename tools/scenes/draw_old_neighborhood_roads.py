"""A roads-only sheet of the old neighbourhood for the user to draw lots, fences and houses on.

    python draw_old_neighborhood_roads.py        (system Python + Pillow; needs out/old_neighborhood_plan.json)

Same framing and scale as draw_old_neighborhood_plan.py (8 px = 1 m), white background, light 10 m grid,
roads in grey, black corner marks. Writes out/old_neighborhood_roads.png and out/old_neighborhood_roads.json:
the mapping back to the map (world x = x0 + px / S, world y = y1 - py / S, Blender metres; Godot z = -y).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(HERE, "out", "old_neighborhood_plan.json")))
S = 8
M = 20.0

pts = [p for s in D["roads"] + D["drives"] for p in s] + [p for L in D["lots"] for p in L["corners"]]
x0, x1 = min(p[0] for p in pts) - M, max(p[0] for p in pts) + M
y0, y1 = min(p[1] for p in pts) - M, max(p[1] for p in pts) + M
W, H = int((x1 - x0) * S), int((y1 - y0) * S) + 60
im = Image.new("RGB", (W, H), (255, 255, 255))
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
    d.line(T((gx, y0)) + T((gx, y1)), fill=(232, 232, 232))
for gy in range(int(y0 // 10) * 10, int(y1) + 10, 10):
    d.line(T((x0, gy)) + T((x1, gy)), fill=(232, 232, 232))
road_w = int(2 * D["road_half"] * S)
for a, b in D["roads"]:
    d.line(T(a) + T(b), fill=(128, 128, 128), width=road_w)
    for p in (a, b):
        x, y = T(p)
        d.ellipse((x - road_w / 2, y - road_w / 2, x + road_w / 2, y + road_w / 2), fill=(128, 128, 128))
# the existing cottage (stays where it is): its lot in the plan, outlined in dark grey
hero = next((L for L in D["lots"] if L["hero"]), None)
if hero:
    d.polygon([T(p) for p in hero["corners"]], outline=(60, 60, 60), width=2)
    cx = sum(p[0] for p in hero["corners"]) / 4
    cy = sum(p[1] for p in hero["corners"]) / 4
    d.text(T((cx, cy)), "existing\ncottage", fill=(60, 60, 60), font=F, anchor="mm", align="center")
far = max((p for s in D["roads"] for p in s), key=lambda p: p[0])
fx, fy = T(far)
d.text((fx - 10, fy - 30), "to the bridge / shops", fill=(60, 60, 60), font=F, anchor="rm")
for cx, cy in ((12, 12), (W - 12, 12), (12, H - 72), (W - 12, H - 72)):      # corner marks
    d.line((cx - 10, cy, cx + 10, cy), fill="black", width=2)
    d.line((cx, cy - 10, cx, cy + 10), fill="black", width=2)
ly = H - 40
d.line((20, ly, 20 + 20 * S, ly), fill="black", width=3)
d.text((20 + 10 * S, ly - 14), "20 m (grid = 10 m)", fill="black", font=F, anchor="mm")
d.text((W - 20, ly), "Old neighbourhood - roads only (60 %), road 7 m wide, north up", fill="black", font=FB,
       anchor="rm")
out = os.path.join(HERE, "out", "old_neighborhood_roads.png")
im.save(out)
json.dump(dict(x0=x0, y1=y1, px_per_m=S, size=[W, H], note="world x = x0 + px / S, world y = y1 - py / S "
               "(Blender metres; Godot x = x, z = -y)"), open(out[:-4] + ".json", "w"), indent=1)
print("drawn", out, im.size)
