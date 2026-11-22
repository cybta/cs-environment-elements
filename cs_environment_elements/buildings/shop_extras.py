"""Shopping row, the rest of the outside and the shop fittings (see shop.py for the facade).

- Roof: a flat slab behind a parapet with coping; a stepped cornice with dentils along
  the front, piers over the pilasters, and over the shared entrance a raised arched
  crown with rosettes and the year the row was "built", as on the first reference.
- Signs: each shop's name in gilt letters on its fascia (font outlines turned into mesh).
- Street: a sidewalk with a kerb, a step at each door, planters by the doors.
- Inside (optional): a shelving unit along one wall of each shop and a counter.

Works on shop._Ctx (`c`): c.box / c.part collect parts per object, shop.py builds them.
"""

import math

import bmesh
import bpy

from .cottage import _extrude
from .mesh_utils import _boxes_mesh, _obj, _paint_by_normal

SIGN_NAMES = (
    "BAKERY", "BOOKS", "CAFE", "FLOWERS", "TAILOR", "GROCER", "BARBER", "TOYS", "WINE", "HARDWARE",
    "PHARMACY", "TEA ROOM", "CHEESE", "BUTCHER", "JEWELLER", "GALLERY", "CARPENTER", "TOOLS", "DELI",
    "FABRICS", "ANTIQUES", "SWEETS", "MUSIC", "OPTICIAN", "HATS", "LAMPS", "PASTRY", "STATIONER",
)
PARAPET = 0.85
SIDEWALK = 2.6
WALK_Z = -0.15          # sidewalk top; the floor inside is at 0, a half step in between


def build(c):
    _roof(c)
    _cornice(c)
    _parapet(c)
    if c.g.sidewalk:
        _sidewalk(c)
    _planters(c)
    if c.g.fittings:
        _fittings(c)


# --------------------------------------------------------------------------
# Small geometry helpers -> (verts, faces)
# --------------------------------------------------------------------------

def blob(x, y, z, rx, ry, rz, rng=None):
    """A low-poly lumpy ball (foliage)."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    bm.verts.index_update()
    verts = []
    for v in bm.verts:
        j = 1.0 + (rng.uniform(-0.12, 0.12) if rng else 0.0)
        verts.append((x + v.co.x * rx * j, y + v.co.y * ry * j, z + v.co.z * rz * j))
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return verts, faces


def _ring_prism(rings, n=8, at=lambda r, a, h: (0, 0, 0)):
    """A closed prism through rings [(h, r)], each ring placed by at(r, angle, h)."""
    verts = [at(r, 2 * math.pi * (i + 0.5) / n, h) for h, r in rings for i in range(n)]
    faces = [list(range(n))[::-1], [len(rings) * n - n + i for i in range(n)]]
    for k in range(len(rings) - 1):
        b = k * n
        faces += [[b + i, b + (i + 1) % n, b + n + (i + 1) % n, b + n + i] for i in range(n)]
    return verts, faces


def pot(x, y, z0, h, r0, r1, n=8):
    return _ring_prism([(z0, r0), (z0 + h * 0.85, r1), (z0 + h * 0.85, r1 + 0.03), (z0 + h, r1 + 0.03)], n,
                       lambda r, a, z: (x + r * math.cos(a), y + r * math.sin(a), z))


def disc(x, z, r, y0, y1, n=8):
    """A short cylinder along y (a rosette)."""
    return _ring_prism([(y0, r), (y1, r)], n, lambda r, a, y: (x + r * math.cos(a), y, z + r * math.sin(a)))


def text_part(body, size, max_w):
    """Letters as mesh, in face terms: [(s, d, z)] centred on s = z = 0, standing out from
    d = 0 to 0.024, and the faces. None if the font gives nothing."""
    cu = bpy.data.curves.new("ShopText", "FONT")
    cu.body, cu.size, cu.extrude, cu.resolution_u = body, size, 0.012, 2
    cu.align_x, cu.align_y = "CENTER", "CENTER"
    ob = bpy.data.objects.new("ShopText", cu)
    try:
        me = bpy.data.meshes.new_from_object(ob)
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
    if not me.vertices:
        bpy.data.meshes.remove(me)
        return None
    xs, zs = [v.co.x for v in me.vertices], [v.co.y for v in me.vertices]
    cx, cz = (min(xs) + max(xs)) / 2, (min(zs) + max(zs)) / 2
    k = min(1.0, max_w / max(max(xs) - min(xs), 1e-4))
    verts = [((v.co.x - cx) * k, 0.012 + v.co.z, (v.co.y - cz) * k) for v in me.vertices]
    faces = [list(p.vertices) for p in me.polygons]
    bpy.data.meshes.remove(me)
    return verts, faces


def put_text(c, face, body, size, max_w, s, d, z, mat):
    """Letters on `face`, centred on (s, z), standing on the surface d out from the wall."""
    t = text_part(body, size, max_w)
    if t:
        verts, faces = t
        c.part("Signs", mat, ([face.pt(s + face.read * vs, d + vd, z + vz) for vs, vd, vz in verts], faces))


def sign_text(c, face, name, s, max_w, d, z0, z1, mat):
    """A shop's name on its fascia (between heights z0 and z1)."""
    put_text(c, face, name, (z1 - z0) * 0.55, max_w, s, d, (z0 + z1) / 2, mat)


