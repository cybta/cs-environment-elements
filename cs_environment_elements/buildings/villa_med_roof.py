"""The Mediterranean villa's roofs: every block of the courtyard house under its own clay-tile
roof at its own height (plan.villa["units"], see villa_med_layout).

Per block:
- its ceiling slab, at the block's own height,
- a band of wall from the ground floor's ceiling up to that height where the block stands
  taller than the ground floor (the corner rooms, the great room) - with clerestory windows
  over the loggia's roof on the great room,
- the roof itself: an open gable or a hip, with deep eaves on timber rafter tails. Where the
  block backs onto a taller one, the overhang on that side is cut off at the taller block's
  wall, so no roof pokes through into a room.

Then the loggia's lean-to roof between the arcade and the great room, and the chimneys.

Plan coordinates as in villa.py (front at y = 0, ground floor at z = 0); meshes are offset by
c.center like everything else.
"""

import math

from mathutils import Vector

from .house_roof import _roof_geometry
from . import roof_edge
from .mesh_utils import _clip_mesh, _mat_index, _obj, _sheared_box, _solid

EPS = 1e-4
OVERHANG = 0.65          # not the front recess (0.7): the main hip's eave would lie in the entry bay's face
ROOF_T = 0.2
RAFTER_W, RAFTER_D, RAFTER_STEP = 0.09, 0.16, 0.6     # width, depth under the soffit, spacing
CHIMNEY = (1.0, 0.7)                                   # along / across the ridge
SIDES = ("x0", "x1", "y0", "y1")


# --------------------------------------------------------------------------
# Who stands next to whom
# --------------------------------------------------------------------------

def _line(rect, side):
    """(axis of the wall, its coordinate, span start, span end) of one side of a rect."""
    x0, y0, x1, y1 = rect
    return {"x0": ("Y", x0, y0, y1), "x1": ("Y", x1, y0, y1),
            "y0": ("X", y0, x0, x1), "y1": ("X", y1, x0, x1)}[side]


def _opposite(side):
    return {"x0": "x1", "x1": "x0", "y0": "y1", "y1": "y0"}[side]


def _taller_across(u, units, side):
    """Taller blocks sharing this side's wall from the other side -> [(s0, s1)]."""
    axis, k, a, b = _line(u["rect"], side)
    out = []
    for v in units:
        if v is u or v["top"] <= u["top"] + EPS:
            continue
        va, vk, p, q = _line(v["rect"], _opposite(side))
        if va == axis and abs(vk - k) < EPS and min(b, q) - max(a, p) > EPS:
            out.append((max(a, p), min(b, q)))
    return out


def _subtract(ivs, cut):
    out = []
    for a, b in ivs:
        if cut[1] <= a + EPS or cut[0] >= b - EPS:
            out.append((a, b))
            continue
        if cut[0] > a + EPS:
            out.append((a, cut[0]))
        if cut[1] < b - EPS:
            out.append((cut[1], b))
    return out


# --------------------------------------------------------------------------
# Ceiling slabs and the wall bands of the raised blocks
# --------------------------------------------------------------------------

def _slab(c, u, units):
    te, m = c.te, c.mats
    if "slab" in u:
        x0, y0, x1, y1 = u["slab"]
    else:
        # Out over the wall top on every side, except into a taller block (its band is there)
        ext = {s: 0.0 if _taller_across(u, units, s) else te / 2 for s in SIDES}
        rx0, ry0, rx1, ry1 = u["rect"]
        x0, y0, x1, y1 = rx0 - ext["x0"], ry0 - ext["y0"], rx1 + ext["x1"], ry1 + ext["y1"]
    top = u["top"]
    c.add(f"{u['name']}_Ceiling", [(x0, y0, top, x1, y1, top + c.plan.slab)],
          paint=(m["roof_flat"], m["ceiling"], m["wall_out"]))


def _band_boxes(axis, k, t, a, b, z0, z1, holes):
    """Wall boxes along a line from a to b, z0 to z1, round (s0, s1, h0, h1) holes."""
    out, cur = [], a

    def box(s0, s1, h0, h1):
        return (s0, k - t / 2, h0, s1, k + t / 2, h1) if axis == "X" else (k - t / 2, s0, h0, k + t / 2, s1, h1)

    for s0, s1, h0, h1 in sorted(holes):
        if s0 < a or s1 > b:
            continue
        if s0 > cur + EPS:
            out.append(box(cur, s0, z0, z1))
        out += [box(s0, s1, z0, h0), box(s0, s1, h1, z1)]
        cur = s1
    if b > cur + EPS:
        out.append(box(cur, b, z0, z1))
    return out


