"""Old 4-seat merry-go-round (ref/playground, red/blue/green carousel).

'MerryGoRoundBase' (static): dark steel pedestal. Slot 0 DarkSteel.
'MerryGoRound' (child, spins about its local Z; origin on the axis at floor level):
1.9 m painted deck in four coloured quarters, centre post and hub, and per quarter a
seat plank between two pipe side frames with two spokes from the hub.
Slots: 0-3 PaintRed/Blue/Green/Yellow (pipes), 4 DarkSteel,
5-8 PeeledWoodRed/Blue/Green/Yellow (deck quarters and seat planks).
"""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
exec(open(os.path.join(HERE, "playground_lib.py")).read())

STEEL = 4
DECK_R, DECK_Z0, DECK_Z1 = 0.95, 0.20, 0.245
HUB_Z = 0.86

# ---------------- base ----------------
begin()
lathe([(0, 0), (0.24, 0), (0.24, 0.02), (0.10, 0.05), (0.075, 0.19), (0.075, DECK_Z0 + 0.002), (0, DECK_Z0 + 0.002)],
      segs=24)
base = finish("MerryGoRoundBase", material=["DarkSteel"])

# ---------------- rotor ----------------
begin()
deck = new_faces(lathe, [(0, DECK_Z0), (DECK_R - 0.01, DECK_Z0), (DECK_R, DECK_Z0 + 0.01),
                         (DECK_R, DECK_Z1 - 0.008), (DECK_R - 0.008, DECK_Z1), (0, DECK_Z1)], segs=64)
for f in deck:                                         # quarter colours by angle
    c = f.calc_center_median()
    f.material_index = 5 + int((math.atan2(c.y, c.x) % (2*math.pi))/(math.pi/2)) % 4
paint(new_faces(lathe, [(0, DECK_Z1 - 0.002), (0.05, DECK_Z1 - 0.002), (0.05, DECK_Z1 + 0.03),
                        (0.035, DECK_Z1 + 0.04), (0.035, HUB_Z - 0.04), (0.06, HUB_Z - 0.02),
                        (0.06, HUB_Z + 0.02), (0.03, HUB_Z + 0.05), (0, HUB_Z + 0.055)], segs=16), STEEL)

SEAT_Z, ARM_Z = 0.50, 0.78
R_IN, R_OUT, HALF_T = 0.40, 0.86, 0.23
for q in range(4):
    a = math.pi/4 + q*math.pi/2                          # quarter centre
    rh, th = Vector((math.cos(a), math.sin(a), 0)), Vector((-math.sin(a), math.cos(a), 0))
    P = lambda r, t, z: rh*r + th*t + Vector((0, 0, z))
    for s in (-1, 1):
        t = s*HALF_T
        paint(bent([P(R_IN, t, DECK_Z1 - 0.01), P(R_IN, t, ARM_Z), P(R_OUT, t, ARM_Z),
                    P(R_OUT, t, DECK_Z1 - 0.01)], 0.018, bend=0.09, seg=6), q)       # side frame
        paint(bent([P(0.03, t*0.12, HUB_Z), P(R_OUT - 0.01, t, ARM_Z + 0.004)], 0.016, sides=8), q)  # spoke
    # seat plank (radial depth x tangential width), spans between the two side frames
    corners = [P(r, t, z) for z in (SEAT_Z, SEAT_Z + 0.032) for r, t in
               ((R_IN + 0.05, -HALF_T), (R_OUT - 0.10, -HALF_T), (R_OUT - 0.10, HALF_T), (R_IN + 0.05, HALF_T))]
    vs = [bm.verts.new(c) for c in corners]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    seat = {bm.faces.new([vs[i] for i in qd]) for qd in quads}
    uv_box(seat, TILE); paint(seat, 5 + q)
    paint(bent([P(R_IN + 0.12, -HALF_T, SEAT_Z - 0.004), P(R_IN + 0.12, HALF_T, SEAT_Z - 0.004)],
               0.014, sides=8), q)                                           # seat cross bar

rotor = part("MerryGoRound", ["PaintRed", "PaintBlue", "PaintGreen", "PaintYellow", "DarkSteel",
                                "PeeledWoodRed", "PeeledWoodBlue", "PeeledWoodGreen", "PeeledWoodYellow"], parent=base)
