"""Park bench and slatted wooden bin (ref/playground, bench + bin photo).

'PlaygroundBench': 1.5 m bench, 4 seat slats and 4 reclined back slats on wooden
bearers, a dark steel pipe arch at each end (front leg, armrest arch, raked back leg)
with a low wooden stretcher. Slots: 0 OldWornWood, 1 DarkSteel.

'PlaygroundBin': galvanised liner (seen as the silver base) wrapped in 16 vertical
slats with alternating tops and a black steel band. Slots: 0 OldWornWood, 1 GalvSteel,
2 DarkSteel (band). It sits at BIN_AT, beside the bench.

Origins: floor, centre of each footprint. Front faces -Y.
"""
import os, math
from mathutils import Vector, Matrix
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
exec(open(os.path.join(HERE, "playground_lib.py")).read())

WOOD, STEEL, BAND = 0, 1, 2
BIN_AT = (-1.25, -0.05, 0)

def slat(lo, hi):
    f = box(lo, hi, bevel=0.004, segs=1); uv_box(f, TILE); return f

def rotate(faces, axis, angle, pivot):
    m = Matrix.Rotation(angle, 3, axis); pv = Vector(pivot)
    for v in {v for f in faces for v in f.verts}: v.co = m @ (v.co - pv) + pv

# ================= bench =================
L, AX = 0.75, 0.78           # slat half length, arch x
SEAT_Z = 0.43
begin()
for sx in (-1, 1):
    x = sx*AX
    paint(bent([(x, -0.26, 0), (x, -0.25, 0.60), (x, 0.06, 0.60), (x, 0.24, 0)], 0.022, bend=0.15, seg=8), STEEL)
    yb = 0.06 + (0.24 - 0.06)*(0.60 - 0.12)/0.60                       # back leg y at z=0.12
    paint(slat((x - 0.014, -0.25, 0.10), (x + 0.014, yb, 0.14)), WOOD)   # low stretcher
    xi = sx*(AX - 0.06)
    lo, hi = sorted((xi, sx*(AX - 0.02)))
    paint(slat((lo, -0.25, SEAT_Z - 0.06), (hi, 0.20, SEAT_Z - 0.019)), WOOD)   # seat bearer
    back = slat((lo, 0.15, SEAT_Z - 0.06), (hi, 0.20, 0.90))                    # back bearer
    rotate(back, 'X', math.radians(-16), (0, 0.18, SEAT_Z - 0.06))
    paint(back, WOOD)

for i in range(4):                                              # seat slats, front to back
    y0 = -0.235 + i*0.108
    paint(slat((-L, y0, SEAT_Z - 0.02), (L, y0 + 0.094, SEAT_Z + 0.004)), WOOD)
for i in range(4):                                              # back slats, bottom to top
    z0 = SEAT_Z + 0.07 + i*0.105
    f = slat((-L, 0.135, z0), (L, 0.157, z0 + 0.09))
    rotate(f, 'X', math.radians(-16), (0, 0.18, SEAT_Z - 0.06)); paint(f, WOOD)

center_footprint()
finish("PlaygroundBench", material=["OldWornWood", "DarkSteel"])

# ================= bin =================
begin()
paint(new_faces(lathe, [(0, 0.006), (0.172, 0.0), (0.186, 0.012), (0.186, 0.58), (0.178, 0.58),
                        (0.178, 0.03), (0, 0.03)], segs=32), 1)                     # liner
N, RC = 16, 0.197
for i in range(N):
    a = 2*math.pi*i/N
    top = 0.64 if i % 2 else 0.68
    f = slat((-0.031, -0.0075, 0.055), (0.031, 0.0075, top))
    m = Matrix.Rotation(a, 3, 'Z')
    for v in {v for ff in f for v in ff.verts}: v.co = m @ (v.co + Vector((0, -RC, 0)))
    paint(f, 0)
paint(new_faces(lathe, [(0.2045, 0.50), (0.213, 0.50), (0.213, 0.535), (0.2045, 0.535), (0.2045, 0.50)],
                segs=32), 2)                                                        # band
finish("PlaygroundBin", location=BIN_AT, material=["OldWornWood", "GalvSteel", "DarkSteel"])