def _bands(c, u, units, clerestory):
    """The walls of a raised block from the ground floor's ceiling up to its own."""
    H, te, m = c.H, c.te, c.mats
    z0, z1 = H + 0.003, u["top"] + 0.003
    if z1 - z0 < 0.05 or u["top"] >= c.F1 + c.H - EPS:    # not raised / the upper storey's own walls
        return
    rx0, ry0, rx1, ry1 = u["rect"]
    taller = [v for v in units if v["top"] > u["top"] + EPS]
    boxes = []
    for side in SIDES:
        axis, k, a, b = _line(u["rect"], side)
        ivs = [(a - te / 2, b + te / 2)] if axis == "X" else [(a + te / 2, b - te / 2)]
        for v in taller:                                    # a taller block's own walls are there
            vx0, vy0, vx1, vy1 = v["rect"]
            if axis == "X" and vy0 - te / 2 - EPS <= k <= vy1 + te / 2 + EPS:
                ivs = _subtract(ivs, (vx0 - te / 2, vx1 + te / 2))
            if axis == "Y" and vx0 - te / 2 - EPS <= k <= vx1 + te / 2 + EPS:
                ivs = _subtract(ivs, (vy0 - te / 2, vy1 + te / 2))
        holes = clerestory if side == "y0" else []
        for p, q in ivs:
            if q - p > 0.01:
                boxes += _band_boxes(axis, k, te, p, q, z0, z1, holes)
    ob = c.add(f"{u['name']}_UpperWalls", boxes, m["wall_out"])
    if ob is None:
        return
    me = ob.data                                            # plaster on the faces looking into the block
    i_in = _mat_index(me, m["wall_in"])
    for p in me.polygons:
        q = p.center - c.center + p.normal * 0.05
        if abs(p.normal.z) < 0.5 and rx0 < q.x < rx1 and ry0 < q.y < ry1:
            p.material_index = i_in


def _clerestory(c, u, shed_top):
    """Windows in the great room's wall over the loggia roof -> [(s0, s1, z0, z1)] holes, built."""
    span = u.get("clerestory")
    if not span:
        return []
    z0, z1 = shed_top + 0.2, u["top"] - 0.25
    if z1 - z0 < 0.4:
        return []
    a, b = span
    n = max(2, round((b - a) / 2.2))
    holes = []
    for i in range(n):
        mid = a + (b - a) * (i + 0.5) / n
        holes.append((mid - 0.55, mid + 0.55, z0, z1))
    k, te, m = u["rect"][1], c.te, c.mats
    glass, frames, sills = [], [], []
    fw, d = 0.05, 0.08
    for s0, s1, h0, h1 in holes:
        glass.append((s0, k - 0.003, h0, s1, k + 0.003, h1))
        frames += [(s0, k - d / 2, h0, s0 + fw, k + d / 2, h1), (s1 - fw, k - d / 2, h0, s1, k + d / 2, h1),
                   (s0, k - d / 2, h0, s1, k + d / 2, h0 + fw), (s0, k - d / 2, h1 - fw, s1, k + d / 2, h1),
                   ((s0 + s1) / 2 - fw / 2, k - d / 2, h0, (s0 + s1) / 2 + fw / 2, k + d / 2, h1)]
        # a limestone sill under each, on the loggia side
        sills.append((s0 - 0.06, k - te / 2 - 0.06, h0 - 0.07, s1 + 0.06, k - te / 2 + 0.05, h0 + 0.012))
    c.add("Clerestory_Sills", sills, m.get("limestone", m["trim"]))
    c.add("Clerestory_Glass", glass, m["glass"])
    c.add("Clerestory_Frames", frames, m["trim"])
    return holes


# --------------------------------------------------------------------------
# Roofs
# --------------------------------------------------------------------------

