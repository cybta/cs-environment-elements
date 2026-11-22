"""Villa exteriors: everything house.py's walls and floors don't cover.

Roofs (a flat slab with a deep overhang, or a steep gable with skylights),
window frames, the carport, balcony rails, the entrance, and the driveway
and paving around the house. Works in plan coordinates (front of the house at
y = 0, ground floor at z = 0, ground level one slab below that).
"""

import math

from mathutils import Matrix, Vector

from .house_walls import OUTDOOR, _wall_box
from .mesh_utils import _boxes_mesh, _clip_mesh, _mat_index, _obj, _paint_by_normal

EPS = 1e-4
FRONT_YARD = 6.0        # facade to the street, for the driveway and front path
ROOF_T = 0.24           # gable roof thickness


class _Ctx:
    def __init__(self, s, plan, mats, coll, root, name, center):
        self.s, self.plan, self.mats = s, plan, mats
        self.coll, self.root, self.name, self.center = coll, root, name, center
        self.W, self.D, self.te = plan.W, plan.D, plan.t_ext
        self.H, self.F1, self.G = plan.ceiling_h, plan.storey_h, -plan.slab
        self.ground, self.upper = plan.floors[0], plan.floors[1]
        self.modern = plan.villa["style"] == "MODERN"
        self.drive = None           # (x0, x1, y) where the driveway meets the carport

    def planes(self, floor):
        """The roof planes that trim this floor, in mesh coordinates."""
        off = self.center + Vector((0, 0, floor.base_z))
        return [(Vector(co) + off, Vector(no)) for co, no in self.plan.clip.get(floor.index, ())]

    def add(self, label, boxes, mat=None, paint=None, planes=None):
        """One object from boxes. `paint` = (top, bottom, side) materials by face direction."""
        if not boxes:
            return None
        me = _boxes_mesh(f"{self.name}_{label}", boxes, self.center)
        if planes:
            _clip_mesh(me, planes)
        if paint:
            _paint_by_normal(me, *paint)
        return _obj(f"{self.name}_{label}", me, self.coll, self.root, [mat] if mat else ())


def build_exterior(s, plan, mats, coll, root, name, center):
    c = _Ctx(s, plan, mats, coll, root, name, center)
    root["villa_style"] = plan.villa["style"]
    _frames(c)
    _open_air(c)
    _entrance(c)
    if c.modern:
        _flat_roof(c)
    else:
        _gable_roof(c)
        _carport_wing(c)
    if s.villa_site:
        _site(c)
    if s.villa_pool:
        _pool(c)


# --------------------------------------------------------------------------
# Window frames
# --------------------------------------------------------------------------

def _frames(c, fw=0.05, depth=0.08):
    """Dark frames (and mullions on wide panes) around every outside window."""
    for f in c.plan.floors:
        boxes = []
        for o in f.openings:
            if not o.exterior or o.kind not in ("WINDOW", "PATIO"):
                continue

            def bar(s0, s1, z0, z1):
                b = _wall_box(o.axis, o.coord, depth, s0, s1, z0, z1)
                boxes.append((b[0], b[1], b[2] + f.base_z, b[3], b[4], b[5] + f.base_z))

            bar(o.s0, o.s0 + fw, o.z0, o.z1)
            bar(o.s1 - fw, o.s1, o.z0, o.z1)
            bar(o.s0 + fw, o.s1 - fw, o.z1 - fw, o.z1)
            bar(o.s0 + fw, o.s1 - fw, o.z0, o.z0 + (fw if o.z0 > 0.05 else 0.03))
            n = round((o.s1 - o.s0) / 1.2) if o.s1 - o.s0 > 1.9 else 1
            for k in range(1, n):
                m = o.s0 + (o.s1 - o.s0) * k / n
                bar(m - fw / 2, m + fw / 2, o.z0, o.z1 - fw)
        c.add(f"{f.label}_Frames", boxes, c.mats["trim"], planes=c.planes(f))


