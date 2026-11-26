"""The Mediterranean villa's exterior (villa.build_exterior hands over here): the courtyard
house of villa_med_layout.

- every block under its own clay-tile roof at its own height (villa_med_roof),
- the courtyard: arcade, fountain, pots (villa_med_court),
- the arched front door in a limestone surround, and over it an arched French door with
  a fanlight, opening onto a little balcony on corbels,
- limestone sills and dark timber shutters at the windows,
- the front path, stone planters by it, the back patio and the pool.

Plan coordinates as in villa.py: front at y = 0, ground floor at z = 0, ground one slab down.
Shapes on a wall are drawn in its own frame (villa_arch.Wall: s along it, w out of it).
"""

import math

from . import villa_arch as va
from . import villa_med_court
from .villa_arch import Wall
from .villa_med_layout import PITCH
from .villa_med_roof import build_roofs

EPS = 1e-4
RAIL_H = 1.0
BAR, BAR_STEP = 0.018, 0.11
PLANTER_GAP = 0.85       # the planters stand this far either side of the front path's centre; the path fills it


def build(c):
    from .villa import _frames, _pool, _site
    _frames(c)
    _sills(c)
    _shutters(c)
    _entrance(c)
    _french_door(c)
    _arched_windows(c)
    build_roofs(c, c.plan.villa.get("pitch", PITCH))
    villa_med_court.build(c)
    if c.s.villa_site:
        _site(c, path_half=PLANTER_GAP)
        _planters(c)
    if c.s.villa_pool:
        _pool(c, along=True)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _lime(c):
    return c.mats.get("limestone", c.mats["trim"])


def _wall_of(f, o):
    """The wall an opening is in, facing away from its room."""
    r = f.room(o.rooms[0])
    across = r.center[1] if o.axis == "X" else r.center[0]
    return Wall(o.axis, o.coord, -1.0 if across > o.coord else 1.0, f.base_z)


def _facade(c, f, x, y):
    """The facade material at (x, y) on this floor: a stone zone's, or the render."""
    for x0, y0, x1, y1, role in f.accents:
        if x0 <= x <= x1 and y0 <= y <= y1 and role in c.mats:
            return c.mats[role]
    return c.mats["wall_out"]


def _rail(out, a, b, z0, h=RAIL_H):
    """A black iron railing from plan point a to b (axis-aligned) standing on z0: a bottom rail,
    square bars, a band under the handrail and the handrail -> boxes into `out`."""
    along_x = abs(b[0] - a[0]) >= abs(b[1] - a[1])
    s0, s1 = sorted((a[0], b[0])) if along_x else sorted((a[1], b[1]))
    k = a[1] if along_x else a[0]

    def bar(u0, u1, half, lo, hi):
        return (u0, k - half, lo, u1, k + half, hi) if along_x else (k - half, u0, lo, k + half, u1, hi)

    out += [bar(s0, s1, 0.016, z0 + 0.05, z0 + 0.09), bar(s0, s1, 0.012, z0 + h - 0.23, z0 + h - 0.2),
            bar(s0, s1, 0.03, z0 + h - 0.045, z0 + h)]
    n = max(1, round((s1 - s0) / BAR_STEP))
    for i in range(n + 1):
        u = min(max(s0 + (s1 - s0) * i / n, s0 + BAR / 2), s1 - BAR / 2)
        out.append(bar(u - BAR / 2, u + BAR / 2, BAR / 2, z0 + 0.05, z0 + h - 0.045))


def _surround(s0, s1, zs, t, width, proud, key=True, z0=0.0):
    """A limestone surround on the wall face round an arched opening: the archivolt, a strip
    down each jamb (from z0) and a keystone at the crown."""
    r, sm = (s1 - s0) / 2, (s0 + s1) / 2
    f0, f1 = t / 2, t / 2 + proud
    parts = [va.band(sm, zs, r, r + width, f0, f1), va.box(s0 - width, s0, f0, f1, z0, zs),
             va.box(s1, s1 + width, f0, f1, z0, zs)]
    if key:
        k = width * 0.6
        parts.append(va.box(sm - k, sm + k, f0, f1 + 0.03, zs + r - 0.05, zs + r + width + 0.05))
    return parts


# --------------------------------------------------------------------------
# Sills and shutters
# --------------------------------------------------------------------------

def _sills(c):
    boxes = []
    for f in c.plan.floors:
        for o in f.openings:
            if not o.exterior or o.kind != "WINDOW" or getattr(o, "round", False) or o.z0 < 0.2:
                continue
            t = o.thickness or c.te
            boxes.append(_wall_of(f, o).box(o.s0 - 0.06, o.s1 + 0.06, t / 2 - 0.06, t / 2 + 0.05,
                                            o.z0 - 0.07, o.z0 + 0.012))
    c.add("Sills", boxes, _lime(c))


