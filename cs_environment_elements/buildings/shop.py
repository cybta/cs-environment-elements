"""Shopping-row exterior: everything house.py's walls, floors and stairs don't cover.

After the old high-street shopfronts in the user's references: stone pilasters between
the shops, a painted timber shopfront for each (posts, stall risers under the display
windows, a glazed door with a fanlight, a fascia carrying the shop's name in gilt
letters), a canvas awning, a belt course at the upper floor, and tall upper windows
with stone surrounds, hoods (segmental arches, pediments or flat cornices) and flower
boxes. The end shops wrap their shopfront round the corner (display windows, fascia and
name on the side wall), and those side walls are dressed like the front. The shared
entrance gets a pair of doors under a hood and lanterns either side. shop_extras builds
the roof, cornice, parapet, sidewalk, signs and props.

Plan coordinates: street front at y = 0 (the wall's centre line), ground-floor top at
z = 0. Everything is boxes and extruded outlines, merged into a few objects per row.
UVs are metric; each box's texture U runs along its longest side, so the painted
timber's grain follows every stile and rail.
"""

import math
import random

from mathutils import Vector

from . import shop_extras as ex
from . import shop_materials as sm
from .cottage import _extrude
from .house_walls import _wall_box
from .mesh_utils import _obj, _solid

BOX_FACES = ([0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7])
PIL_G, PIL_U = 0.5, 0.42        # pilaster widths, ground and upper floor
HOODS = ("arch", "pediment", "cornice")
UP, XAX = Vector((0.0, 0.0, 1.0)), Vector((1.0, 0.0, 0.0))


def box_part(b):
    """An axis-aligned box (x0, y0, z0, x1, y1, z1) -> (verts, faces)."""
    x0, y0, z0, x1, y1, z1 = b
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    return verts, [list(f) for f in BOX_FACES]


def _long_axis(b):
    size = (b[3] - b[0], b[4] - b[1], b[5] - b[2])
    k = max(range(3), key=lambda i: size[i])
    return Vector([1.0 if i == k else 0.0 for i in range(3)])


class Face:
    """One outer wall face. `s` runs along the wall, `d` outwards from its surface."""

    def __init__(self, axis, plane, out, read):
        self.axis, self.plane, self.out = axis, plane, out
        self.read = read            # +1 if text reads towards +s seen from outside

    def box(self, s0, s1, z0, z1, d, back=0.01):
        a, b = sorted((self.plane + self.out * d, self.plane - self.out * back))
        return (s0, a, z0, s1, b, z1) if self.axis == "X" else (a, s0, z0, b, s1, z1)

    def extrude(self, outline, d0, d1, caps=None):
        """An (s, z) outline pushed out from d0 to d1."""
        a, b = sorted((self.plane + self.out * d0, self.plane + self.out * d1))
        return _extrude(outline, a, b, "Y" if self.axis == "X" else "X", caps)

    def pt(self, s, d, z):
        p = self.plane + self.out * d
        return (s, p, z) if self.axis == "X" else (p, s, z)

    def radii(self, rs, rd):
        return (rs, rd) if self.axis == "X" else (rd, rs)


