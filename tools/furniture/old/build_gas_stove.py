"""Freestanding 4-burner gas cooker, 60 x 60 x 85 cm, cream enamel, 70s/80s style.
Cast-iron pan supports, black burner caps on aluminium rings, 5 knobs, oven door with
dark glass and bar handle, drawer panel, recessed black plinth.

Origin: floor, centre of the footprint. Front faces -Y (same as the furniture set).
Run in Blender (Text Editor > Open > Run Script). Rebuilds 'GasStove80s'.
"""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())

CREAM, BLACK, IRON, ALU, GLASS = range(5)
MATS = ["CreamEnamel", "BlackEnamel", "CastIron", "Aluminium", "OvenGlass"]

begin()
def paint(faces, slot):
    for f in faces: f.material_index = slot
    return faces

def move(faces, d):
    for v in {v for f in faces for v in f.verts}: v.co += Vector(d)
    return faces

# ---------------- body ----------------
W, D, H = 0.60, 0.60, 0.85
X, Y = W/2, D/2
FY = -Y                          # front plane of the door/panels
PL_H = 0.08                      # plinth height

paint(box((-X + 0.02, -Y + 0.035, 0), (X - 0.02, Y - 0.02, PL_H + 0.002)), BLACK)       # recessed plinth
paint(box((-X, -Y + 0.012, PL_H), (X, Y, H - 0.012), bevel=0.006), CREAM)              # cabinet
paint(box((-X, -Y, H - 0.014), (X, Y, H), bevel=0.004), CREAM)                          # hob plate

# ---------------- front ----------------
paint(box((-X + 0.004, FY, PL_H + 0.004), (X - 0.004, FY + 0.013, 0.198), bevel=0.003), CREAM)   # drawer
paint(box((-X + 0.004, FY - 0.003, 0.204), (X - 0.004, FY + 0.013, 0.676), bevel=0.004), CREAM) # door
paint(box((-0.2, FY - 0.0045, 0.29), (0.2, FY, 0.585), bevel=0.003), GLASS)                     # window
paint(box((-0.255, FY - 0.04, 0.636), (0.255, FY - 0.025, 0.656), bevel=0.006), CREAM)          # handle
for sx in (-0.235, 0.235):                                                                        # handle brackets
    paint(box((sx - 0.012, FY - 0.03, 0.638), (sx + 0.012, FY - 0.002, 0.654), bevel=0.003), CREAM)
paint(box((-X + 0.004, FY - 0.002, 0.682), (X - 0.004, FY + 0.013, 0.836), bevel=0.003), CREAM) # control panel

# knobs: 4 burner knobs on the left, oven knob on the right
KZ, PANEL_FRONT = 0.762, FY - 0.002
for kx in (-0.225, -0.155, -0.085, -0.015, 0.215):
    at = (kx, PANEL_FRONT + 0.001, KZ)
    bez = new_faces(lathe, [(0, 0), (0.026, 0), (0.026, 0.004), (0, 0.004)], segs=20)
    facing_front(paint(bez, ALU), at)
    knob = new_faces(lathe, [(0, 0.002), (0.02, 0.002), (0.019, 0.022), (0.016, 0.026), (0, 0.026)], segs=20)
    facing_front(paint(knob, BLACK), at)
    paint(box((kx - 0.005, PANEL_FRONT - 0.032, KZ - 0.017), (kx + 0.005, PANEL_FRONT - 0.02, KZ + 0.017),
              bevel=0.003), BLACK)                                                                 # finger grip

# ---------------- hob: burners ----------------
BX, BY = 0.1475, 0.1425
burners = [(-BX, BY, 0.046), (BX, BY, 0.030), (-BX, -BY, 0.046), (BX, -BY, 0.037)]   # BL, BR, FL, FR
for cx, cy, R in burners:
    ring = new_faces(lathe, [(0, H - 0.001), (R + 0.014, H - 0.001), (R + 0.014, H + 0.006),
                             (R + 0.006, H + 0.011), (0, H + 0.011)], segs=28)
    move(paint(ring, ALU), (cx, cy, 0))
    cap = new_faces(lathe, [(0, H + 0.019), (R - 0.003, H + 0.019), (R, H + 0.016),
                            (R, H + 0.010), (0, H + 0.010)], segs=28)
    move(paint(cap, BLACK), (cx, cy, 0))

# ---------------- cast-iron pan supports (left and right grids) ----------------
T, GT = 0.009, H + 0.032          # bar width, top of the grid
ZB = GT - 0.010                   # underside of frame bars
F, FB = 0.007, GT - 0.012         # finger width, finger underside
GY0, GY1 = -Y + 0.013, Y - 0.013
def bar(lo, hi): return paint(box(lo, hi), IRON)

for side in (-1, 1):
    x0, x1 = sorted((side*0.008, side*0.292))
    bar((x0, GY0, ZB), (x1, GY0 + T, GT)); bar((x0, GY1 - T, ZB), (x1, GY1, GT))     # front / back
    sy0, sy1 = GY0 + T - 0.001, GY1 - T + 0.001                                       # sides fit between
    bar((x0, sy0, ZB), (x0 + T, sy1, GT)); bar((x1 - T, sy0, ZB), (x1, sy1, GT))     # sides (no shared edge)
    bar((x0, -T/2, ZB), (x1, T/2, GT))                                                 # middle
    for px in (x0 + T/2, x1 - T/2):                                                    # feet
        for py in (GY0 + T/2, 0.0, GY1 - T/2):
            bar((px - T/2, py - T/2, H - 0.001), (px + T/2, py + T/2, ZB + 0.001))
    for cx, cy, R in burners:
        if (cx < 0) != (side < 0): continue
        gap = R + 0.012                                     # fingers stop short of the cap
        ylo, yhi = (GY0 + T, -T/2) if cy < 0 else (T/2, GY1 - T)
        bar((cx + gap, cy - F/2, FB), (x1 - T + 0.001, cy + F/2, GT))     # +X finger
        bar((x0 + T - 0.001, cy - F/2, FB), (cx - gap, cy + F/2, GT))     # -X finger
        bar((cx - F/2, cy + gap, FB), (cx + F/2, yhi + 0.001, GT))        # +Y finger
        bar((cx - F/2, ylo - 0.001, FB), (cx + F/2, cy - gap, GT))        # -Y finger

finish("GasStove80s", location=(0, 0, 0), material=MATS)
