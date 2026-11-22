"""Old steel seesaw (ref/playground, green beam on red posts).

'SeesawBase' (static): two red pipe posts, base plates and a steel axle.
Slots: 0 PaintRed, 1 DarkSteel.
'Seesaw' (child, tilts about its local Y; origin = pivot): 3 m green square-tube beam,
pivot sleeve, a red seat plank and a green handle hoop at each end, rubber bumpers
under the ends. Slots: 0 PaintGreen, 1 PeeledWoodRed (seats), 2 DarkSteel, 3 Rubber.
Max tilt before a bumper touches the floor: about 17 degrees.
"""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
exec(open(os.path.join(HERE, "playground_lib.py")).read())

PIVOT_Z = 0.52
HALF_L = 1.5

# ---------------- base ----------------
begin()
for sy in (-1, 1):
    y = sy*0.10
    paint(bent([(0, y, 0.0), (0, y, PIVOT_Z + 0.05)], 0.035, sides=12), 0)                  # post
    paint(box((-0.12, y - 0.06, 0), (0.12, y + 0.06, 0.012)), 1)                          # base plate
paint(new_faces(tube, [Vector((0, -0.15, PIVOT_Z)), Vector((0, 0.15, PIVOT_Z))], 0.014, sides=10), 1)  # axle
base = finish("SeesawBase", material=["PaintRed", "DarkSteel"])

# ---------------- beam (built around the pivot at the origin) ----------------
begin()
paint(box((-HALF_L, -0.035, 0.03), (HALF_L, 0.035, 0.09), bevel=0.006, segs=1), 0)          # beam
paint(new_faces(tube, [Vector((0, -0.062, 0)), Vector((0, 0.062, 0))], 0.03, sides=12), 0)   # sleeve
paint(box((-0.04, -0.045, 0.0), (0.04, 0.045, 0.04)), 0)                                      # sleeve web
for sx in (-1, 1):
    x0, x1 = sorted((sx*1.17, sx*(HALF_L - 0.03)))
    seat = box((x0, -0.14, 0.09), (x1, 0.14, 0.125), bevel=0.006, segs=1)
    uv_box(seat, TILE); paint(seat, 1)
    hx = sx*1.06
    paint(bent([(hx, -0.12, 0.09), (hx, -0.12, 0.36), (hx, 0.12, 0.36), (hx, 0.12, 0.09)],
               0.016, bend=0.07, seg=6), 0)                                                   # handle hoop
    bx0, bx1 = sorted((sx*(HALF_L - 0.20), sx*(HALF_L - 0.08)))
    paint(box((bx0, -0.05, -0.05), (bx1, 0.05, 0.03), bevel=0.01, segs=1), 3)               # bumper
beam = part("Seesaw", ["PaintGreen", "PeeledWoodRed", "DarkSteel", "Rubber"], parent=base, at=(0, 0, PIVOT_Z))