class _Ctx:
    """Collects parts per object (label) with a material each, then builds one mesh per label."""

    def __init__(self, s, plan, mats, coll, root, name, center):
        self.s, self.plan, self.m, self.coll, self.root, self.name, self.center = s, plan, mats, coll, root, name, center
        self.g = s.shop                                   # the shopping-row settings
        self.W, self.D, self.te, self.ti = plan.W, plan.D, plan.t_ext, plan.t_int
        self.H, self.F1, self.slab = plan.ceiling_h, plan.storey_h, plan.slab
        self.k = plan.shops
        self.yf = -plan.t_ext / 2                         # street face of the front wall
        self.yb = plan.D + plan.t_ext / 2                 # back face
        self.RB = self.F1 + self.H                        # underside of the roof slab
        self.rng = random.Random(s.seed * 29 + 3)
        te = plan.t_ext
        self.front = Face("X", -te / 2, -1, 1)
        self.back = Face("X", plan.D + te / 2, 1, -1)
        self.left = Face("Y", -te / 2, -1, -1)
        self.right = Face("Y", plan.W + te / 2, 1, 1)
        self.dressed = [self.left if x < 1e-4 else self.right for x in self.k["sides"]]
        self.parts = {}

    # -- collecting ------------------------------------------------------------
    def part(self, label, mat, vf, along=None):
        self.parts.setdefault(label, []).append((mat, vf, along))

    def box(self, label, mat, *boxes):
        for b in boxes:
            if min(b[3] - b[0], b[4] - b[1], b[5] - b[2]) > 1e-5:
                self.part(label, mat, box_part(b), _long_axis(b))

    def fbox(self, x0, x1, z0, z1, d, back=0.01):
        """A box standing proud of the street face by d (and 1 cm into the wall)."""
        return self.front.box(x0, x1, z0, z1, d, back)

    def face_of(self, o):
        if o.axis == "X":
            return self.front if o.coord < 1e-4 else self.back
        return self.left if o.coord < 1e-4 else self.right

    def span(self, face, d):
        """s range for a moulding running the length of a face, returned round dressed corners."""
        te = self.te
        if face.axis == "X":
            lo = d if self.left in self.dressed else min(d, 0.06)
            hi = d if self.right in self.dressed else min(d, 0.06)
            return -te / 2 - lo, self.W + te / 2 + hi
        # A side run starts where the front run (which turns the corner) ends, so the two never
        # overlap: overlapping boxes put coplanar faces with different UVs on top of each other.
        return -te / 2 + 0.01, self.D + te / 2

    def run(self, face, z0, z1, d, mat, label="Mouldings"):
        s0, s1 = self.span(face, d)
        self.box(label, mat, face.box(s0, s1, z0, z1, d))

    # -- building --------------------------------------------------------------
    def flush(self):
        for label, items in self.parts.items():
            verts, faces, fmat, fdir, mats = [], [], [], [], []
            for mat, (vs, fs), along in items:
                if mat not in mats:
                    mats.append(mat)
                b = len(verts)
                verts += [Vector(v) + self.center for v in vs]
                faces += [[b + i for i in f] for f in fs]
                fmat += [mats.index(mat)] * len(fs)
                fdir += [along] * len(fs)
            me = _solid(f"{self.name}_{label}", verts, faces)
            for m in mats:
                me.materials.append(m)
            for p, mi in zip(me.polygons, fmat):
                p.material_index = mi
            _uv_along(me, fdir)
            _obj(f"{self.name}_{label}", me, self.coll, self.root)
        self.parts = {}


def _uv_along(me, dirs):
    """Metric UVs, U along each face's direction (projected onto it) or level when it has none."""
    uv = me.uv_layers.new(name="UVMap")
    for p in me.polygons:
        n, a = p.normal, dirs[p.index]
        t = None
        if a is not None:
            t = a - n * a.dot(n)
            t = t if t.length > 1e-4 else None
        if t is None:
            t = UP.cross(n) if abs(n.z) < 0.999 else XAX.copy()
        t.normalize()
        b = n.cross(t)
        for li in p.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (v.dot(t), v.dot(b))


def build_exterior(s, plan, mats, coll, root, name, center):
    c = _Ctx(s, plan, mats, coll, root, name, center)
    shops = [b for b in c.k["bays"] if b["kind"] == "shop"]
    c.looks = sm.looks(len(shops), s.seed)
    c.hood = c.rng.choice(HOODS)
    c.names = ex.shop_names(c, len(shops))
    root["shop_count"] = len(shops)
    root["window_hood"] = c.hood
    root["shop_names"] = ", ".join(c.names)

    _pilasters(c)
    for f in [c.front] + c.dressed:                                  # belt course
        c.run(f, c.F1 - 0.12, c.F1 + 0.06, 0.17, c.m["stone"])
        c.run(f, c.F1 + 0.06, c.F1 + 0.12, 0.21, c.m["stone"])
    ground = c.plan.floors[0].openings
    for b in c.k["bays"]:
        if b["kind"] == "shop":
            _shopfront(c, b, ground)
        else:
            _entry(c, b, next(o for o in ground if getattr(o, "role", "") == "entry"))
    _windows(c)
    _office_plaques(c)
    ex.build(c)
    c.flush()


