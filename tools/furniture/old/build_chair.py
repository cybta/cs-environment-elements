"""Original procedural generator for the bentwood chair.

NOTE: the chair in old_bentwood_chair.blend was hand-edited after this script ran, then
cleaned up and optimised with optimize_for_game.py (weld caps, fill holes, reduce to ~3k tris,
grain-aligned UVs). Running this script REPLACES 'OldBentwoodChair' with the unedited,
heavier (~15k tris) version, so run it in a copy of the file, as a starting point only.
"""
import os, bpy, bmesh, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())   # for ensure_material()

old = bpy.data.objects.get("OldBentwoodChair")
if old: bpy.data.objects.remove(old, do_unlink=True)
mat = ensure_material()
parts = []

def link(name, me):
    ob = bpy.data.objects.new(name, me); bpy.context.collection.objects.link(ob); parts.append(ob); return ob

def catmull(pts, seg=12):
    out = []
    P = [pts[0] + (pts[0]-pts[1])] + pts + [pts[-1] + (pts[-1]-pts[-2])]
    for i in range(1, len(P)-2):
        p0, p1, p2, p3 = P[i-1], P[i], P[i+1], P[i+2]
        for k in range(seg):
            t = k/seg; t2, t3 = t*t, t*t*t
            out.append(0.5*((2*p1) + (-p0+p2)*t + (2*p0-5*p1+4*p2-p3)*t2 + (-p0+3*p1-3*p2+p3)*t3))
    out.append(pts[-1].copy()); return out

def tube(name, pts, radii, res=4):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = 1.0; cu.bevel_resolution = res; cu.use_fill_caps = True
    sp = cu.splines.new('POLY'); sp.points.add(len(pts)-1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1); sp.points[i].radius = radii(i/(len(pts)-1)) if callable(radii) else radii
    link(name, cu)

def at_z(line, z):
    for a, b in zip(line, line[1:]):
        if (a.z-z)*(b.z-z) <= 0 and a.z != b.z:
            return a.lerp(b, (z-a.z)/(b.z-a.z))

def _base_outline(n=128):
    """Superellipse seat shape (wider at front), resampled to even spacing."""
    dense = []
    for i in range(2000):
        a = 2*math.pi*i/2000; c, s = math.cos(a), math.sin(a)
        x = math.copysign(abs(c)**0.5, c); y = math.copysign(abs(s)**0.5, s)
        hw = 0.215 - 0.03*(y+1)/2
        dense.append(Vector((x*hw, -0.005 + y*0.2, 0)))
    seg = [(dense[i+1 if i+1 < len(dense) else 0] - dense[i]).length for i in range(len(dense))]
    total = sum(seg); step = total/n; out = []; acc = 0; k = 0
    for i, d in enumerate(seg):
        while k < n and acc + d >= k*step:
            t = (k*step - acc)/d if d else 0
            out.append(dense[i].lerp(dense[(i+1) % len(dense)], t)); k += 1
        acc += d
    return out
_BASE = _base_outline()

def outline(inset):
    """True inward offset of the seat outline (constant rim thickness)."""
    n = len(_BASE); out = []
    for i in range(n):
        a, b = _BASE[i-1], _BASE[(i+1) % n]
        t = (b - a).normalized(); nrm = Vector((t.y, -t.x, 0))  # outward for CCW
        out.append(_BASE[i] - nrm*inset)
    return out

def dist_to_poly(p, poly):
    best = 9
    for a, b in zip(poly, poly[1:]+poly[:1]):
        ab = b-a; t = max(0, min(1, (p-a).dot(ab)/ab.length_squared))
        best = min(best, (a+ab*t-p).length)
    return best

