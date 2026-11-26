"""Old cottage exterior and fittings: everything house.py's walls and floors don't cover.

After the classic timber dacha: the house stands on steel piles under a sill beam,
corner boards and painted casings frame the weathered siding, a gambrel roof in
corrugated sheet runs from the front gable to the back one, and a covered veranda
(deck, posts, baluster rail, steps and a lean-to roof) runs across the front.
Inside: a steep straight stair with open treads and turned-style balusters, and a
guard rail round its hole upstairs.

The painted style (plan.cottage["roof"] == "GABLE") swaps the piles and the gambrel for
a brick plinth and an open gable roof; cottage_painted.py builds those.

Plan coordinates: front of the house at y = 0, ground-floor top at z = 0. Everything
is built from boxes and extruded outlines, with metric UVs, so it exports cleanly as
game geometry.
"""

import math

import bmesh
from mathutils import Vector

from .house_walls import _wall_box
from .mesh_utils import _boxes_mesh, _mat_index, _obj, _sheared_box, _solid

PILE_H = 0.4            # piles between the ground and the sill beam
SILL_H = 0.18
ROOF_T = 0.14           # corrugated sheet on battens
EAVE = 0.3              # eave overhang past the side walls (horizontal)
VERGE = 0.3             # verge overhang past the gable walls
DECK_TOP = -0.04        # the veranda one step-lip below the floor inside
VERANDA_PITCH = 14.0
JOIST_SET_BACK = 0.01   # the veranda's deck and rim joists sit this far behind the posts' faces (no shared plane)
EPS = 1e-4


class _Ctx:
    def __init__(self, s, plan, mats, coll, root, name, center):
        self.s, self.plan, self.coll, self.root, self.name, self.center = s, plan, coll, root, name, center
        fb = mats.get("trim") or mats["wall_out"]
        self.m = dict(mats)
        for role in ("trim", "timber", "post", "pile", "chimney", "chimney_cap"):
            self.m.setdefault(role, fb)
        self.m.setdefault("soffit_out", mats["soffit"])    # undersides out in the weather
        self.m.setdefault("stair_v", mats["stair"])         # upright stair parts, grain vertical
        # Parts the painted style paints white; the old cottage leaves them bare wood
        for role, base in (("corner", "post"), ("veranda_post", "post"), ("baluster", "post"),
                           ("veranda_rail", "timber"), ("bargeboard", "timber"),
                           ("plinth", "chimney"), ("plinth_cap", "chimney_cap")):
            self.m.setdefault(role, self.m[base])
        self.W, self.D, self.te, self.ti = plan.W, plan.D, plan.t_ext, plan.t_int
        self.H, self.F1, self.slab = plan.ceiling_h, plan.storey_h, plan.slab
        self.G = -plan.slab - SILL_H - PILE_H           # the ground
        self.k = plan.cottage
        self.ridge_top = None

    def add(self, label, boxes, role, lengthwise=False):
        """One object from boxes; `lengthwise` runs each box's wood grain along its longest side."""
        if not boxes:
            return None
        me = _boxes_mesh(f"{self.name}_{label}", boxes, self.center)
        if lengthwise:
            assert len(me.polygons) == 6 * len(boxes)
            along, mid = _lengthwise(boxes)
            _uv_along(me, along, lambda i: mid(i) + self.center)
        return _obj(f"{self.name}_{label}", me, self.coll, self.root, [self.m[role]])

    def solid(self, label, parts, role=None, paint=None, along=None):
        """One object from (verts, faces) parts; `paint(mesh)` sets per-face materials instead of `role`.
        `along` (a direction) lays the texture's U, so the wood grain, along it on every face."""
        if not parts:
            return None
        verts, faces = [], []
        for v, f in parts:
            b = len(verts)
            verts += [Vector(p) + self.center for p in v]
            faces += [[b + i for i in face] for face in f]
        me = _solid(f"{self.name}_{label}", verts, faces)
        if paint:
            paint(me)
        if along:
            _uv_along(me, along)
        return _obj(f"{self.name}_{label}", me, self.coll, self.root, [self.m[role]] if role else ())


def build_exterior(s, plan, mats, coll, root, name, center):
    c = _Ctx(s, plan, mats, coll, root, name, center)
    root["cottage_roof"] = c.m["roof"].name
    gabled = c.k.get("roof") == "GABLE"
    if gabled:
        from . import cottage_painted as cp
        cp.plinth(c)
    else:
        _base(c)
    _corner_boards(c)
    _casings(c)
    _veranda(c)
    if gabled:
        cp.roof(c)
        cp.gable_trim(c)
    else:
        _roof(c)
    if getattr(s, "cottage_chimney", True):
        _chimney(c)
    _stair(c)