def _office_plaques(c):
    """A painted board with the office's name in gilt letters over each door, on the corridor side."""
    up = c.plan.floors[1]
    board, gold = c.m["get"](sm.DARK_PAINT), c.m["gold"]
    for o in up.openings:
        if o.kind != "DOOR" or "Corridor" not in o.rooms:
            continue
        name = next((r for r in o.rooms if r.startswith("Office")), None)
        if not name:
            continue
        face = Face("X", o.coord + c.ti / 2, 1, -1)       # the corridor is behind the wall (+y)
        sc, z0 = (o.s0 + o.s1) / 2, up.base_z + o.z1 + 0.1
        c.box("Plaques", board, face.box(sc - 0.3, sc + 0.3, z0, z0 + 0.17, 0.02))
        ex.put_text(c, face, name.upper(), 0.085, 0.5, sc, 0.02, z0 + 0.085, gold)


# --------------------------------------------------------------------------
# Pilasters
# --------------------------------------------------------------------------

def pilaster_span(c, x, w):
    """x range of a pilaster on bay line x; the end ones sit flush with the end walls."""
    if x < 1e-4:
        return -c.te / 2, -c.te / 2 + w
    if x > c.W - 1e-4:
        return c.W + c.te / 2 - w, c.W + c.te / 2
    return x - w / 2, x + w / 2


def bay_lines(c):
    return [b["x0"] for b in c.k["bays"]] + [c.W]


def _pilaster(c, face, p0, p1, q0, q1, lo="flare", hi="flare"):
    """A ground and an upper pilaster on `face`. Each end either flares (base and capitals a
    little wider), wraps a dressed corner (every course reaches round by its own depth, so it
    covers the corner square) or abuts the wrapping pilaster of the other face (stops flat)."""
    st, F1, RB = c.m["stone"], c.F1, c.RB

    def piece(a, b, z0, z1, d, flare):
        a -= {"flare": flare, "wrap": d, "abut": 0.0}[lo]
        b += {"flare": flare, "wrap": d, "abut": 0.0}[hi]
        return face.box(a, b, z0, z1, d)

    c.box("Mouldings", st,
          piece(p0, p1, -c.slab, F1 - 0.12, 0.1, 0.0),                    # shaft
          piece(p0, p1, -c.slab, 0.3, 0.14, 0.04),                         # base
          piece(p0, p1, F1 - 0.32, F1 - 0.12, 0.14, 0.04),                 # capital
          piece(q0, q1, F1 + 0.12, RB - 0.2, 0.07, 0.0),                   # upper shaft and capital
          piece(q0, q1, RB - 0.38, RB - 0.2, 0.11, 0.03))


def _pilasters(c):
    for x in bay_lines(c):
        lo = "wrap" if x < 1e-4 and c.left in c.dressed else "flare"
        hi = "wrap" if x > c.W - 1e-4 and c.right in c.dressed else "flare"
        _pilaster(c, c.front, *pilaster_span(c, x, PIL_G), *pilaster_span(c, x, PIL_U), lo, hi)
    te, D = c.te, c.D
    for f in c.dressed:                                                  # the corners of a dressed side
        a = -te / 2 + 0.01                                               # behind the front's corner pilaster
        _pilaster(c, f, a, -te / 2 + PIL_G, a, -te / 2 + PIL_U, lo="abut")
        _pilaster(c, f, D + te / 2 - PIL_G, D + te / 2, D + te / 2 - PIL_U, D + te / 2)


# --------------------------------------------------------------------------
# Shopfronts
# --------------------------------------------------------------------------

def zone(c, b):
    """The shopfront's x range: between the pilasters of its bay."""
    return pilaster_span(c, b["x0"], PIL_G)[1] + 0.03, pilaster_span(c, b["x1"], PIL_G)[0] - 0.03


def _gaps(a, b, spans, grow=0.02):
    """Pieces of [a, b] not covered by the (s0, s1) spans, each grown into its neighbours."""
    out, cur = [], a
    for s0, s1 in sorted(spans):
        if s0 > cur + 1e-4:
            out.append((cur - (grow if cur > a else 0.0), s0 + grow))
        cur = max(cur, s1)
    if b > cur + 1e-4:
        out.append((cur - grow, b))
    return out