def shop_names(c, n):
    names = list(SIGN_NAMES)
    c.rng.shuffle(names)
    return [names[i % len(names)] for i in range(n)]


# --------------------------------------------------------------------------
# Roof, cornice, parapet, crown
# --------------------------------------------------------------------------

def _roof(c):
    te, RB = c.te, c.RB
    box = (-te / 2, -te / 2, RB, c.W + te / 2, c.D + te / 2, RB + c.slab)
    me = _paint_by_normal(_boxes_mesh(f"{c.name}_Roof", [box], c.center), c.m["roof_flat"], c.m["ceiling"], c.m["wall_out"])
    _obj(f"{c.name}_Roof", me, c.coll, c.root)


def _cornice(c):
    """Three stepped courses with dentils, along the front and round any dressed side."""
    st, RB, top = c.m["stone"], c.RB, c.RB + c.slab
    for f in [c.front] + c.dressed:
        c.run(f, RB - 0.2, RB - 0.08, 0.09, st)
        c.run(f, RB - 0.08, RB + 0.06, 0.18, st)
        c.run(f, RB + 0.06, top, 0.32, st)
        s0, s1 = c.span(f, 0.0)
        n = int((s1 - s0 - 0.2) / 0.22)
        for i in range(n + 1):
            s = s0 + 0.1 + (s1 - s0 - 0.2) * i / max(n, 1)
            c.box("Mouldings", st, f.box(s - 0.04, s + 0.04, RB - 0.06, RB + 0.06, 0.26))