def _shutters(c):
    """A pair of dark timber shutters folded back beside each ordinary window, each leaf framed
    with three rails across, where the wall beside the window has room for them."""
    boxes = []
    for f in c.plan.floors:
        spans = {}                                          # what else is on each wall line
        for o in f.openings:
            spans.setdefault((o.axis, round(o.coord, 3)), []).append((o.s0, o.s1))
        for o in f.openings:
            if not o.exterior or o.kind != "WINDOW" or getattr(o, "round", False) or o.z0 < 0.2:
                continue
            w = (o.s1 - o.s0) / 2
            if w > 0.8:
                continue
            r = f.room(o.rooms[0])
            lo, hi = (r.x0, r.x1) if o.axis == "X" else (r.y0, r.y1)
            a, b = o.s0 - 0.03 - w, o.s1 + 0.03 + w
            others = [s for s in spans[(o.axis, round(o.coord, 3))] if s != (o.s0, o.s1)]
            if a < lo + c.te / 2 + 0.05 or b > hi - c.te / 2 - 0.05 or any(s0 < b + 0.1 and a - 0.1 < s1 for s0, s1 in others):
                continue
            t = o.thickness or c.te
            wall = _wall_of(f, o)
            w0, w1 = t / 2 + 0.005, t / 2 + 0.045
            for s0, s1 in ((a, o.s0 - 0.03), (o.s1 + 0.03, b)):
                boxes.append(wall.box(s0, s1, w0, w1, o.z0, o.z1))
                for zz in (o.z0 + 0.06, (o.z0 + o.z1) / 2, o.z1 - 0.06):       # rails standing proud
                    boxes.append(wall.box(s0 + 0.03, s1 - 0.03, w1, w1 + 0.015, zz - 0.04, zz + 0.04))
    c.add("Shutters", boxes, c.mats["door"])


# --------------------------------------------------------------------------
# The arched front door and the French door over it
# --------------------------------------------------------------------------

def _entrance(c):
    o = next((o for o in c.ground.openings if o.kind == "ENTRANCE"), None)
    if o is None:
        return
    wall, t = _wall_of(c.ground, o), o.thickness or c.te
    s0, s1, zt = o.s0, o.s1, o.z1
    r, sm = (s1 - s0) / 2, (s0 + s1) / 2
    zs = zt - r
    face = _facade(c, c.ground, *wall.point(sm, t / 2 + 0.01, 1.0)[:2])
    m = c.mats
    va.add(c, "EntranceArch", wall, [va.prism(p, -t / 2, t / 2) for p in va.spandrels(s0, s1, zs, zt)],
           face, m["wall_in"], face)
    # Two leaves in one round-topped slab, a dark astragal where they meet, a pull handle on each
    va.add(c, "EntranceDoor", wall, [va.prism(va.round_top(s0, s1, 0.0, zs), -0.03, 0.03)], m["door"])
    va.add(c, "EntranceDoorTrim", wall, [va.box(sm - 0.014, sm + 0.014, -0.04, 0.04, 0.0, zt - 0.004)]
           + [va.box(sm + k - 0.012, sm + k + 0.012, 0.03, 0.06, 0.9, 1.2) for k in (-0.09, 0.09)], m["trim"])
    va.add(c, "EntranceSurround", wall, _surround(s0, s1, zs, t, 0.2, 0.06), _lime(c))
    c.add("EntranceStep", [wall.box(s0 - 0.6, s1 + 0.6, t / 2, t / 2 + 1.0, c.G, -0.03)], _lime(c))