def _shopfront(c, b, ground):
    paint_n, canvas_n, striped = c.looks[b["index"]]
    paint = c.m["get"](paint_n)
    name = c.names[b["index"]]
    opens = [o for o in ground if getattr(o, "role", "") in ("door", "display") and o.axis == "X"
             and b["x0"] < o.s0 < b["x1"]]
    za, zb = zone(c, b)
    _front_parts(c, c.front, za, zb, opens, paint, name, paint_n)
    if c.g.awnings:
        _awning(c, za + 0.05, zb - 0.05, c.k["sign0"] - 0.03, c.m["get"](canvas_n), striped)
    for x in b["sides"]:                                    # wrapped round the corner
        face = c.left if x < 1e-4 else c.right
        side = [o for o in ground if getattr(o, "role", "") == "display" and o.axis == "Y" and abs(o.coord - x) < 1e-4]
        if side:
            _front_parts(c, face, -c.te / 2 + PIL_G + 0.03, max(o.s1 for o in side) + 0.15, side, paint, name, paint_n)


def _front_parts(c, face, za, zb, opens, paint, name, paint_n):
    """Posts, head rail, fascia, stall risers and frames of a shopfront on one face, za..zb along it."""
    k = c.k
    top, sill = k["top"], k["sill"]
    L = "Shopfronts"
    for g0, g1 in _gaps(za, zb, [(o.s0, o.s1) for o in opens]):     # posts and piers
        c.box(L, paint, face.box(g0, g1, 0.0, top + 0.15, 0.07))
    c.box(L, paint, face.box(za, zb, top, top + 0.15, 0.07))         # head rail
    s0, s1 = k["sign0"], k["sign1"]
    c.box(L, paint, face.box(za, zb, s0 - 0.05, s0, 0.16), face.box(za, zb, s0, s1, 0.13),
          face.box(za, zb, s1, s1 + 0.07, 0.18))
    for o in opens:
        if o.role == "display":
            c.box(L, paint,
                  face.box(o.s0 - 0.02, o.s1 + 0.02, 0.0, sill, 0.09),                 # stall riser
                  face.box(o.s0 + 0.12, o.s1 - 0.12, 0.1, sill - 0.1, 0.12),           # its raised panel
                  face.box(o.s0 - 0.05, o.s1 + 0.05, sill - 0.04, sill + 0.02, 0.14))  # sill ledge
            _display_frame(c, o, paint)
        else:
            door(c, o, paint, leaves=1)
    if c.g.signs and name:
        dark = paint_n in sm.LIGHT_PAINTS
        ex.sign_text(c, face, name, (za + zb) / 2, zb - za - 0.6, 0.13, s0, s1,
                     c.m["get"](sm.DARK_PAINT) if dark else c.m["gold"])


def _in_opening(o, s0, s1, z0, z1, depth, base=0.0):
    return _wall_box(o.axis, o.coord, depth, s0, s1, base + z0, base + z1)


def _display_frame(c, o, paint, fw=0.06, depth=0.1):
    """Frame, mullions and a transom (upper lights) inside a display window."""
    s0, s1, z0, z1 = o.s0, o.s1, o.z0, o.z1
    bx = [_in_opening(o, s0, s0 + fw, z0, z1, depth), _in_opening(o, s1 - fw, s1, z0, z1, depth),
          _in_opening(o, s0, s1, z1 - fw, z1, depth), _in_opening(o, s0, s1, z0, z0 + fw, depth)]
    n = max(1, math.ceil((s1 - s0) / 1.4))
    for i in range(1, n):
        m = s0 + (s1 - s0) * i / n
        bx.append(_in_opening(o, m - 0.03, m + 0.03, z0, z1, depth))
    if z1 - z0 > 1.5:
        t = z1 - 0.45
        bx.append(_in_opening(o, s0, s1, t - 0.03, t + 0.03, depth))
    c.box("Shopfronts", paint, *bx)


