"""1950s rounded-top refrigerator, 74 x 70 x 148 cm, aged cream enamel.
Pillow-edged full-height door (hinged left), chrome lever handle on the right,
chrome nameplate with blue strip and a half-round gold emblem (no brand lettering),
pinstripes under the badge, raised bead around the lower door panel, bottom grille
lines, black door gasket and four short feet.

Origin: floor, centre of the footprint. Front faces -Y (same as the furniture set).
Run in Blender (Text Editor > Open > Run Script). Rebuilds 'Fridge50s'.
"""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())

CREAM, BLACK, CHROME, BLUE, GOLD = range(5)
MATS = ["AgedCreamEnamel", "BlackEnamel", "Chrome", "BadgeBlue", "BadgeGold"]

begin()
def paint(faces, slot):
    for f in faces: f.material_index = slot
    return faces

def rrect(hx, hy, radii, segs):
    """Rounded rectangle, corners (+,+) (-,+) (-,-) (+,-); same point count for any radii."""
    pts = []
    for (sx, sy, a0), r in zip(((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)), radii):
        r = max(min(r, hx, hy), 0.0005)
        cx, cy = sx*(hx - r), sy*(hy - r)
        for k in range(segs + 1):
            a = math.radians(a0 + 90*k/segs)
            pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return pts

def rounded_slab(hx, hy, w0, w1, radii, r0, r1, to_world, segs=6, rsegs=4):
    """Rounded-rect section (hx, hy, corner radii) swept from w0 to w1, with the
    w0 edge rounded by r0 and the w1 edge by r1. to_world(u, v, w) -> (x, y, z)."""
    before = set(bm.faces)
    prof = [(r0*(1 - math.sin(a)), w0 + r0*(1 - math.cos(a)))
            for a in (math.pi/2*k/rsegs for k in range(rsegs + 1))] if r0 else [(0, w0)]
    prof += [(r1*(1 - math.cos(a)), w1 - r1 + r1*math.sin(a))
             for a in (math.pi/2*k/rsegs for k in range(rsegs + 1))] if r1 else [(0, w1)]
    rings = [[bm.verts.new(to_world(u, v, w))
              for u, v in rrect(hx - ins, hy - ins, [r - ins for r in radii], segs)]
             for ins, w in prof]
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for k in range(n):
            bm.faces.new((a[k], a[(k+1) % n], b[(k+1) % n], b[k]))
    bm.faces.new(rings[0]); bm.faces.new(list(reversed(rings[-1])))
    new = set(bm.faces) - before
    for f in new: f.smooth = True
    uv_box(new); return new

def prism_xz(pts, y0, y1):
    """Flat plate from an (x, z) outline, between y0 (back) and y1 (front)."""
    before = set(bm.faces)
    back = [bm.verts.new((x, y0, z)) for x, z in pts]
    front = [bm.verts.new((x, y1, z)) for x, z in pts]
    n = len(pts)
    for k in range(n):
        bm.faces.new((back[k], back[(k+1) % n], front[(k+1) % n], front[k]))
    bm.faces.new(back); bm.faces.new(list(reversed(front)))
    new = set(bm.faces) - before; uv_box(new); return new

def half_disc(cx, z0, r, n=16):
    return [(cx + r*math.cos(math.pi*k/n), z0 + r*math.sin(math.pi*k/n)) for k in range(n + 1)]

# ---------------- body ----------------
W, D, H = 0.74, 0.70, 1.48
X, Y = W/2, D/2
FEET = 0.032
CAB_FRONT = -Y + 0.06                       # cabinet front; the door sits in front of it
cy = (CAB_FRONT + Y)/2
paint(rounded_slab(X, (Y - CAB_FRONT)/2, FEET, H, [0.035]*4, 0.008, 0.07,
                   lambda u, v, w: (u, cy + v, w)), CREAM)                         # cabinet

# ---------------- door ----------------
DZ0, DZ1 = 0.05, H - 0.012
dzc = (DZ0 + DZ1)/2
FY = -Y                                     # flat front of the door
paint(rounded_slab(X - 0.002, (DZ1 - DZ0)/2, -(CAB_FRONT - 0.003), Y, [0.075, 0.075, 0.022, 0.022],
                   0.004, 0.03, lambda u, v, w: (u, -w, dzc + v)), CREAM)          # door
paint(box((-X + 0.02, CAB_FRONT - 0.004, DZ0 + 0.02), (X - 0.02, CAB_FRONT + 0.001, DZ1 - 0.03)),
      BLACK)                                                                        # gasket

def line(x0, x1, z0, z1, proud=0.0015, slot=CREAM):
    return paint(box((x0, FY - proud, z0), (x1, FY + 0.001, z1)), slot)

# raised bead around the lower door panel
PX, PZ0, PZ1, B = 0.295, 0.145, 1.085, 0.003
line(-PX, PX, PZ0, PZ0 + B); line(-PX, PX, PZ1 - B, PZ1)
line(-PX, -PX + B, PZ0 + B - 0.001, PZ1 - B + 0.001)           # uprights fit between,
line(PX - B, PX, PZ0 + B - 0.001, PZ1 - B + 0.001)             # no shared corner edge
for z in (1.097, 1.107, 1.117, 1.127):     # pinstripes under the badge
    line(-0.30, 0.30, z, z + 0.002, 0.001)
for z in (0.085, 0.097, 0.109, 0.121):     # bottom grille lines
    line(-0.30, 0.30, z, z + 0.003, 0.0015)

# ---------------- nameplate + emblem ----------------
NZ0, NZ1, NX = 1.148, 1.178, 0.258
paint(box((-NX, FY - 0.007, NZ0), (NX, FY + 0.001, NZ1), bevel=0.003), CHROME)
paint(box((-NX + 0.012, FY - 0.0085, NZ0 + 0.007), (NX - 0.012, FY - 0.005, NZ1 - 0.007)), BLUE)
EX = -0.005
paint(prism_xz(half_disc(EX, NZ1 - 0.002, 0.048), FY - 0.006, FY + 0.001), CHROME)
paint(prism_xz(half_disc(EX, NZ1, 0.036), FY - 0.0085, FY - 0.004), GOLD)
paint(prism_xz(half_disc(EX, NZ1, 0.016), FY - 0.0105, FY - 0.007), BLUE)

# ---------------- chrome lever handle (right side, hinge left) ----------------
HZ = 0.97
boss = new_faces(lathe, [(0, 0), (0.022, 0), (0.022, 0.006), (0.019, 0.02), (0.016, 0.034),
                         (0.012, 0.04), (0, 0.042)], segs=20)                      # round pivot boss
facing_front(paint(boss, CHROME), (0.315, FY + 0.004, HZ))
grip = [Vector((x, FY - 0.03, HZ + dz)) for x, dz in
        ((0.318, 0.002), (0.273, 0.002), (0.228, 0.001), (0.183, -0.001), (0.138, -0.004))]
paint(new_faces(tube, catmull(grip, seg=3), lambda t: 0.009 - 0.0025*t, sides=10), CHROME)

# ---------------- feet ----------------
for fx in (-X + 0.05, X - 0.05):
    for fy in (CAB_FRONT + 0.04, Y - 0.05):
        paint(box((fx - 0.025, fy - 0.025, 0), (fx + 0.025, fy + 0.025, FEET + 0.003), bevel=0.004),
              CREAM)

finish("Fridge50s", location=(0, 0, 0), material=MATS)