def _arched_glazing(c, f, o, label):
    """A round-topped window or French door: the wall round its arch, the glass, a dark frame
    (jambs, sill, arched head, a transom at the spring, two or three lights, a sunburst of
    glazing bars in the fanlight) and a slim limestone surround -> (wall, thickness)."""
    wall, t = _wall_of(f, o), o.thickness or c.te
    s0, s1, z0, zt = o.s0, o.s1, o.z0, o.z1
    r, sm = (s1 - s0) / 2, (s0 + s1) / 2
    zs = zt - r
    m = c.mats
    face = _facade(c, f, *wall.point(sm, t / 2 + 0.01, 1.0)[:2])
    va.add(c, f"{label}Arch", wall, [va.prism(p, -t / 2, t / 2) for p in va.spandrels(s0, s1, zs, zt)],
           face, m["wall_in"], face)
    va.add(c, f"{label}Glass", wall, [va.prism(va.round_top(s0, s1, z0, zs), -0.003, 0.003)], m["glass"])
    fw, d = 0.05, 0.04
    lights = 2 if s1 - s0 < 1.5 else 3
    frame = [va.box(s0, s0 + fw, -d, d, z0, zs), va.box(s1 - fw, s1, -d, d, z0, zs),
             va.box(s0 + fw, s1 - fw, -d, d, z0, z0 + 0.04), va.band(sm, zs, r - fw, r, -d, d),
             va.box(s0 + fw, s1 - fw, -d, d, zs - fw, zs), va.band(sm, zs, 0.1, 0.14, -0.03, 0.03)]
    for k in range(1, lights):
        u = s0 + (s1 - s0) * k / lights
        frame.append(va.box(u - fw / 2, u + fw / 2, -d, d, z0 + 0.04, zs - fw))
    frame += [va.prism(va.ray(sm, zs, 0.14, r - fw, a, 0.03), -0.03, 0.03)
              for a in (math.pi / 4, math.pi / 2, 3 * math.pi / 4)]
    va.add(c, f"{label}Frame", wall, frame, m["trim"])
    sur = _surround(s0, s1, zs, t, 0.14, 0.04, z0=z0)
    if z0 > 0.2:                                            # a window: a sill under it
        sur.append(va.box(s0 - 0.2, s1 + 0.2, t / 2 - 0.06, t / 2 + 0.06, z0 - 0.08, z0 + 0.012))
    va.add(c, f"{label}Surround", wall, sur, _lime(c))
    return wall, t


def _arched_windows(c):
    """Round-topped windows other than the French door (the stone-clad front room's)."""
    for f in c.plan.floors:
        for k, o in enumerate(x for x in f.openings if getattr(x, "round", False) and x.kind == "WINDOW"):
            _arched_glazing(c, f, o, f"{f.label}_ArchedWindow{k}")


def _french_door(c):
    o = next((o for o in c.upper.openings if getattr(o, "round", False) and o.kind == "PATIO"), None)
    if o is None:
        return
    wall, t = _arched_glazing(c, c.upper, o, "FrenchDoor")
    s0, s1, m = o.s0, o.s1, c.mats

    # The little balcony: a limestone slab on two corbels, railed round (kept clear of the big
    # balcony's railing, which ends at the hall wall just beside it)
    deep, e = 0.55, 0.16
    a0, a1, out = s0 - e, s1 + e, t / 2 + deep
    lime = [wall.box(a0, a1, t / 2 - 0.02, out, -0.16, -0.02)]
    lime += [wall.box(q, q + 0.15, t / 2, out - 0.12, -0.42, -0.16) for q in (a0 + 0.05, a1 - 0.2)]
    c.add("JulietSlab", lime, _lime(c))
    rails = []
    inner = out - 0.04
    pts = [wall.point(a0 + 0.03, t / 2, -0.02), wall.point(a0 + 0.03, inner, -0.02),
           wall.point(a1 - 0.03, inner, -0.02), wall.point(a1 - 0.03, t / 2, -0.02)]
    for p, q in zip(pts[:-1], pts[1:]):
        _rail(rails, p[:2], q[:2], p[2], 0.95)
    c.add("JulietRail", rails, m["trim"])


# --------------------------------------------------------------------------
# Garden
# --------------------------------------------------------------------------

def _planters(c):
    """Two raised stone planters, clipped hedge on top, either side of the front path."""
    o = next((o for o in c.ground.openings if o.kind == "ENTRANCE"), None)
    if o is None:
        return
    te, G, m = c.te, c.G, c.mats
    mid = (o.s0 + o.s1) / 2
    y0, y1 = -te / 2 - 3.4, -te / 2 - 1.5
    rims, tops = [], []
    for sgn in (-1.0, 1.0):
        xa, xb = sorted((mid + sgn * PLANTER_GAP, mid + sgn * (PLANTER_GAP + 1.2)))
        rims.append((xa, y0, G - 0.05, xb, y1, G + 0.5))
        tops += [(xa + 0.08, y0 + 0.08, G + 0.5, xb - 0.08, y1 - 0.08, G + 0.74),      # clipped, rounded off
                 (xa + 0.15, y0 + 0.15, G + 0.74, xb - 0.15, y1 - 0.15, G + 0.82)]
    c.add("Planters", rims, m["accent"])
    c.add("PlanterHedges", tops, m.get("planter_top", m["accent"]))