def _roof(c, u, units, pitch):
    te, m = c.te, c.mats
    rx0, ry0, rx1, ry1 = u.get("roof_rect", u["rect"])
    along_x = u["ridge"] == "X"
    ox, oy = (rx1 - rx0) / 2 + te / 2, (ry1 - ry0) / 2 + te / 2
    hx, hy = (ox, oy) if along_x else (oy, ox)
    z0 = u["top"] + c.plan.slab
    roof, walls = _roof_geometry(u["kind"], hx, hy, z0, pitch, OVERHANG, ROOF_T, te)
    cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
    off = c.center + Vector((cx, cy, 0.0))

    def place(vf):
        v, f = vf
        if not along_x:
            v = [(y, x, z) for x, y, z in v]
        return [Vector(p) + off for p in v], f

    # Cut the overhang off where the block backs onto a taller one: 1 cm into its wall
    planes = []
    x0, y0, x1, y1 = u["rect"]
    for side, co, no in (("x0", (x0 + te / 2 - 0.01, 0, 0), (-1, 0, 0)), ("x1", (x1 - te / 2 + 0.01, 0, 0), (1, 0, 0)),
                         ("y0", (0, y0 + te / 2 - 0.01, 0), (0, -1, 0)), ("y1", (0, y1 - te / 2 + 0.01, 0), (0, 1, 0))):
        if _taller_across(u, units, side):
            planes.append((Vector(co) + c.center, Vector(no)))
    u["_cut"] = {p for p in SIDES if _taller_across(u, units, p)}

    name = f"{c.name}_{u['name']}_Roof"
    me = _solid(name, *place(roof))
    if planes:
        _clip_mesh(me, planes)
    roof_edge.paint(me, m)
    _obj(name, me, c.coll, c.root)
    roof_edge.edge_uvs(me, m)
    if walls:
        gw = _solid(f"{name}Gables", *place(walls))
        if planes:
            _clip_mesh(gw, planes)
        _obj(f"{name}Gables", gw, c.coll, c.root, [m["wall_out"]])
    _rafters(c, u, z0, math.tan(math.radians(pitch)))
    return z0 + hy * math.tan(math.radians(pitch)) + ROOF_T / math.cos(math.radians(pitch))


def _rafters(c, u, z0, tn):
    """Timber rafter tails under the eaves (not on a cut side, and clear of hip corners)."""
    te = c.te
    x0, y0, x1, y1 = u.get("roof_rect", u["rect"])
    reach = OVERHANG - 0.06
    ridge_x = u["ridge"] == "X"
    hip = u["kind"] == "HIP"
    parts = []
    sides = (   # (side, along x?, wall face, outward direction, span start, span end)
        ("y0", True, y0 - te / 2, -1.0, x0 - te / 2, x1 + te / 2), ("y1", True, y1 + te / 2, 1.0, x0 - te / 2, x1 + te / 2),
        ("x0", False, x0 - te / 2, -1.0, y0 - te / 2, y1 + te / 2), ("x1", False, x1 + te / 2, 1.0, y0 - te / 2, y1 + te / 2),
    )
    for side, along_x, face, out, a, b in sides:
        if side in u.get("_cut", ()) or (not hip and along_x != ridge_x):
            continue                                       # a cut side, or a gable end
        if u["name"] == "EntryBay" and side == "y1":
            continue
        pad = OVERHANG + 0.15 if hip else 0.1
        a, b = a + pad, b - pad
        if b <= a:
            continue
        n = max(1, round((b - a) / RAFTER_STEP))
        for i in range(n + 1):
            s = a + (b - a) * i / n
            p0 = Vector((s, face, z0) if along_x else (face, s, z0))
            p1 = p0 + Vector((0, out * reach, -reach * tn) if along_x else (out * reach, 0, -reach * tn))
            parts.append(_sheared_box(p0 + c.center, p1 + c.center, RAFTER_W / 2, -RAFTER_D, 0.01))
    if parts:
        name = f"{c.name}_{u['name']}_RafterTails"
        _obj(name, _merge(name, parts), c.coll, c.root, [c.mats["rafter"]])


