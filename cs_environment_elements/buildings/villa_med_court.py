"""The Mediterranean villa's courtyard (villa_med hands over here):

- an arcade of round arches on stucco piers along the galleries and the loggia, with
  limestone bases and imposts - the wing roofs and the loggia's lean-to rest on it,
- limestone bands laid into the courtyard's paving: a border and a cross,
- a tiered stone fountain in the middle,
- terracotta pots with clipped shrubs round the fountain and along the arcade.

Plan coordinates as in villa.py: front at y = 0, ground floor at z = 0, ground one slab down.
"""

import math

from mathutils import Vector

from . import villa_arch as va
from .mesh_utils import _obj, _solid
from .villa_arch import Wall

PIER = 0.55             # narrowest pier between two arches
BAY = 2.3               # arcade bays aim for this
BAND = 0.45             # wall left over the crowns of the arches


def build(c):
    _arcade(c)
    _paving(c)
    _fountain(c)
    _pots(c)


def _lime(c):
    return c.mats.get("limestone", c.mats["trim"])


# --------------------------------------------------------------------------
# The arcade
# --------------------------------------------------------------------------

def _runs(c):
    """(label, wall, start s, end s) for the three arcade runs: the galleries end on the front
    block's wall and on the loggia's run, which takes the two corners."""
    x0, y0, x1, y1 = c.plan.villa["court"]
    te = c.te
    return [
        ("West", Wall("Y", x0, 1.0), y0 + te / 2, y1 - te / 2),
        ("Back", Wall("X", y1, -1.0), x0 - te / 2, x1 + te / 2),
        ("East", Wall("Y", x1, -1.0), y0 + te / 2, y1 - te / 2),
    ]


def _arcade(c):
    te, G, H = c.te, c.G, c.H
    runs = _runs(c)
    # One arch size for all: as wide as the tightest bay allows, crowns level under the band
    bays = [(b - a) / max(1, round((b - a) / BAY)) for _, _, a, b in runs]
    span = min(max(min(bays) - PIER, 1.0), 2.0)
    r = span / 2
    zs = H - BAND - r
    top = H + 0.003
    for label, wall, a, b in runs:
        n = max(1, round((b - a) / BAY))
        bay = (b - a) / n
        holes = [(a + bay * (k + 0.5) - r, a + bay * (k + 0.5) + r) for k in range(n)]
        cuts = [a] + [v for h in holes for v in h] + [b]
        piers = [(p0, p1) for p0, p1 in zip(cuts[0::2], cuts[1::2]) if p1 - p0 > 0.01]
        parts = [va.box(p0, p1, -te / 2, te / 2, G, top) for p0, p1 in piers]
        for s0, s1 in holes:
            parts += [va.prism(p, -te / 2, te / 2) for p in va.spandrels(s0, s1, zs, top)]
        va.add(c, f"Arcade_{label}", wall, parts, c.mats["wall_out"])

        # Limestone bases and imposts round the piers, not past the run's ends
        deco = []
        for p0, p1 in piers:
            for e, z0, z1 in ((0.03, G, G + 0.42), (0.04, zs - 0.14, zs)):
                q0 = p0 if abs(p0 - a) < 0.02 else p0 - e
                q1 = p1 if abs(p1 - b) < 0.02 else p1 + e
                deco.append(va.box(q0, q1, -te / 2 - e, te / 2 + e, z0, z1))
        for s0, s1 in holes:                              # a slim limestone archivolt
            deco.append(va.band((s0 + s1) / 2, zs, r, r + 0.12, te / 2, te / 2 + 0.03))
        va.add(c, f"ArcadeStone_{label}", wall, deco, _lime(c))


# --------------------------------------------------------------------------
# Paving, fountain, pots
# --------------------------------------------------------------------------

def _paving(c):
    """Limestone bands in the courtyard floor: a border inside the arcade and a cross."""
    x0, y0, x1, y1 = c.plan.villa["court"]
    te = c.te
    a0, b0, a1, b1 = x0 + te / 2 + 0.3, y0 + te / 2 + 0.3, x1 - te / 2 - 0.3, y1 - te / 2 - 0.3
    w, z0, z1 = 0.3, -0.03, -0.012
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    boxes = [(a0, b0, z0, a1, b0 + w, z1), (a0, b1 - w, z0, a1, b1, z1),
             (a0, b0 + w, z0, a0 + w, b1 - w, z1), (a1 - w, b0 + w, z0, a1, b1 - w, z1),
             (cx - w / 2, b0 + w, z0, cx + w / 2, cy - 1.9, z1), (cx - w / 2, cy + 1.9, z0, cx + w / 2, b1 - w, z1),
             (a0 + w, cy - w / 2, z0, cx - 1.9, cy + w / 2, z1), (cx + 1.9, cy - w / 2, z0, a1 - w, cy + w / 2, z1)]
    c.add("CourtyardBands", boxes, _lime(c))