def point_in_poly(p, poly):
    c = False
    for a, b in zip(poly, poly[1:]+poly[:1]):
        if (a.y > p.y) != (b.y > p.y) and p.x < (b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x: c = not c
    return c

RIM_T = 0.016
inner = outline(RIM_T)

def leg_center(angle_deg, r):
    """Walk inward from outside along a diagonal until the leg just touches
    the rim's inner face (1 mm press fit)."""
    a = math.radians(angle_deg); d = Vector((math.cos(a), math.sin(a), 0))
    for i in range(400):
        q = Vector((0, -0.005, 0)) + d*(0.30 - i*0.001)
        if point_in_poly(q, inner) and dist_to_poly(q, inner) >= r - 0.001:
            return q

R_FRONT, R_REAR = 0.018, 0.017
Z_RIM_BOT, Z_RIM_TOP, Z_PANEL_BOT = 0.425, 0.462, 0.44
Z_TOP = 0.79                 # top of crest rail
POST_TOP = Z_TOP - 0.008     # posts stop inside the rail, hidden

# ---------- seat rim + panel ----------
bm = bmesh.new()
outer = outline(0.0)
def ring(pts, z): return [bm.verts.new((p.x, p.y, z)) for p in pts]
rings = [ring(outer, Z_RIM_BOT), ring(outer, Z_RIM_TOP), ring(inner, Z_RIM_TOP), ring(inner, Z_RIM_BOT)]
n = len(outer)
for i in range(n):
    j = (i+1) % n
    for k in range(4):
        a, b = rings[k], rings[(k+1) % 4]
        bm.faces.new((a[i], a[j], b[j], b[i]))
m = bpy.data.meshes.new("SeatRim"); bm.to_mesh(m); bm.free()
rim = link("SeatRim", m); bv = rim.modifiers.new("Bevel", 'BEVEL'); bv.width = 0.004; bv.segments = 2

panel_pts = outline(RIM_T - 0.004)   # panel tucked 4 mm into the rim
def panel_z(p): return 0.452 - 0.006*(1 - min(1, (p.x**2 + (p.y+0.005)**2)/0.04))
bm = bmesh.new()
top = [bm.verts.new((p.x, p.y, 0.452)) for p in panel_pts]
bot = [bm.verts.new((p.x, p.y, Z_PANEL_BOT)) for p in panel_pts]
ftop = bm.faces.new(top); bm.faces.new(list(reversed(bot)))
for i in range(len(panel_pts)):
    j = (i+1) % len(panel_pts); bm.faces.new((bot[i], bot[j], top[j], top[i]))
bmesh.ops.triangulate(bm, faces=[ftop])
m = bpy.data.meshes.new("SeatPanel"); bm.to_mesh(m); bm.free()
link("SeatPanel", m)

# ---------- legs ----------
legs = {}
for s in (-1, 1):
    f = leg_center(-90 + s*48, R_FRONT)
    r = leg_center(90 - s*42, R_REAR)
    # evenly spaced control points: uneven ones make the Catmull-Rom overshoot
    fl = catmull([Vector((f.x + s*0.04, f.y - 0.06, 0)), Vector((f.x + s*0.016, f.y - 0.022, 0.22)),
                  Vector((f.x, f.y, Z_PANEL_BOT))], seg=20)
    fl[-1] = Vector((f.x, f.y, Z_PANEL_BOT - 0.001))   # top seats just under the panel
    tube("FrontLeg", fl, lambda t: R_FRONT*(0.8 + 0.2*min(1, t*1.3)))
    rl = catmull([Vector((r.x + s*0.04, r.y + 0.09, 0)), Vector((r.x + s*0.016, r.y + 0.032, 0.22)),
                  Vector((r.x, r.y, 0.44)), Vector((r.x, r.y + 0.016, 0.62)),
                  Vector((r.x, r.y + 0.044, POST_TOP))], seg=18)
    tube("RearLeg", rl, lambda t: R_REAR*(0.85 + 0.15*math.sin(math.pi*min(1, t*1.6))))
    legs[s] = (fl, rl)

# ---------- arches ----------
APEX = Z_PANEL_BOT - 0.0095 + 0.0015
def arch(p0, p1, name, nseg=24):
    pts = []
    for i in range(nseg+1):
        t = i/nseg; p = p0.lerp(p1, t)
        p.z = p0.z + (APEX - p0.z)*math.sin(math.pi*t)**0.75
        pts.append(p)
    tube(name, pts, 0.0095)
arch(at_z(legs[-1][0], 0.27), at_z(legs[1][0], 0.27), "ArchFront")
arch(at_z(legs[-1][1], 0.29), at_z(legs[1][1], 0.29), "ArchBack")
for s in (-1, 1):
    arch(at_z(legs[s][0], 0.285), at_z(legs[s][1], 0.30), "ArchSide")

# ---------- crest rail ----------
pr = legs[1][1][-1]
XP, YP = pr.x, pr.y
BULGE, RAIL_T, RAIL_Z0 = 0.04, 0.034, 0.715
def rail_y(x): return YP + BULGE*(1 - (x/XP)**2)
xe = XP + R_REAR + 0.008       # rail runs past the posts and fully covers them
# rounded-rectangle cross-section (u = across thickness, v = height), swept along the arc
RR = 0.008
hu, hv = RAIL_T/2, (Z_TOP - RAIL_Z0)/2
sect = []
for cu_, cv_, a0 in ((hu-RR, hv-RR, 0), (-hu+RR, hv-RR, 90), (-hu+RR, -hv+RR, 180), (hu-RR, -hv+RR, 270)):
    for k in range(5):
        a = math.radians(a0 + 90*k/4)
        sect.append((cu_ + RR*math.cos(a), cv_ + RR*math.sin(a)))
zc = (Z_TOP + RAIL_Z0)/2
bm = bmesh.new(); loops = []
NS = 48
for i in range(NS+1):
    x = -xe + 2*xe*i/NS; y = rail_y(x)
    dydx = -2*BULGE*x/XP**2; nrm = Vector((-dydx, 1, 0)).normalized()
    loops.append([bm.verts.new((x + nrm.x*u, y + nrm.y*u, zc + v)) for u, v in sect])
K = len(sect)
for a, b in zip(loops, loops[1:]):
    for k in range(K): bm.faces.new((a[k], a[(k+1)%K], b[(k+1)%K], b[k]))
bm.faces.new(loops[0]); bm.faces.new(list(reversed(loops[-1])))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
m = bpy.data.meshes.new("CrestRail"); bm.to_mesh(m); bm.free()
link("CrestRail", m)

# ---------- slats ----------
def back_edge_y(x):
    return max(p.y for p in inner if p.y > 0 and abs(p.x - x) < 0.02)
for x in (-0.09, -0.045, 0.0, 0.045, 0.09):
    yb = back_edge_y(x) - 0.022
    yt = rail_y(x)
    zb = panel_z(Vector((x, yb, 0))) - 0.006
    zt = RAIL_Z0 + 0.025
    w, d = 0.0085, 0.006
    bm = bmesh.new()
    a = [bm.verts.new((x+dx, yb+dy, zb)) for dx, dy in ((-w,-d),(w,-d),(w,d),(-w,d))]
    b = [bm.verts.new((x+dx, yt+dy, zt)) for dx, dy in ((-w,-d),(w,-d),(w,d),(-w,d))]
    for k in range(4): bm.faces.new((a[k], a[(k+1)%4], b[(k+1)%4], b[k]))
    bm.faces.new(list(reversed(a))); bm.faces.new(b)
    m = bpy.data.meshes.new("Slat"); bm.to_mesh(m); bm.free()
    sl = link("Slat", m); bv = sl.modifiers.new("Bevel", 'BEVEL'); bv.width = 0.003; bv.segments = 2

for p in parts: p.data.materials.append(mat)

bpy.ops.object.select_all(action='DESELECT')
for p in parts: p.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.convert(target='MESH'); bpy.ops.object.join()
ch = bpy.context.active_object; ch.name = ch.data.name = "OldBentwoodChair"
if hasattr(bpy.ops.object, "shade_auto_smooth"): bpy.ops.object.shade_auto_smooth()
else: bpy.ops.object.shade_smooth()
bpy.context.scene.cursor.location = (0, 0, 0); bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
print("post top", pr, "rail ends", xe, "dims", tuple(round(v, 3) for v in ch.dimensions))