def _parapet(c):
    from .shop import PIL_G, bay_lines, pilaster_span

    te, W, D = c.te, c.W, c.D
    z0 = c.RB + c.slab
    z1 = z0 + PARAPET
    o = te / 2
    walls = [(-o, -o, z0, W + o, o, z1), (-o, D - o, z0, W + o, D + o, z1),
             (-o, o, z0, o, D - o, z1), (W - o, o, z0, W + o, D - o, z1)]
    c.box("Parapet", c.m["wall_out"], *walls)
    k = 0.05
    c.box("Parapet", c.m["cap"], (-o - k, -o - k, z1, W + o + k, o + k, z1 + 0.07),
          (-o - k, D - o - k, z1, W + o + k, D + o + k, z1 + 0.07),
          (-o - k, o + k, z1, o + k, D - o - k, z1 + 0.07), (W - o - k, o + k, z1, W + o + k, D - o - k, z1 + 0.07))

    entry = next(b for b in c.k["bays"] if b["kind"] == "entry")
    st = c.m["stone"]
    for x in bay_lines(c):                              # piers over the pilasters
        if abs(x - entry["x0"]) < 1e-4 or abs(x - entry["x1"]) < 1e-4:
            continue
        p0, p1 = pilaster_span(c, x, PIL_G - 0.06)
        if x < 1e-4:                                    # an end pier stands proud of the end wall too,
            p0 -= 0.06                                  # not flush with it (and clear of the coping)
        if x > c.W - 1e-4:
            p1 += 0.06
        c.box("Mouldings", st, (p0, c.yf - 0.06, z0, p1, c.yf + te + 0.04, z1 + 0.3),
              (p0 - 0.04, c.yf - 0.1, z1 + 0.3, p1 + 0.04, c.yf + te + 0.08, z1 + 0.38))

    # The crown over the entrance: a block, a half disc, an arch moulding, rosettes, a date
    xc = (entry["x0"] + entry["x1"]) / 2
    hw = min((entry["x1"] - entry["x0"]) / 2 + 0.25, xc + te / 2, c.W + te / 2 - xc)   # not past an end wall
    zc = z1 + 0.25
    yA, yB = c.yf - 0.08, c.yf + te + 0.04             # its back stands clear of the parapet's inner face
    c.box("Mouldings", st, (xc - hw, yA, z0, xc + hw, yB, zc), (xc - hw - 0.05, yA - 0.04, zc - 0.08, xc + hw + 0.05, yB + 0.04, zc))
    k = 12
    half = [(xc + hw * math.cos(math.pi * i / k), zc + hw * 0.62 * math.sin(math.pi * i / k)) for i in range(k + 1)]
    c.part("Mouldings", st, _extrude(half, yA, yB, "Y"))
    ro, ri = hw - 0.12, hw - 0.26
    outer = [(xc + ro * math.cos(math.pi * i / k), zc + ro * 0.62 * math.sin(math.pi * i / k)) for i in range(k + 1)]
    inner = [(xc + ri * math.cos(math.pi * i / k), zc + ri * 0.62 * math.sin(math.pi * i / k)) for i in range(k + 1)]
    caps = [[i, i + 1, 2 * k - i, 2 * k + 1 - i] for i in range(k)]
    c.part("Mouldings", st, _extrude(outer + inner[::-1], yA - 0.05, yA + 0.01, "Y", caps))
    for sx in (-1, 1):
        c.part("Mouldings", st, disc(xc + sx * (hw - 0.19), zc + 0.08, 0.1, yA - 0.07, yA + 0.01))
    if c.g.signs:
        put_text(c, c.front, str(c.rng.randint(1884, 1926)), 0.3, ri * 1.1, xc, 0.08, zc + ri * 0.28, c.m["gold"])


# --------------------------------------------------------------------------
# Street
# --------------------------------------------------------------------------

def _doors(c):
    return [o for o in c.plan.floors[0].openings if getattr(o, "role", "") in ("door", "entry")]


def _sidewalk(c):
    """Street sidewalk and kerb in front. It reaches past the side walls by the panel's
    sidewalk width, so the paving laid beside and behind the row (house._onto_ground)
    carries straight on round the corner."""
    te, yf = c.te, c.yf
    side = getattr(c.s, "sidewalk_width", 0.6)
    x0, x1 = -te / 2 - side, c.W + te / 2 + side
    y_k = yf - SIDEWALK
    c.box("Sidewalk", c.m["sidewalk"], (x0, y_k + 0.15, WALK_Z - 0.2, x1, yf, WALK_Z))
    c.box("Sidewalk", c.m["curb"], (x0, y_k, WALK_Z - 0.35, x1, y_k + 0.15, WALK_Z))
    for o in _doors(c):                                 # a half step up to each door
        c.box("Sidewalk", c.m["cap"], (o.s0 - 0.12, yf - 0.36, WALK_Z, o.s1 + 0.12, yf + 0.01, WALK_Z / 2))