def door(c, o, paint, leaves=1, base=0.0):
    """A glazed shop door: frame, leaves with a raised kick panel and glass, a fanlight over
    a transom, and pull handles on both faces."""
    L, G = "Shopfronts", "ShopGlass"
    s0, s1, z1, fw = o.s0, o.s1, o.z1, 0.06
    c.box(L, paint, _in_opening(o, s0, s0 + fw, 0.0, z1, 0.12, base), _in_opening(o, s1 - fw, s1, 0.0, z1, 0.12, base),
          _in_opening(o, s0, s1, z1 - fw, z1, 0.12, base))
    zt = z1 - 0.4 if z1 - 0.4 >= 2.0 else None
    if zt:
        c.box(L, paint, _in_opening(o, s0 + fw, s1 - fw, zt - 0.03, zt + 0.03, 0.1, base))
        c.box(G, c.m["glass"], _in_opening(o, s0 + fw, s1 - fw, zt + 0.03, z1 - fw, 0.008, base))
    lt = (zt - 0.03) if zt else z1 - fw
    a, b = s0 + fw + 0.004, s1 - fw - 0.004
    for i in range(leaves):
        l0 = a + (b - a) * i / leaves + (0.003 if i else 0.0)
        l1 = a + (b - a) * (i + 1) / leaves - (0.003 if i < leaves - 1 else 0.0)
        st = 0.1 if l1 - l0 > 0.6 else 0.08
        c.box(L, paint,
              _in_opening(o, l0, l0 + st, 0.005, lt, 0.05, base), _in_opening(o, l1 - st, l1, 0.005, lt, 0.05, base),
              _in_opening(o, l0 + st, l1 - st, lt - 0.1, lt, 0.05, base),
              _in_opening(o, l0 + st, l1 - st, 0.5, 0.56, 0.06, base),                   # lock rail
              _in_opening(o, l0 + st, l1 - st, 0.005, 0.5, 0.05, base),                  # kick panel
              _in_opening(o, l0 + st + 0.05, l1 - st - 0.05, 0.08, 0.43, 0.07, base))    # its raised field
        c.box(G, c.m["glass"], _in_opening(o, l0 + st, l1 - st, 0.56, lt - 0.1, 0.008, base))
        hx = l1 - st / 2 if i == 0 else l0 + st / 2                                       # the meeting / lock side
        for sg in (-1.0, 1.0):                                                           # both faces (doors are on X walls)
            ya, yb = sorted((o.coord + sg * 0.06, o.coord + sg * 0.09))
            c.box("Hardware", c.m["metal"], (hx - 0.015, ya, base + 0.85, hx + 0.015, yb, base + 1.35))
            sa, sb = sorted((o.coord + sg * 0.025, o.coord + sg * 0.06))
            for z in (0.9, 1.3):                                                         # stand-offs
                c.box("Hardware", c.m["metal"], (hx - 0.01, sa, base + z - 0.01, hx + 0.01, sb, base + z + 0.01))


def _awning(c, x0, x1, z_a, canvas, striped, proj=1.1, drop=0.4, t=0.025, val=0.22):
    """A sloping canvas awning with a valance and side cheeks; stripes are separate strips."""
    y_a = c.yf - 0.17
    y_e, z_e = y_a - proj, z_a - drop
    slope = Vector((0.0, -proj, -drop)).normalized()
    n = max(1, round((x1 - x0) / 0.32)) if striped else 1
    stripe = c.m["stripe"]
    for i in range(n):
        a, b = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
        mat = stripe if striped and i % 2 else canvas
        c.part("Awnings", mat, _extrude([(y_a, z_a), (y_e, z_e), (y_e, z_e - t), (y_a, z_a - t)], a, b, "X"), slope)
        c.part("Awnings", mat, _extrude([(y_e, z_e), (y_e, z_e - val), (y_e - t, z_e - val), (y_e - t, z_e)], a, b, "X"),
               UP)
    side = [(y_a, z_a), (y_e, z_e), (y_e, z_e - val), (y_a, z_e - val - 0.15)]
    for a in (x0, x1 - 0.02):
        c.part("Awnings", canvas, _extrude(side, a, a + 0.02, "X"), slope)
    # A metal bar behind the valance, and two arms back to the wall
    c.box("Hardware", c.m["metal"], (x0 + 0.02, y_e + 0.002, z_e - 0.06, x1 - 0.02, y_e + 0.04, z_e - t - 0.002))
    for a in (x0 + 0.15, x1 - 0.15):
        c.part("Hardware", c.m["metal"], _extrude([(c.yf, z_e - 0.25), (y_e + 0.02, z_e - 0.02), (y_e + 0.02, z_e - 0.05),
                                                   (c.yf, z_e - 0.28)], a - 0.012, a + 0.012, "X"))