# --------------------------------------------------------------------------
# Carport, terrace and balcony: beams, posts, side walls, rails
# --------------------------------------------------------------------------

def _open_air(c):
    W, D, te, H, G, F1 = c.W, c.D, c.te, c.H, c.G, c.F1
    white, posts, glass, rails = [], [], [], []

    for r in c.ground.rooms:
        if r.kind not in OUTDOOR:
            continue
        west, east, south, north = r.x0 < EPS, r.x1 > W - EPS, r.y0 < EPS, r.y1 > D - EPS
        xa = r.x0 - te / 2 if west else r.x0 + te / 2
        xb = r.x1 + te / 2 if east else r.x1 - te / 2
        # A beam under the upper floor along each open edge; the carport's side is a full wall
        for on, y in ((south, 0.0), (north, D)):
            if on:
                white.append((xa, y - te / 2, H - 0.3, xb, y + te / 2, H))
        for on, x in ((west, 0.0), (east, W)):
            if on:
                z0 = G if r.kind == "carport" else H - 0.3
                white.append((x - te / 2, r.y0 + te / 2, z0, x + te / 2, r.y1 - te / 2, H))
        if r.kind == "carport":
            c.drive = (r.x0, r.x1, -te / 2)
            continue
        for xon, x in ((west, 0.0), (east, W)):          # a slim post at each free corner
            for yon, y in ((south, 0.0), (north, D)):
                if xon and yon:
                    posts.append((x - 0.07, y - 0.07, G, x + 0.07, y + 0.07, H - 0.3))

    side = []
    for r in c.upper.rooms:
        if r.kind != "balcony":
            continue
        # Glass rail along the front, between the side wall and the bay
        y = -te / 2 + 0.05
        glass.append((r.x0 + te / 2, y, F1, r.x1 - te / 2, y + 0.012, F1 + 1.0))
        rails.append((r.x0 + te / 2, y - 0.02, F1 + 1.0, r.x1 - te / 2, y + 0.035, F1 + 1.04))
        # Its outer side: a full-height fin (modern) or the knee wall under the roof (gable)
        for on, x in ((r.x0 < EPS, 0.0), (r.x1 > W - EPS, W)):
            if on:
                top = F1 + (H if c.modern else c.plan.villa["ridge_z"])
                side.append((x - te / 2, -te / 2, F1 - 0.02, x + te / 2, r.y1 - te / 2, top))

    c.add("Beams", white, c.mats["wall_out"])
    c.add("Posts", posts, c.mats["trim"])
    c.add("BalconySide", side, c.mats["wall_out"], planes=c.planes(c.upper))
    c.add("BalconyGlass", glass, c.mats["glass"])
    c.add("BalconyRail", rails, c.mats["trim"])


def _entrance(c):
    ent = next((o for o in c.ground.openings if o.kind == "ENTRANCE"), None)
    if ent is None:
        return
    te = c.te
    c.add("EntranceStep", [(ent.s0 - 0.4, -te / 2 - 1.0, c.G, ent.s1 + 0.4, -te / 2, -0.03)], c.mats["paving"])
    if not c.modern:    # the modern villa's door already sits under the balcony band
        c.add("EntranceCanopy", [(ent.s0 - 0.5, -te / 2 - 1.1, 2.4, ent.s1 + 0.5, -te / 2, 2.5)], c.mats["trim"])


# --------------------------------------------------------------------------
# Roofs
# --------------------------------------------------------------------------