# --------------------------------------------------------------------------
# Small geometry helpers
# --------------------------------------------------------------------------

def _extrude(outline, a0, a1, axis="Y", caps=None):
    """An outline of (p, z) points extruded from a0 to a1 along `axis` -> (verts, faces).
    axis 'Y': p is x; axis 'X': p is y. `caps` splits a non-convex end into convex pieces."""
    n = len(outline)

    def P(p, z, a):
        return (p, a, z) if axis == "Y" else (a, p, z)

    verts = [P(p, z, a0) for p, z in outline] + [P(p, z, a1) for p, z in outline]
    caps = caps or [list(range(n))]
    faces = [list(cp) for cp in caps] + [[i + n for i in reversed(cp)] for cp in caps]
    faces += [[i, (i + 1) % n, (i + 1) % n + n, i + n] for i in range(n)]
    return verts, faces


def _clip_z(poly, lo, hi):
    """Clip a (d, z) polygon to lo <= z <= hi (Sutherland-Hodgman)."""
    def cut(pts, inside, z_at):
        out = []
        for i, p in enumerate(pts):
            q = pts[i - 1]
            if inside(p):
                if not inside(q):
                    out.append(z_at(q, p))
                out.append(p)
            elif inside(q):
                out.append(z_at(q, p))
        return out

    def at(z):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]), z)

    poly = cut(poly, lambda p: p[1] >= lo - 1e-9, at(lo))
    return cut(poly, lambda p: p[1] <= hi + 1e-9, at(hi))


def _stringer(start, along, slope, z0, top, bottom, length, lo, hi, y0, y1):
    """A stair stringer: a board following z = z0 + slope * d (d from `start` in direction
    `along`, +1/-1 along x), `top` above and `bottom` below that line, cut level at lo / hi.
    Extruded across y0..y1."""
    poly = [(0.0, z0 + top), (length, z0 + slope * length + top),
            (length, z0 + slope * length - bottom), (0.0, z0 - bottom)]
    poly = _clip_z(poly, lo, hi)
    return _extrude([(start + along * d, z) for d, z in poly], y0, y1, "Y")


def _balustrade(axis, c, a, b, z0, h=0.9, step=0.13):
    """A wooden rail along x (axis 'X', at y = c) or y ('Y', at x = c) from a to b, standing on z0
    -> (rail boxes, baluster boxes)."""
    if b - a < 0.08:
        return [], []
    rails = [_wall_box(axis, c, 0.09, a, b, z0 + h - 0.05, z0 + h),
             _wall_box(axis, c, 0.06, a, b, z0 + 0.08, z0 + 0.14)]
    n = max(1, int((b - a) / step))
    bal = []
    for i in range(n):
        m = a + (b - a) * (i + 0.5) / n
        bal.append(_wall_box(axis, c, 0.04, m - 0.02, m + 0.02, z0 + 0.14, z0 + h - 0.05))
    return rails, bal


def _split(me, planes):
    """Cut the mesh's faces along each (point, normal) plane, keeping everything."""
    bm = bmesh.new()
    bm.from_mesh(me)
    for co, no in planes:
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5, plane_co=co, plane_no=no)
    bm.to_mesh(me)
    bm.free()


def _uv_along(me, along, centre=None, pitch=1 / 9):
    """Metric UVs with U following `along` (projected onto each face), so boards and grain
    run the length of sloped parts such as stringers and handrails. `along` may be a function
    of the polygon index. With `centre` (also per polygon), V is shifted so that point falls
    mid-board for boards `pitch` apart (the lining's), keeping grooves off narrow trims."""
    uv = me.uv_layers.new(name="UVMap")
    fixed = None if callable(along) else Vector(along).normalized()
    for p in me.polygons:
        a = fixed if fixed is not None else along(p.index)
        n = p.normal
        t = a - n * a.dot(n)
        t = n.orthogonal() if t.length < 1e-4 else t
        t.normalize()
        b = n.cross(t)
        dv = 0.0
        if centre:
            dv = pitch / 2 - centre(p.index).dot(b) % pitch
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (v.dot(t), v.dot(b) + dv)