# --------------------------------------------------------------------------
# The shared entrance
# --------------------------------------------------------------------------

def _entry(c, b, o):
    door(c, o, c.m["get"](sm.DARK_PAINT), leaves=2)
    st, z1 = c.m["stone"], o.z1
    c.box("Mouldings", st,
          c.fbox(o.s0 - 0.14, o.s0, 0.0, z1, 0.06), c.fbox(o.s1, o.s1 + 0.14, 0.0, z1, 0.06),       # architraves
          c.fbox(o.s0 - 0.14, o.s1 + 0.14, z1, z1 + 0.12, 0.06),
          c.fbox(o.s0 - 0.28, o.s1 + 0.28, z1 + 0.12, z1 + 0.28, 0.24),                             # hood
          c.fbox(o.s0 - 0.24, o.s0 - 0.12, z1 - 0.3, z1 + 0.12, 0.18),                              # consoles
          c.fbox(o.s1 + 0.12, o.s1 + 0.24, z1 - 0.3, z1 + 0.12, 0.18))
    p0 = pilaster_span(c, b["x0"], PIL_G)[1]                                                        # plinth
    p1 = pilaster_span(c, b["x1"], PIL_G)[0]
    for a, bb in ((p0, o.s0 - 0.14), (o.s1 + 0.14, p1)):
        c.box("Mouldings", st, c.fbox(a, bb, -c.slab, 0.4, 0.04))
    for x in (b["x0"], b["x1"]):
        _lantern(c, x)


def _lantern(c, x):
    m, gl = c.m["metal"], c.m["glass"]
    y = c.yf - 0.1                                      # the pilaster's face
    c.box("Hardware", m, (x - 0.025, y - 0.32, 2.38, x + 0.025, y + 0.01, 2.43),     # arm
          (x - 0.13, y - 0.53, 2.28, x + 0.13, y - 0.27, 2.34),                     # roof
          (x - 0.04, y - 0.44, 2.34, x + 0.04, y - 0.36, 2.43),
          (x - 0.09, y - 0.49, 1.86, x + 0.09, y - 0.31, 1.91))                     # base
    for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):                               # corner bars
        cx, cy = x + dx * 0.085, y - 0.4 + dy * 0.085
        c.box("Hardware", m, (cx - 0.01, cy - 0.01, 1.91, cx + 0.01, cy + 0.01, 2.28))
    c.box("ShopGlass", gl, (x - 0.08, y - 0.48, 1.91, x + 0.08, y - 0.32, 2.28))


# --------------------------------------------------------------------------
# Windows: frames everywhere; surrounds, hoods and flower boxes on the dressed faces
# --------------------------------------------------------------------------

def _windows(c):
    frame = c.m["frame"]
    for f in c.plan.floors:
        base = f.base_z
        for o in f.openings:
            if o.kind != "WINDOW" or getattr(o, "role", "") == "display":
                continue
            _sash(c, o, base, frame)
            face = c.face_of(o)
            if getattr(o, "role", "") == "upper":
                _surround(c, face, o, base)
            else:                                       # back and corridor windows: a plain stone sill
                c.box("Mouldings", c.m["stone"], face.box(o.s0 - 0.06, o.s1 + 0.06, base + o.z0 - 0.06, base + o.z0, 0.06))