def _flat_roof(c):
    """Ceiling slab, then a roof slab with a deep front overhang and a timber soffit."""
    W, D, te, m = c.W, c.D, c.te, c.mats
    top = c.F1 + c.H
    slab = c.plan.slab
    c.add("TopCeiling", [(-te / 2, -te / 2, top, W + te / 2, D + te / 2, top + slab)],
          paint=(m["roof_flat"], m["ceiling"], m["wall_out"]))
    c.add("Roof", [(-te / 2 - 0.35, -te / 2 - 1.1, top + slab, W + te / 2 + 0.35, D + te / 2 + 0.5, top + slab + 0.28)],
          paint=(m["roof_flat"], m["soffit_wood"], m["trim"]))
    # A stone blade standing proud of the bay's outer corner, ground to roof
    bay = c.upper.room(c.plan.villa["bay"])
    x0 = W + te / 2 if bay.x1 > W - EPS else -te / 2 - 0.3
    c.add("StoneBlade", [(x0, -te / 2 - 0.6, c.G, x0 + 0.3, 2.2, top + slab)], m["accent"])


def _skylights(c, x_e, tn, cs, y0, y1):
    """Skylight holes per slope: {'W': [(u0, u1, v0, v1)], 'E': [...]} in slope coordinates."""
    knee = c.plan.villa["knee"]
    v0 = ((1.45 - knee) / tn - x_e) / cs       # low edge about 1.45 m above the floor
    holes = {"W": [], "E": []}
    for r in c.upper.rooms:
        if r.kind not in ("master", "bedroom", "study", "bathroom"):
            continue
        side = "W" if r.x0 < EPS else "E" if r.x1 > c.W - EPS else None
        span = r.y1 - r.y0 - 1.0
        if side is None or span < 0.6:
            continue
        mid = (r.y0 + r.y1) / 2
        w = 0.6 if r.kind == "bathroom" else 0.78
        panes = [(mid - w / 2, mid + w / 2)]
        if r.kind != "bathroom" and span >= 2.0:    # a pair, side by side
            panes = [(mid - w - 0.07, mid - 0.07), (mid + 0.07, mid + w + 0.07)]
        for a, b in panes:
            u0, u1 = (a - y0, b - y0) if side == "W" else (y1 - b, y1 - a)
            holes[side].append((u0, u1, v0, v0 + (0.9 if r.kind == "bathroom" else 1.18)))
    return holes


def _gable_roof(c):
    """Two slabs leaning together at the ridge, with skylights over the rooms along the eaves."""
    W, D, te, m = c.W, c.D, c.te, c.mats
    p = math.radians(c.plan.villa["pitch"])
    tn, cs, sn = math.tan(p), math.cos(p), math.sin(p)
    t = ROOF_T
    x_e = -te / 2 - 0.3                                  # eave edge, west side
    z_e = c.F1 + c.plan.villa["knee"] + x_e * tn         # the underside is the plane that trims the walls
    y0, y1 = -te / 2 - 0.4, D + te / 2 + 0.4             # verges overhang the gables a little
    Lu, Lv = y1 - y0, (W / 2 - x_e) / cs + t * tn        # run past the ridge so the top edges meet
    holes = _skylights(c, x_e, tn, cs, y0, y1)

    for side in ("W", "E"):
        # Slope coordinates: v up the slope, u along the ridge, w out of the roof
        if side == "W":
            a, b, n, o = Vector((cs, 0, sn)), Vector((0, 1, 0)), Vector((-sn, 0, cs)), Vector((x_e, y0, z_e))
        else:
            a, b, n, o = Vector((-cs, 0, sn)), Vector((0, -1, 0)), Vector((sn, 0, cs)), Vector((W - x_e, y1, z_e))
        o = o + c.center
        M = Matrix(((a.x, b.x, n.x, o.x), (a.y, b.y, n.y, o.y), (a.z, b.z, n.z, o.z), (0, 0, 0, 1)))

        slab, glass, frames = [], [], []
        cur = 0.0
        for u0, u1, v0, v1 in sorted(h for h in holes[side] if h[3] < Lv - 0.5):
            if u0 < cur + 0.05:
                continue
            slab += [(0, cur, 0, Lv, u0, t), (0, u0, 0, v0, u1, t), (v1, u0, 0, Lv, u1, t)]
            cur = u1
            glass.append((v0, u0, t - 0.06, v1, u1, t - 0.05))
            f = 0.05
            frames += [(v0, u0, -0.01, v1, u0 + f, t + 0.03), (v0, u1 - f, -0.01, v1, u1, t + 0.03),
                       (v0, u0 + f, -0.01, v0 + f, u1 - f, t + 0.03), (v1 - f, u0 + f, -0.01, v1, u1 - f, t + 0.03)]
        slab.append((0, cur, 0, Lv, Lu, t))

        def obj(label, boxes, mat=None):
            if not boxes:
                return None
            me = _boxes_mesh(f"{c.name}_{label}_{side}", boxes, Vector())
            me.transform(M)
            me.update()
            if mat is None:     # tiles on top, white underneath and on the edges (the verge frame)
                i_roof, i_soffit = _mat_index(me, m["roof"]), _mat_index(me, m["soffit"])
                for poly in me.polygons:
                    poly.material_index = i_roof if poly.normal.dot(n) > 0.5 else i_soffit
            return _obj(f"{c.name}_{label}_{side}", me, c.coll, c.root, [mat] if mat else ())

        obj("Roof", slab)
        obj("SkylightGlass", glass, m["glass"])
        obj("SkylightFrames", frames, m["trim"])