def _planters(c):
    from .shop import zone

    if not c.g.planters:
        return
    gz = WALK_Z if c.g.sidewalk else -c.slab
    y = c.yf - 0.5

    def plant(x, big=False):
        h, r = (0.55, 0.26) if big else (0.42, 0.2)
        c.part("Props", c.m["pot"], pot(x, y, gz, h, r * 0.8, r))
        for i in range(3 if big else 2):
            a = c.rng.uniform(0, 2 * math.pi)
            d = c.rng.uniform(0.0, r * 0.4)
            rr = r * c.rng.uniform(1.0, 1.35)
            c.part("Props", c.m["leaves"], blob(x + d * math.cos(a), y + d * math.sin(a), gz + h + rr * 0.55,
                                               rr, rr, rr * 0.85, c.rng))

    doors = _doors(c)
    for b in c.k["bays"]:
        if b["kind"] == "entry":
            o = next(d for d in doors if d.role == "entry")
            for x in (o.s0 - 0.42, o.s1 + 0.42):
                plant(x, big=True)
            continue
        za, zb = zone(c, b)
        for x in (za + 0.3, zb - 0.3):
            if c.rng.random() < 0.45 and all(not (d.s0 - 0.5 < x < d.s1 + 0.5) for d in doors):
                plant(x)


# --------------------------------------------------------------------------
# Shop fittings
# --------------------------------------------------------------------------

def _fittings(c):
    H = c.H
    for b in c.k["bays"]:
        if b["kind"] != "shop":
            continue
        r = c.plan.floors[0].room(b["name"])
        paint = c.m["get"](c.looks[b["index"]][0])
        wood = c.m["shelf"]
        xl = r.x0 + (c.te if r.x0 < 1e-4 else c.ti) / 2
        xr = r.x1 - (c.te if r.x1 > c.W - 1e-4 else c.ti) / 2
        yb = r.y1 - (c.te if r.y1 > c.D - 1e-4 else c.ti) / 2
        left = c.rng.random() < 0.5
        if b["sides"]:                                  # keep the shelves off the glazed side wall
            left = b["sides"][0] > c.W - 1e-4
        y0, y1 = 0.9, yb - 1.0
        if y1 - y0 >= 1.0:
            sx = (xl, xl + 0.42) if left else (xr - 0.42, xr)
            h = min(2.2, H - 0.4)
            parts = [(sx[0], y0, 0.0, sx[1], y1, 0.08)]                                   # plinth
            back = (sx[0], y0, 0.0, sx[0] + 0.02, y1, h) if left else (sx[1] - 0.02, y0, 0.0, sx[1], y1, h)
            parts.append(back)
            n = max(1, math.ceil((y1 - y0) / 1.0))
            for i in range(n + 1):
                yy = y0 + (y1 - y0) * i / n
                parts.append((sx[0], max(y0, yy - 0.015), 0.0, sx[1], min(y1, yy + 0.015), h))
            c.box("Fittings", paint, *parts)
            shelves = [(sx[0], y0, z, sx[1], y1, z + 0.025) for z in (0.08, 0.5, 0.92, 1.34, 1.76)]
            shelves.append((sx[0], y0, h, sx[1], y1, h + 0.03))
            c.box("Fittings", wood, *shelves)
        if xr - xl >= 3.6:                              # the counter, staff side towards the wall
            cx = (xr - 1.6, xr - 1.0) if left else (xl + 1.0, xl + 1.6)
            ca = r.y0 + (yb - r.y0) * 0.45
            cb = min(ca + 1.8, yb - 0.8)
            if cb - ca >= 0.9:
                c.box("Fittings", paint, (cx[0], ca, 0.0, cx[1], cb, 0.9))
                c.box("Fittings", wood, (cx[0] - 0.03, ca - 0.03, 0.9, cx[1] + 0.03, cb + 0.03, 0.95))