def _sash(c, o, base, frame, fw=0.06, depth=0.08):
    s0, s1, z0, z1 = o.s0, o.s1, o.z0, o.z1
    bx = [_in_opening(o, s0, s0 + fw, z0, z1, depth, base), _in_opening(o, s1 - fw, s1, z0, z1, depth, base),
          _in_opening(o, s0, s1, z1 - fw, z1, depth, base), _in_opening(o, s0, s1, z0, z0 + fw, depth, base)]
    if s1 - s0 >= 0.8:
        m = (s0 + s1) / 2
        bx.append(_in_opening(o, m - 0.025, m + 0.025, z0, z1, depth, base))
    if z1 - z0 >= 1.2:
        t = z0 + (z1 - z0) * 0.7
        bx.append(_in_opening(o, s0, s1, t - 0.025, t + 0.025, depth, base))
    c.box("WindowFrames", frame, *bx)


def _surround(c, face, o, base):
    st = c.m["stone"]
    s0, s1, z0, z1 = o.s0, o.s1, base + o.z0, base + o.z1
    sc = (s0 + s1) / 2
    c.box("Mouldings", st,
          face.box(s0 - 0.1, s0, z0, z1, 0.05), face.box(s1, s1 + 0.1, z0, z1, 0.05),     # architraves
          face.box(s0 - 0.1, s1 + 0.1, z1, z1 + 0.1, 0.05),
          face.box(s0 - 0.1, s1 + 0.1, z0 - 0.08, z0, 0.1))                              # sill
    zh = z1 + 0.1
    if c.hood == "arch":
        hc, rise, t = (s1 - s0) / 2 + 0.1, 0.24, 0.12
        R = (hc * hc + rise * rise) / (2 * rise)
        cz = zh + rise - R
        ph = math.asin(min(1.0, hc / R))
        k = 8
        angs = [-ph + 2 * ph * i / k for i in range(k + 1)]
        inner = [(sc + R * math.sin(a), cz + R * math.cos(a)) for a in angs]
        outer = [(sc + (R + t) * math.sin(a), cz + (R + t) * math.cos(a)) for a in angs]
        caps = [[i, i + 1, 2 * k - i, 2 * k + 1 - i] for i in range(k)]
        c.part("Mouldings", st, face.extrude(outer + inner[::-1], -0.01, 0.09, caps))
        c.part("Mouldings", st, face.extrude(inner, -0.01, 0.03))                          # tympanum
        c.box("Mouldings", st, face.box(sc - 0.08, sc + 0.08, zh + rise - 0.06, zh + rise + t + 0.06, 0.12))
    elif c.hood == "pediment":
        hw = (s1 - s0) / 2 + 0.18
        c.box("Mouldings", st, face.box(sc - hw - 0.03, sc + hw + 0.03, zh, zh + 0.07, 0.15))
        c.part("Mouldings", st, face.extrude([(sc - hw, zh + 0.07), (sc + hw, zh + 0.07), (sc, zh + 0.36)], -0.01, 0.12))
    else:
        c.box("Mouldings", st, face.box(s0 - 0.16, s1 + 0.16, zh, zh + 0.15, 0.16),
              face.box(s0 - 0.15, s0 - 0.05, z1 - 0.18, zh, 0.13), face.box(s1 + 0.05, s1 + 0.15, z1 - 0.18, zh, 0.13))
    if c.g.flower_boxes and c.rng.random() < 0.6:
        _flower_box(c, face, s0, s1, z0)


def _flower_box(c, face, s0, s1, z0):
    c.box("Props", c.m["metal"], face.box(s0 + 0.02, s1 - 0.02, z0 - 0.02, z0 + 0.17, 0.3),
          face.box(s0 + 0.08, s0 + 0.13, z0 - 0.2, z0 - 0.02, 0.26), face.box(s1 - 0.13, s1 - 0.08, z0 - 0.2, z0 - 0.02, 0.26))
    n = max(2, round((s1 - s0) / 0.28))
    for i in range(n):
        s = s0 + 0.1 + (s1 - s0 - 0.2) * (i + 0.5) / n
        r = c.rng.uniform(0.12, 0.17)
        rx, ry = face.radii(r, 0.13)
        c.part("Props", c.m["leaves"], ex.blob(*face.pt(s, 0.16, z0 + 0.19), rx, ry, r * 0.8, c.rng))