def _carport_wing(c, width=5.6, depth=6.0, setback=0.9):
    """Gable villa: a flat-roofed carport on slim posts against the balcony side of the house."""
    W, te, G, H, m = c.W, c.te, c.G, c.H, c.mats
    west = c.upper.room("Balcony").x0 < EPS
    x0, x1 = (-te / 2 - width, -te / 2) if west else (W + te / 2, W + te / 2 + width)
    y0, y1 = setback, setback + depth
    c.add("CarportRoof", [(x0, y0, H - 0.02, x1, y1, H + 0.2)], paint=(m["roof_flat"], m["soffit"], m["trim"]))
    xo = x0 + 0.15 if west else x1 - 0.29               # posts along the outer edge
    c.add("CarportPosts", [(xo, y, G, xo + 0.14, y + 0.14, H - 0.02) for y in (y0 + 0.15, y1 - 0.29)], m["trim"])
    c.add("CarportFloor", [(x0, y0, G, x1, y1, G + 0.05)], m["paving"])
    c.drive = (x0, x1, y0)


# --------------------------------------------------------------------------
# Around the house
# --------------------------------------------------------------------------

def _site(c):
    W, D, te, G, m = c.W, c.D, c.te, c.G, c.mats
    if c.drive:
        x0, x1, y = c.drive
        c.add("Driveway", [(x0 + 0.1, -FRONT_YARD, G, x1 - 0.1, y, G + 0.04)], m["drive"])
    ent = next((o for o in c.ground.openings if o.kind == "ENTRANCE"), None)
    if ent:
        mid = (ent.s0 + ent.s1) / 2
        c.add("FrontPath", [(mid - 0.7, -FRONT_YARD, G, mid + 0.7, -te / 2 - 1.0, G + 0.04)], m["paving"])
    c.add("BackPatio", [(-te / 2, D + te / 2, G, W + te / 2, D + te / 2 + 3.0, G + 0.04)], m["paving"])


def _pool(c, width=4.0, length=8.0, rim=0.4):
    W, D, te, G, m = c.W, c.D, c.te, c.G, c.mats
    x0, y0 = W / 2 - width / 2, D + te / 2 + 4.0
    x1, y1 = x0 + width, y0 + length
    c.add("PoolEdge", [
        (x0 - rim, y0 - rim, G, x1 + rim, y0, G + 0.1), (x0 - rim, y1, G, x1 + rim, y1 + rim, G + 0.1),
        (x0 - rim, y0, G, x0, y1, G + 0.1), (x1, y0, G, x1 + rim, y1, G + 0.1),
    ], m["paving"])
    c.add("PoolWater", [(x0, y0, G, x1, y1, G + 0.06)], m["water"])