def _loggia_roof(c, pitch):
    """A lean-to from the arcade up to the great room's wall, with the ceiling slab under it and
    a triangle of wall closing each end. Returns the height of its top at the great room wall."""
    xa, ya, xb, yb = c.plan.villa["loggia"]
    xc0, _, xc1, _ = c.plan.villa["court"]
    te, H, S, m = c.te, c.H, c.plan.slab, c.mats
    tn = math.tan(math.radians(pitch))
    dt = ROOF_T / math.cos(math.radians(pitch))
    c.add("Loggia_Ceiling", [(xc0 + te / 2, ya - te / 2, H, xc1 - te / 2, yb - te / 2 + 0.01, H + S)],
          paint=(m["roof_flat"], m["ceiling"], m["wall_out"]))
    y_face, y_wall = ya - te / 2, yb - te / 2 + 0.01
    ye = y_face - OVERHANG

    def zu(y):                                             # underside of the roof
        return H + S + (y - y_face) * tn

    x0, x1 = xc0 - te / 2, xc1 + te / 2
    base = [(x0, ye, zu(ye)), (x1, ye, zu(ye)), (x1, y_wall, zu(y_wall)), (x0, y_wall, zu(y_wall))]
    verts = [Vector(p) + c.center for p in base] + [Vector((x, y, z + dt)) + c.center for x, y, z in base]
    faces = [[3, 2, 1, 0], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    me = _solid(f"{c.name}_Loggia_Roof", verts, faces)
    roof_edge.paint(me, m)
    _obj(f"{c.name}_Loggia_Roof", me, c.coll, c.root)
    roof_edge.edge_uvs(me, m)

    ends = []
    for xe in (xc0, xc1):                                  # the triangles under the roof's ends
        tri = [(xe - te / 2, y_face, H + S), (xe - te / 2, y_wall, H + S), (xe - te / 2, y_wall, zu(y_wall)),
               (xe + te / 2, y_face, H + S), (xe + te / 2, y_wall, H + S), (xe + te / 2, y_wall, zu(y_wall))]
        ends.append(([Vector(p) + c.center for p in tri], [[0, 1, 2], [5, 4, 3], [0, 3, 4, 1], [1, 4, 5, 2], [2, 5, 3, 0]]))
    _obj(f"{c.name}_Loggia_Ends", _merge(f"{c.name}_Loggia_Ends", ends), c.coll, c.root, [m["wall_out"]])

    reach = OVERHANG - 0.06
    parts = []
    n = max(1, round((x1 - x0 - 0.6) / RAFTER_STEP))
    for i in range(n + 1):
        s = x0 + 0.3 + (x1 - x0 - 0.6) * i / n
        p0 = Vector((s, y_face, H + S))
        p1 = p0 + Vector((0, -reach, -reach * tn))
        parts.append(_sheared_box(p0 + c.center, p1 + c.center, RAFTER_W / 2, -RAFTER_D, 0.01))
    _obj(f"{c.name}_Loggia_RafterTails", _merge(f"{c.name}_Loggia_RafterTails", parts), c.coll, c.root,
         [m["rafter"]])
    return zu(y_wall - 0.01) + dt


# --------------------------------------------------------------------------
# Chimneys
# --------------------------------------------------------------------------

def _chimney(c, u, ridge_top):
    m = c.mats
    lime = m.get("limestone", m["trim"])
    x0, y0, x1, y1 = u["rect"]
    a, b = CHIMNEY
    if u["ridge"] == "X":
        half = (x1 - x0) / 2 - (y1 - y0) / 2
        cx, cy = (x0 + x1) / 2 + 0.55 * max(half, 0.0), (y0 + y1) / 2
        hx_, hy_ = a / 2, b / 2
    else:
        half = (y1 - y0) / 2 - (x1 - x0) / 2
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.45 * max(half, 0.0)
        hx_, hy_ = b / 2, a / 2
    z0 = u["top"] + c.plan.slab
    zc = ridge_top + 0.75

    def ring(e, lo, hi):
        return (cx - hx_ - e, cy - hy_ - e, lo, cx + hx_ + e, cy + hy_ + e, hi)

    label = f"{u['name']}_Chimney"
    c.add(label, [ring(0.0, z0, zc)], m["wall_out"])
    k = 0.16                                     # corner posts of the open cap
    posts = [(px, py, zc + 0.06, px + k, py + k, zc + 0.42)
             for px in (cx - hx_, cx + hx_ - k) for py in (cy - hy_, cy + hy_ - k)]
    c.add(f"{label}Posts", posts, m["wall_out"])
    # The dark flue seen through the openings; big enough to outlive the posts in the LODs, so
    # the cap never floats
    c.add(f"{label}Flue", [ring(-0.1, zc + 0.06, zc + 0.42)], m["trim"])
    c.add(f"{label}Cap", [ring(0.05, zc, zc + 0.06), ring(0.07, zc + 0.42, zc + 0.48)], lime)
    e, apex = 0.1, zc + 0.74
    base = [(cx - hx_ - e, cy - hy_ - e), (cx + hx_ + e, cy - hy_ - e), (cx + hx_ + e, cy + hy_ + e),
            (cx - hx_ - e, cy + hy_ + e)]
    verts = [Vector((x, y, zc + 0.48)) + c.center for x, y in base] + [Vector((cx, cy, apex)) + c.center]
    me = _solid(f"{c.name}_{label}Roof", verts, [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [3, 2, 1, 0]])
    _obj(f"{c.name}_{label}Roof", me, c.coll, c.root, [m["roof"]])


# --------------------------------------------------------------------------

def build_roofs(c, pitch):
    units = c.plan.villa["units"]
    shed_top = _loggia_roof(c, pitch)
    for u in units:
        _slab(c, u, units)
        _bands(c, u, units, _clerestory(c, u, shed_top))
        ridge_top = _roof(c, u, units, pitch)
        if u.get("chimney"):
            _chimney(c, u, ridge_top)


def _merge(name, parts):
    verts, faces = [], []
    for v, f in parts:
        base = len(verts)
        verts += v
        faces += [[base + i for i in face] for face in f]
    return _solid(name, verts, faces)
