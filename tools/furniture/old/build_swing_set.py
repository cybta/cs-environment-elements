"""Old A-frame swing set with three swings (ref/playground, red one).

'SwingSet' (static): red pipe top beam at 2.3 m on two splayed A-frame leg pairs with
a cross brace each. Slot 0 PaintRed.
'Swing_1..3' (children, swing about their local X; origin = hanging point on the beam):
hanger loops, two chains, red steel stirrup triangles and seat.
Slots: 0 PaintRed, 1 DarkSteel.

CHAIN_LINKS = True builds real interlocking links (about 4k tris per swing);
False uses a plain thin rod per chain (about 300 tris per swing), for distant LODs.
"""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
exec(open(os.path.join(HERE, "playground_lib.py")).read())

CHAIN_LINKS = globals().get("CHAIN_LINKS", True)
TOP_Z, HALF_X, SPREAD = 2.30, 1.72, 0.95
SWINGS_X = (-1.08, 0.0, 1.08)
SEAT_DROP = 1.86                 # hanging point to seat top (seat top at about 0.44 m)

# ---------------- frame ----------------
begin()
paint(new_faces(tube, [Vector((-HALF_X - 0.06, 0, TOP_Z)), Vector((HALF_X + 0.06, 0, TOP_Z))], 0.04, sides=14), 0)
for sx in (-1, 1):
    x = sx*HALF_X
    for sy in (-1, 1):
        paint(new_faces(tube, [Vector((x, 0, TOP_Z + 0.02)), Vector((x, sy*SPREAD, 0))], 0.035, sides=12), 0)
    zb = 1.55; yb = SPREAD*(TOP_Z - zb)/TOP_Z
    paint(new_faces(tube, [Vector((x, -yb, zb)), Vector((x, yb, zb))], 0.025, sides=10), 0)  # brace
frame = finish("SwingSet", material=["PaintRed"])

# ---------------- swings (built around their hanging point) ----------------
def build_swing(i, x):
    begin()
    bot = -(SEAT_DROP - 0.20)                       # stirrup apex, chain bottom
    for sx in (-1, 1):
        cx = sx*0.20
        paint(ring_tube(stadium((cx, 0, 0.045), (cx, 0, -0.045), 0.05, (0, 1, 0)), 0.007,
                        (1, 0, 0), sides=6), 1)                              # hanger loop round the beam
        if CHAIN_LINKS:
            paint(chain((cx, 0, -0.085), (cx, 0, bot), wire=0.0035, pitch=0.045, width=0.013, sides=3), 1)
        else:
            paint(new_faces(tube, [Vector((cx, 0, -0.05)), Vector((cx, 0, bot))], 0.005, sides=5), 1)
        sx_seat = sx*0.215
        paint(bent([(sx_seat, -0.075, -SEAT_DROP), (cx, 0, bot), (sx_seat, 0.075, -SEAT_DROP)],
                   0.008, bend=0.02, sides=6), 0)                            # stirrup triangle
    seat = box((-0.245, -0.09, -SEAT_DROP - 0.03), (0.245, 0.09, -SEAT_DROP), bevel=0.005, segs=1)
    paint(seat, 0)
    return part(f"Swing_{i}", ["PaintRed", "DarkSteel"], parent=frame, at=(x, 0, TOP_Z))

swings = [build_swing(i + 1, x) for i, x in enumerate(SWINGS_X)]