def _lengthwise(boxes):
    """For _uv_along on a _boxes_mesh (6 faces per box, in order): each box's grain runs
    along its longest side, so a jamb is grained upright and a head or sill across."""
    dirs, mids = [], []
    for x0, y0, z0, x1, y1, z1 in boxes:
        size = (x1 - x0, y1 - y0, z1 - z0)
        k = max(range(3), key=lambda i: size[i])
        dirs.append(Vector([1.0 if i == k else 0.0 for i in range(3)]))
        mids.append(Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)))
    return (lambda i: dirs[i // 6]), (lambda i: mids[i // 6])


def _post(x, y, z0, z1, w=0.12):
    return (x - w / 2, y - w / 2, z0, x + w / 2, y + w / 2, z1)


# --------------------------------------------------------------------------
# Piles, sill beam, corner boards
# --------------------------------------------------------------------------

def _base(c):
    W, D, te = c.W, c.D, c.te
    z0, z1 = -c.slab - SILL_H, -c.slab + 0.01
    o, w = te / 2 + 0.02, te + 0.04
    c.add("SillBeam", [
        (-o, -o, z0, W + o, -o + w, z1), (-o, D + o - w, z0, W + o, D + o, z1),
        (-o, -o + w, z0, -o + w, D + o - w, z1), (W + o - w, -o + w, z0, W + o, D + o - w, z1),
    ], "timber")
    nx, ny = math.ceil(W / 2.0) + 1, math.ceil(D / 2.0) + 1
    piles = [_post(W * i / (nx - 1), D * j / (ny - 1), c.G, z0, 0.11) for i in range(nx) for j in range(ny)]
    c.add("Piles", piles, "pile")


def _corner_boards(c):
    W, D, te, k = c.W, c.D, c.te, c.k
    top = c.F1 + k["knee"] - (te / 2 + 0.04) * math.tan(math.radians(k["pitch_low"])) - 0.02
    z0, b, d = -c.slab + 0.01, 0.13, 0.025
    boxes = []
    for sx, ox in ((0.0, -1), (W, 1)):
        for sy, oy in ((0.0, -1), (D, 1)):
            cx, cy = sx + ox * te / 2, sy + oy * te / 2
            xa, xb = sorted((cx - ox * b, cx + ox * d))
            boxes.append((xa, min(cy, cy + oy * d), z0, xb, max(cy, cy + oy * d), top))
            ya, yb = sorted((cy - oy * b, cy))
            boxes.append((min(cx, cx + ox * d), ya, z0, max(cx, cx + ox * d), yb, top))
    c.add("CornerBoards", boxes, "corner")


# --------------------------------------------------------------------------
# Casings round windows and doors, casement frames
# --------------------------------------------------------------------------

def _casings(c):
    te, ti = c.te, c.ti
    outside, inside, frames = [], [], []
    for f in c.plan.floors:
        z = f.base_z
        for o in f.openings:
            if o.kind not in ("WINDOW", "ENTRANCE", "DOOR"):
                continue
            win = o.kind == "WINDOW"
            if o.exterior:
                sgn = -1.0 if o.coord < EPS else 1.0
                faces = [(o.coord + sgn * te / 2, sgn, 0.03, 0.1, outside), (o.coord - sgn * te / 2, -sgn, 0.02, 0.07, inside)]
            else:
                faces = [(o.coord + ti / 2, 1.0, 0.02, 0.07, inside), (o.coord - ti / 2, -1.0, 0.02, 0.07, inside)]
            for fc, sg, d, bw, out in faces:
                def board(s0, s1, z0, z1, dd=d):
                    out.append(_wall_box(o.axis, fc + sg * dd / 2, dd, s0, s1, z + z0, z + z1))

                lo = o.z0 - (bw if win else 0.0)
                board(o.s0 - bw, o.s0, lo, o.z1)
                board(o.s1, o.s1 + bw, lo, o.z1)
                if out is outside:      # a deeper cornice board on the head, as on old dachas
                    board(o.s0 - bw - 0.03, o.s1 + bw + 0.03, o.z1, o.z1 + bw + 0.02, d + 0.015)
                else:
                    board(o.s0 - bw, o.s1 + bw, o.z1, o.z1 + bw)
                if win:
                    board(o.s0, o.s1, lo, o.z0)
                    if out is outside:  # the sill
                        board(o.s0 - bw - 0.03, o.s1 + bw + 0.03, o.z0 - 0.035, o.z0 + 0.005, 0.07)
            if win:
                _casement(o, z, frames)
    c.add("Casings", outside, "trim", lengthwise=True)
    c.add("CasingsInside", inside, "stair", lengthwise=True)
    c.add("WindowFrames", frames, "trim", lengthwise=True)


def _casement(o, z, boxes, fw=0.05, depth=0.07):
    """Two casements split by a mullion, with a small top-hung vent (fortochka) in one."""
    def bar(s0, s1, z0, z1):
        boxes.append(_wall_box(o.axis, o.coord, depth, s0, s1, z + z0, z + z1))

    bar(o.s0, o.s0 + fw, o.z0, o.z1)
    bar(o.s1 - fw, o.s1, o.z0, o.z1)
    bar(o.s0 + fw, o.s1 - fw, o.z1 - fw, o.z1)
    bar(o.s0 + fw, o.s1 - fw, o.z0, o.z0 + fw)
    if o.s1 - o.s0 >= 0.7:
        m = (o.s0 + o.s1) / 2
        bar(m - fw / 2, m + fw / 2, o.z0 + fw, o.z1 - fw)
        if o.z1 - o.z0 >= 0.9:
            t = o.z0 + (o.z1 - o.z0) * 0.68
            bar(o.s0 + fw, m - fw / 2, t - fw / 2, t + fw / 2)


# --------------------------------------------------------------------------
# Veranda
# --------------------------------------------------------------------------

def _veranda(c):
    W, te, G = c.W, c.te, c.G
    vd = c.k["veranda"]
    y_in = -te / 2
    y_out = y_in - vd
    x0, x1 = -te / 2, W + te / 2

    # the deck and the rim stand JOIST_SET_BACK behind the posts' outer faces: flush, the faces share a plane and
    # flicker (z-fighting) in the game wherever a post passes the deck edge or the rim
    sb = JOIST_SET_BACK
    c.add("VerandaDeck", [(x0 + sb, y_out + sb, DECK_TOP - 0.045, x1 - sb, y_in, DECK_TOP)], "post")
    jz0, jz1 = DECK_TOP - 0.22, DECK_TOP - 0.045
    c.add("VerandaJoists", [(x0 + sb, y_out + sb, jz0, x1 - sb, y_out + 0.05, jz1),
                            (x0 + sb, y_out + 0.05, jz0, x0 + 0.05, y_in, jz1),
                            (x1 - 0.05, y_out + 0.05, jz0, x1 - sb, y_in, jz1)], "timber")

    # Lean-to roof from the front wall, just above the attic floor, down over the posts
    tn = math.tan(math.radians(VERANDA_PITCH))
    zt = c.F1 + 0.08

    def under(y):
        return zt - (y_in - y) * tn

    y_e = y_out - 0.35
    A, B = Vector((y_in, zt)), Vector((y_e, under(y_e)))
    d = (B - A).normalized()
    n = Vector((d.y, -d.x)) * 0.12
    outline = [tuple(A), tuple(B), tuple(B + n), tuple(A + n)]

    def paint(me):
        ir, isf, it = _mat_index(me, c.m["roof"]), _mat_index(me, c.m["soffit_out"]), _mat_index(me, c.m["timber"])
        for p in me.polygons:
            p.material_index = ir if p.normal.z > 0.5 else isf if p.normal.z < -0.5 else it

    c.solid("VerandaRoof", [_extrude(outline, x0 - 0.15, x1 + 0.15, "X")], paint=paint)
    beam_top = under(y_out + 0.12)
    beam_bot = beam_top - 0.16
    c.add("VerandaBeam", [(x0, y_out, beam_bot, x1, y_out + 0.12, beam_top)], "timber")

    # Steps down from the front edge, in line with the door
    ent = next((o for o in c.plan.floors[0].openings if o.kind == "ENTRANCE"), None)
    sc = (ent.s0 + ent.s1) / 2 if ent else W / 2
    sc = min(max(sc, x0 + 1.0), x1 - 1.0)
    g0, g1 = sc - 0.55, sc + 0.55

    yp = y_out + 0.06
    xs = [x0 + 0.06, g0 - 0.06, g1 + 0.06, x1 - 0.06]
    posts_x = []
    for a, b in zip(xs, xs[1:]):                        # no post further than 2.4 m from the next
        k = max(1, math.ceil((b - a) / 2.4)) if (a, b) != (xs[1], xs[2]) else 1
        posts_x += [a + (b - a) * i / k for i in range(k)]
    posts_x.append(xs[-1])
    c.add("VerandaPosts", [_post(x, yp, G, beam_bot) for x in posts_x], "veranda_post")

    rails, bal = [], []
    for a, b in zip(posts_x, posts_x[1:]):
        if a >= g0 - 0.1 and b <= g1 + 0.1:              # the opening for the steps
            continue
        r, bl = _balustrade("X", yp, a + 0.06, b - 0.06, DECK_TOP)
        rails += r
        bal += bl
    for x in (x0 + 0.06, x1 - 0.06):
        r, bl = _balustrade("Y", x, y_out + 0.12, y_in, DECK_TOP)
        rails += r
        bal += bl
    c.add("VerandaRail", rails, "veranda_rail")
    c.add("VerandaBalusters", bal, "baluster")

    rise = DECK_TOP - G
    n_st = max(2, round(rise / 0.18))
    r, go = rise / n_st, 0.28
    treads = [(g0 + 0.05, y_out - i * go, DECK_TOP - i * r - 0.04, g1 - 0.05, y_out - (i - 1) * go + 0.01,
               DECK_TOP - i * r) for i in range(1, n_st)]
    c.add("VerandaSteps", treads, "post")
    run = n_st * go
    parts = []
    for xa, xb in ((g0, g0 + 0.05), (g1 - 0.05, g1)):
        poly = _clip_z([(0.0, DECK_TOP + 0.02), (run, DECK_TOP + 0.02 - run * r / go),
                        (run, DECK_TOP - 0.2 - run * r / go), (0.0, DECK_TOP - 0.2)], G, DECK_TOP - 0.045)
        parts.append(_extrude([(y_out - dd, z) for dd, z in poly], xa, xb, "X"))
    c.solid("VerandaStringers", parts, "timber", along=(0.0, -go, -r))


# --------------------------------------------------------------------------
# Gambrel roof and chimney
# --------------------------------------------------------------------------

def _roof(c):
    W, D, te, F1, k = c.W, c.D, c.te, c.F1, c.k
    p1, p2 = math.radians(k["pitch_low"]), math.radians(k["pitch_up"])
    bx, zb, zr = k["bx"], k["zb"], k["zr"]
    T = ROOF_T
    x_e = -te / 2 - EAVE
    E = Vector((x_e, F1 + k["knee"] + x_e * math.tan(p1)))
    B = Vector((bx, F1 + zb))
    R = Vector((W / 2, F1 + zr))
    n1, n2 = Vector((-math.sin(p1), math.cos(p1))), Vector((-math.sin(p2), math.cos(p2)))
    d1, d2 = Vector((math.cos(p1), math.sin(p1))), Vector((math.cos(p2), math.sin(p2)))
    Eo = E + n1 * T
    B1, B2 = B + n1 * T, B + n2 * T                     # the outer lines meet at Bo
    det = d2.x * d1.y - d1.x * d2.y
    s = ((B2 - B1).x * -d2.y + d2.x * (B2 - B1).y) / det
    Bo = B1 + d1 * s
    Ro = B2 + d2 * ((W / 2 - B2.x) / d2.x)

    def m(v):
        return (W - v.x, v.y)

    outline = [tuple(E), tuple(B), tuple(R), m(B), m(E), m(Eo), m(Bo), tuple(Ro), tuple(Bo), tuple(Eo)]
    caps = [[0, 1, 8, 9], [1, 2, 7, 8], [2, 3, 6, 7], [3, 4, 5, 6]]
    y0, y1 = -te / 2 - VERGE, D + te / 2 + VERGE

    c.solid("Roof", [_extrude(outline, y0, y1, "Y", caps)], paint=roof_paint(c))
    c.add("RoofRidge", [(W / 2 - 0.12, y0, Ro.y - 0.05, W / 2 + 0.12, y1, Ro.y + 0.03)], "roof")
    c.ridge_top = Ro.y


def roof_paint(c):
    """Per-face materials for a roof extruded along y: sheet on top, pine lining under it
    inside the attic, weathered boards under the eaves and verges, timber edges."""
    W, D, te = c.W, c.D, c.te

    def paint(me):
        # Split the underside along the outer wall faces
        o = te / 2
        _split(me, [((c.center.x - o, 0, 0), (1, 0, 0)), ((c.center.x + W + o, 0, 0), (1, 0, 0)),
                    ((0, c.center.y - o, 0), (0, 1, 0)), ((0, c.center.y + D + o, 0), (0, 1, 0))])
        ir, it = _mat_index(me, c.m["roof"]), _mat_index(me, c.m["timber"])
        isf, iso = _mat_index(me, c.m["soffit"]), _mat_index(me, c.m["soffit_out"])
        for p in me.polygons:
            nm, pc = p.normal, p.center - c.center
            if abs(nm.y) > 0.9:
                p.material_index = it                   # the verge boards at the gables
            elif nm.z > 0.2:
                p.material_index = ir
            elif nm.x * (W / 2 - pc.x) > 0:             # underside
                inside = -o < pc.x < W + o and -o < pc.y < D + o
                p.material_index = isf if inside else iso
            else:
                p.material_index = it                   # eave fascias
    return paint


def _chimney(c):
    W, k = c.W, c.k
    cy = k["chimney_y"]
    z0, z1 = c.F1 + k["zr"] + 0.01, c.ridge_top + 0.75
    c.add("Chimney", [(W / 2 - 0.26, cy - 0.26, z0, W / 2 + 0.26, cy + 0.26, z1)], "chimney")
    c.add("ChimneyCap", [(W / 2 - 0.31, cy - 0.31, z1, W / 2 + 0.31, cy + 0.31, z1 + 0.07)], "chimney_cap")


# --------------------------------------------------------------------------
# Stair
# --------------------------------------------------------------------------

def _stair(c):
    """A steep straight flight against the bedroom wall, open treads between two stringers,
    balusters and a handrail on the open side, and a rail round the hole upstairs."""
    hx0, hy0, hx1, hy1 = c.k["hole"]
    up, n, Hs, ti = c.k["up"], c.k["risers"], c.F1, c.ti
    r = Hs / n
    x_top, x_bot = (hx0 + ti / 2, hx1) if up < 0 else (hx1 - ti / 2, hx0)
    L = abs(x_top - x_bot)
    g = L / (n - 1)
    ya, yb = hy0, hy1 - ti / 2                          # open side, wall side
    sw = 0.05

    def X(d):
        return x_bot + up * d

    def line(d):                                        # through the tread nosings
        return r + d * r / g

    treads = []
    for i in range(1, n):
        xa, xb = sorted((X((i - 1) * g - 0.02), X(i * g)))
        treads.append((xa, ya + sw, i * r - 0.045, xb, yb - sw, i * r))
    # Fill the slot between the top step and the attic floor (the wall below stops at the ceiling)
    xa, xb = sorted((x_top, x_top + up * ti / 2))
    treads.append((xa, ya, c.H, xb, hy1, Hs))
    stringers = [_stringer(x_bot, up, r / g, r, 0.03, 0.25, L, 0.0, Hs, y0, y1)
                 for y0, y1 in ((ya, ya + sw), (yb - sw, yb))]

    hand_y = ya + 0.025
    bal = [(X((i - 0.5) * g) - 0.02, ya + 0.005, line((i - 0.5) * g), X((i - 0.5) * g) + 0.02, ya + 0.045,
            line((i - 0.5) * g) + 0.86) for i in range(1, n)]
    bal = [(min(b[0], b[3]), b[1], b[2], max(b[0], b[3]), b[4], b[5]) for b in bal]
    newels = [_post(X(0.04), ya + 0.035, 0.0, line(0.04) + 0.95, 0.07),
              _post(X(L - 0.04), ya + 0.035, Hs - 0.25, Hs + 0.95, 0.07)]
    hand = _sheared_box((X(0.0), hand_y, line(0.0)), (X(L), hand_y, Hs), 0.03, 0.86, 0.92)

    # Upstairs: rail along both long sides of the hole and across its far end
    rails, bal_up = [], []
    s0, s1 = sorted((x_top, x_bot))
    for axis, cc, a, b in (("X", hy0 - 0.03, s0, s1), ("X", hy1 + 0.03, s0, s1),
                           ("Y", x_bot - up * 0.03, hy0 - 0.03, hy1 + 0.03)):
        rl, bl = _balustrade(axis, cc, a, b, Hs)
        rails += rl
        bal_up += bl
    newels += [_post(x_bot - up * 0.03, y, Hs, Hs + 0.95, 0.07) for y in (hy0 - 0.03, hy1 + 0.03)]
    newels.append(_post(x_top, hy1 + 0.03, Hs, Hs + 0.95, 0.07))

    c.add("StairTreads", treads, "stair")
    c.solid("StairStringers", stringers + [hand], "stair", along=(up * g, 0.0, r))
    c.add("StairBalusters", bal + bal_up, "stair_v")
    c.add("StairNewels", newels, "stair_v")
    c.add("StairRail", rails, "stair")
