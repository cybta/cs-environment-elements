"""Old steel playground slide (ref/playground, yellow one).

Yellow welded-pipe A-frame: front legs under the chute top, ladder rails at the back,
both bent over the top into a handrail hoop. Five ladder rungs, a side brace each side,
a small deck plate. Galvanised sheet chute (about 2.9 m) with folded edge lips, a yellow
pipe rail along each edge and two short legs at the run-out.

Origin: floor, centre of the footprint. The chute runs down towards -Y.
Slots: 0 PaintYellow, 1 GalvSteel. Rebuilds 'PlaygroundSlide'.
"""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
exec(open(os.path.join(HERE, "playground_lib.py")).read())

YELLOW, STEEL = 0, 1
R = 0.021                # frame pipe radius (42 mm pipe)
HW = 0.29                # frame half width (pipe centres)
DECK = 1.45              # deck / chute top height
TOP = 2.02               # handrail hoop top
LAD_TOP, LAD_FOOT = (0.90, TOP), (1.42, 0.0)     # ladder rail line (y, z)

def ladder_y(z):
    (y0, z0), (y1, z1) = LAD_TOP, LAD_FOOT
    return y0 + (y1 - y0)*(z - z0)/(z1 - z0)

begin()
# ---- side frames: front leg -> hoop -> ladder rail ----
for sx in (-1, 1):
    x = sx*HW
    pts = [(x, 0.36, 0.0), (x, 0.56, DECK), (x, 0.60, TOP), (x, LAD_TOP[0], TOP), (x, LAD_FOOT[0], 0.0)]
    paint(bent(pts, R, bend=0.13, seg=8), YELLOW)
    zb = 0.62                                                    # side brace
    yf = 0.36 + (0.56 - 0.36)*zb/DECK
    paint(bent([(x, yf, zb), (x, ladder_y(zb), zb)], R*0.8), YELLOW)

# ---- rungs and deck plate ----
for i in range(5):
    z = 0.26 + i*0.24
    paint(new_faces(tube, [Vector((-HW, ladder_y(z), z)), Vector((HW, ladder_y(z), z))], R*0.8, sides=8), YELLOW)
paint(box((-HW + 0.01, 0.55, DECK - 0.01), (HW - 0.01, ladder_y(DECK) - 0.02, DECK + 0.012)), STEEL)
paint(new_faces(tube, [Vector((-HW, ladder_y(DECK), DECK)), Vector((HW, ladder_y(DECK), DECK))], R*0.8, sides=8), YELLOW)

# ---- chute ----
CW = 0.235                                    # half width of the sheet
path = fillet([(0, 0.56, DECK - 0.01), (0, -1.70, 0.36), (0, -2.32, 0.30)], 0.55, seg=10)
lip = 0.035
prof = [(-CW, 0), (CW, 0), (CW, lip), (CW - 0.005, lip), (CW - 0.005, 0.004),
        (-CW + 0.005, 0.004), (-CW + 0.005, lip), (-CW, lip)]
paint(sheet(path, prof), STEEL)

# edge rails: follow the chute, raised over the lips, front end turns down into a short leg
X_AXIS = Vector((1, 0, 0))
def up_at(i):
    t = (path[min(i+1, len(path)-1)] - path[max(i-1, 0)]).normalized()
    u = X_AXIS.cross(t).normalized(); return u if u.z > 0 else -u
for sx in (-1, 1):
    rail = [Vector((sx*(CW + 0.012), p.y, p.z)) + up_at(i)*(lip + 0.004) for i, p in enumerate(path)]
    rail[0] = Vector((sx*(CW + 0.012), 0.60, DECK + 0.03))                 # weld into the frame
    paint(new_faces(tube, rail, R, sides=10), YELLOW)
    end = rail[-1]
    paint(bent([(end.x, -2.18, end.z), (end.x, -2.18, 0.0)], R*0.85), YELLOW)    # run-out leg

center_footprint()
finish("PlaygroundSlide", material=["PaintYellow", "GalvSteel"])