def _ring(cx, cy, r0, r1, z0, z1, n=28):
    """A round solid: a disc (r0 = 0) or a ring between two radii -> (verts, faces)."""
    pts = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    if r0 <= 0:
        verts = [(cx + r1 * a, cy + r1 * b, z) for z in (z0, z1) for a, b in pts]
        faces = [list(reversed(range(n))), [n + i for i in range(n)]]
        faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
        return verts, faces
    verts = [(cx + r * a, cy + r * b, z) for z in (z0, z1) for r in (r0, r1) for a, b in pts]
    io, oo, it, ot = 0, n, 2 * n, 3 * n                    # inner / outer, bottom / top
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces += [[oo + i, oo + j, ot + j, ot + i], [io + j, io + i, it + i, it + j],
                  [ot + i, ot + j, it + j, it + i], [io + i, io + j, oo + j, oo + i]]
    return verts, faces


def _cone(cx, cy, r0, r1, z0, z1, n=20):
    """A frustum from radius r0 at z0 to r1 at z1 -> (verts, faces)."""
    pts = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
    verts = [(cx + r0 * a, cy + r0 * b, z0) for a, b in pts] + [(cx + r1 * a, cy + r1 * b, z1) for a, b in pts]
    faces = [list(reversed(range(n))), [n + i for i in range(n)]]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return verts, faces


def _solids(c, label, parts, mat):
    if not parts:
        return
    verts, faces = [], []
    for v, f in parts:
        base = len(verts)
        verts += [Vector(p) + c.center for p in v]
        faces += [[base + i for i in face] for face in f]
    name = f"{c.name}_{label}"
    _obj(name, _solid(name, verts, faces), c.coll, c.root, [mat])


def _fountain(c):
    x0, y0, x1, y1 = c.plan.villa["court"]
    cx, cy, z = (x0 + x1) / 2, (y0 + y1) / 2, -0.03
    m = c.mats
    stone = [_ring(cx, cy, 1.12, 1.35, z, z + 0.5),                  # the basin's rim
             _ring(cx, cy, 1.3, 1.5, z, z + 0.08),                   # a step round it
             _ring(cx, cy, 0.0, 1.13, z, z + 0.1),                   # its floor
             _cone(cx, cy, 0.3, 0.16, z + 0.1, z + 0.95),            # the shaft
             _cone(cx, cy, 0.14, 0.62, z + 0.92, z + 1.12),          # the bowl
             _ring(cx, cy, 0.55, 0.64, z + 1.12, z + 1.2),
             _cone(cx, cy, 0.1, 0.07, z + 1.15, z + 1.55),           # the top tier
             _cone(cx, cy, 0.06, 0.3, z + 1.5, z + 1.62),
             _cone(cx, cy, 0.05, 0.0, z + 1.62, z + 1.8)]
    _solids(c, "Fountain", stone, _lime(c))
    water = [_ring(cx, cy, 0.0, 1.13, z + 0.1, z + 0.4), _ring(cx, cy, 0.0, 0.56, z + 1.12, z + 1.17)]
    _solids(c, "FountainWater", water, m["water"])


def _pots(c):
    """Terracotta pots with a clipped shrub: four round the fountain, one by each arcade pier."""
    x0, y0, x1, y1 = c.plan.villa["court"]
    cx, cy, te = (x0 + x1) / 2, (y0 + y1) / 2, c.te
    spots = [(cx + dx, cy + dy, 0.28) for dx in (-2.2, 2.2) for dy in (-2.2, 2.2)]
    for _, wall, a, b in _runs(c):
        n = max(1, round((b - a) / BAY))
        bay = (b - a) / n
        for k in range(1, n):
            p = wall.point(a + bay * k, te / 2 + 0.45, 0.0)
            spots.append((p[0], p[1], 0.22))
    pots, shrubs = [], []
    z = -0.02
    for x, y, r in spots:
        pots += [_cone(x, y, r * 0.7, r, z, z + r * 1.6), _ring(x, y, r * 0.92, r * 1.08, z + r * 1.5, z + r * 1.7)]
        shrubs += [_cone(x, y, r * 0.8, r * 1.25, z + r * 1.6, z + r * 2.6), _cone(x, y, r * 1.25, r * 0.4, z + r * 2.6, z + r * 3.4)]
    _solids(c, "Pots", pots, c.mats["roof"])
    _solids(c, "PotShrubs", shrubs, c.mats.get("planter_top", c.mats["accent"]))
