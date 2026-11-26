"""Finishing touches for the modern and gable villas (villa.build_exterior hands over here
once the house, roof, carport, site and pool are up), after the user's references of 2026-11-26:

- gable: a dark gutter along each eave and downpipes down the corners, concrete footings
  under the carport posts,
- modern: deep dark box frames round the plain windows (not the stone bay's glazing), many
  of them widened to hold a panel of vertical oak slats beside the glass; the back terrace and
  pergola (villa_terrace),
- warm wall lights either side of the front door,
- with the site on: a gravel strip along the front wall and planted beds (shrubs and slim
  conifers, steel edging) either side of the door, and bollard lights along the path and
  driveway (left out on a raised podium, whose terrace takes the path's place),
- modern: a small cantilevered balcony (dark slab, frameless glass, downlights under it) at each
  French door in the side walls upstairs (villa_layout._side_balcony_doors).
No furniture: the user adds props by hand.

Plan coordinates as in villa.py: front at y = 0, ground floor at z = 0, ground at c.G.
"""

import math
import random

import bmesh
from mathutils import Vector

from .house_walls import OUTDOOR
from .mesh_utils import _obj, _solid
from .villa import FRONT_YARD
from .villa_med import _wall_of

EPS = 1e-4


def _mat(c, role, fallback, color):
    """The palette's material for `role`, else a plain one (the non-neighbourhood styles)."""
    if role in c.mats:
        return c.mats[role]
    if fallback in c.mats:
        return c.mats[fallback]
    from ..core.materials import _material
    return _material(f"RoomGen_Villa{role.title().replace('_', '')}", color)


def dress(c):
    from . import podium
    rng = random.Random(c.s.seed * 31 + 7)
    _window_boxes(c, rng)
    if c.modern:
        from . import villa_terrace
        _side_balconies(c)
        villa_terrace.build(c)
    else:
        _gutters(c)
        _footings(c)
    _wall_lights(c)
    _door_lights(c)
    if c.s.villa_site:
        _front_garden(c, rng)
        if not podium.active(c.s):
            _bollards(c)


# --------------------------------------------------------------------------
# Rainwater: gutters along the eaves, downpipes at the corners
# --------------------------------------------------------------------------

def _gutters(c):
    W, D, te, G = c.W, c.D, c.te, c.G
    tn = math.tan(math.radians(c.plan.villa["pitch"]))
    x_e = -te / 2 - 0.3                                     # the eave edge (villa._gable_roof)
    z_e = c.F1 + c.plan.villa["knee"] + x_e * tn
    y0, y1 = -te / 2 - 0.4, D + te / 2 + 0.4
    gutters, pipes = [], []
    # the back corner on a side with the covered terrace cut out of it has no wall to run down
    open_back = {side for r in c.ground.rooms if r.kind in OUTDOOR and r.y1 > D - EPS
                 for side, on in (("W", r.x0 < EPS), ("E", r.x1 > W - EPS)) if on}
    for side in ("W", "E"):
        def X(x):
            return x if side == "W" else W - x
        xa, xb = sorted((X(x_e - 0.16), X(x_e)))
        gutters.append((xa, y0, z_e - 0.13, xb, y1, z_e - 0.01))
        gx = X(x_e - 0.08)                                  # under the gutter's middle
        pa, pb = sorted((X(-te / 2 - 0.1), X(-te / 2 - 0.02)))      # against the side wall
        ca, cb = sorted((gx, X(-te / 2 - 0.02)))
        ys = [-te / 2 + 0.12] + ([] if side in open_back else [D + te / 2 - 0.2])
        for y in ys:
            pipes.append((gx - 0.04, y, z_e - 0.38, gx + 0.04, y + 0.08, z_e - 0.12))   # out of the gutter
            pipes.append((ca, y, z_e - 0.38, cb, y + 0.08, z_e - 0.3))                  # back to the wall
            pipes.append((pa, y, G, pb, y + 0.08, z_e - 0.3))                           # down it
    edge = _mat(c, "fascia", "trim", (0.05, 0.05, 0.06))
    c.add("Gutters", gutters, edge)
    c.add("Downpipes", pipes, edge)


# --------------------------------------------------------------------------
# Modern villa: box frames
# --------------------------------------------------------------------------

def _slat_panel(c, f, o, zones, rng):
    """(s0, s1) for a slat panel beside window `o` (the side with room for it), or None."""
    if rng.random() > 0.65:
        return None
    pw = min(max((o.s1 - o.s0) * 0.6, 0.5), 0.9)
    end = c.W if o.axis == "X" else c.D
    others = [(q.s0, q.s1) for q in f.openings if q is not o and q.axis == o.axis and abs(q.coord - o.coord) < 0.05]
    sides = [(o.s1, o.s1 + pw), (o.s0 - pw, o.s0)]
    if rng.random() < 0.5:
        sides.reverse()
    for a, b in sides:
        if a < 0.45 or b > end - 0.45 or any(a < q1 + 0.55 and q0 - 0.55 < b for q0, q1 in others):
            continue
        m = (a + b) / 2
        x, y = (m, o.coord) if o.axis == "X" else (o.coord, m)
        if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1, _ in zones):
            continue
        return a, b
    return None


def _window_boxes(c, rng, w=0.1, proud=0.16):
    """A deep dark box round each plain window: jambs, head and sill standing out of the render,
    some widened round a panel of vertical oak slats beside the glass. The stone bay's and the
    carport's walls keep their own look."""
    backing, slats = [], []
    frame = _mat(c, "fascia", "trim", (0.05, 0.05, 0.06))
    for f in c.plan.floors:
        boxes = []
        zones = [z for z in f.accents if z[4] in ("accent", "recess", "carport_wall")]
        for o in f.openings:
            balcony = _is_balcony_door(c, f, o)
            if not o.exterior or (o.kind != "WINDOW" and not balcony):
                continue
            r = f.room(o.rooms[0])
            if r.kind in OUTDOOR:
                continue
            mid = (o.s0 + o.s1) / 2
            x, y = (mid, o.coord) if o.axis == "X" else (o.coord, mid)
            if any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1, _ in zones):
                continue
            t = o.thickness or c.te
            wall = _wall_of(f, o)
            a, b = t / 2 - 0.01, t / 2 + proud
            lo, hi = o.s0, o.s1
            panel = _slat_panel(c, f, o, zones, rng) if c.modern else None     # (the gable is all oak)
            if panel:
                p0, p1 = panel
                lo, hi = min(lo, p0), max(hi, p1)
                cut = o.s1 if p0 >= o.s1 else o.s0                     # a bar between glass and slats
                boxes.append(wall.box(cut - w / 4, cut + w / 4, a, b, o.z0, o.z1))
                backing.append(wall.box(p0, p1, t / 2 - 0.005, t / 2 + 0.02, o.z0, o.z1))
                n = max(3, int((p1 - p0) / 0.075))
                for k in range(n):
                    s = p0 + (p1 - p0) * (k + 0.5) / n
                    slats.append(wall.box(s - 0.018, s + 0.018, t / 2 + 0.02, t / 2 + 0.075, o.z0, o.z1))
            zb = o.z0 if balcony else o.z0 - w                     # a door's box stops at the floor
            boxes += [wall.box(lo - w, lo, a, b, zb, o.z1 + w), wall.box(hi, hi + w, a, b, zb, o.z1 + w),
                      wall.box(lo, hi, a, b, o.z1, o.z1 + w)]
            if not balcony:
                boxes.append(wall.box(lo, hi, a, b, o.z0 - w, o.z0))
        c.add(f"{f.label}_WindowBoxes", boxes, frame, planes=c.planes(f))     # (trimmed by a gable roof)
    c.add("WindowSlatBacking", backing, _mat(c, "carport_wall", "trim", (0.12, 0.1, 0.09)))
    c.add("WindowSlats", slats, _mat(c, "soffit_wood", "accent", (0.55, 0.37, 0.2)))


# --------------------------------------------------------------------------
# Modern villa: side balconies
# --------------------------------------------------------------------------

def _is_balcony_door(c, f, o):
    """A French door upstairs in a side wall (villa_layout._side_balcony_doors)."""
    return (c.modern and f.index == 1 and o.exterior and o.kind == "PATIO" and o.axis == "Y"
            and (abs(o.coord) < 0.05 or abs(o.coord - c.W) < 0.05))


def _side_balconies(c, deep=1.1, over=0.35, rail=1.0):
    f = c.upper
    slab, glass, lights = [], [], []
    for o in f.openings:
        if not _is_balcony_door(c, f, o):
            continue
        wall, t = _wall_of(f, o), o.thickness or c.te
        a0, a1, d0, d1 = o.s0 - over, o.s1 + over, t / 2, t / 2 + deep
        slab.append(wall.box(a0, a1, d0, d1, -0.24, -0.02))
        g = 0.012
        glass += [wall.box(a0 + 0.03, a1 - 0.03, d1 - 0.04, d1 - 0.04 + g, -0.02, rail),
                  wall.box(a0 + 0.03, a0 + 0.03 + g, d0 + 0.02, d1 - 0.04, -0.02, rail),
                  wall.box(a1 - 0.03 - g, a1 - 0.03, d0 + 0.02, d1 - 0.04, -0.02, rail)]
        for s in (a0 + (a1 - a0) * 0.3, a0 + (a1 - a0) * 0.7):
            lights.append(wall.box(s - 0.05, s + 0.05, (d0 + d1) / 2 - 0.05, (d0 + d1) / 2 + 0.05, -0.247, -0.239))
    c.add("SideBalconies", slab, _mat(c, "fascia", "trim", (0.05, 0.05, 0.06)))
    c.add("SideBalconyGlass", glass, _mat(c, "glass", "glass", (0.8, 0.9, 1.0)))
    c.add("SideBalconyLights", lights, _mat(c, "lamp", "glass", (1.0, 0.75, 0.45)))


# --------------------------------------------------------------------------
# Lights
# --------------------------------------------------------------------------

def _entrance(c):
    return next((o for o in c.ground.openings if o.kind == "ENTRANCE"), None)


def _wall_lights(c):
    """A slim black up-and-down light either side of the front door, glowing warm."""
    ent = _entrance(c)
    if ent is None:
        return
    y = -c.te / 2
    bodies, glow = [], []
    for x in (ent.s0 - 0.38, ent.s1 + 0.26):
        if c.drive and c.drive[0] - 0.1 < x + 0.12 and x < c.drive[1] + 0.1:
            continue                                        # that side opens into the carport
        bodies.append((x, y - 0.13, 1.8, x + 0.12, y, 2.2))
        glow += [(x + 0.02, y - 0.135, 1.78, x + 0.1, y - 0.01, 1.8),           # light spilling down
                 (x + 0.02, y - 0.135, 2.2, x + 0.1, y - 0.01, 2.22)]           # and up
    c.add("WallLights", bodies, _mat(c, "fascia", "trim", (0.05, 0.05, 0.06)))
    c.add("WallLightGlow", glow, _mat(c, "lamp", "glass", (1.0, 0.75, 0.45)))


def _door_lights(c):
    """Up-and-down wall lights either side of every glazed door on the ground floor (terrace and
    garden doors), where the wall beside it is free."""
    f = c.ground
    bodies, glow = [], []
    for o in f.openings:
        if not o.exterior or o.kind != "PATIO" or getattr(o, "round", False):
            continue
        wall, t = _wall_of(f, o), o.thickness or c.te
        end = c.W if o.axis == "X" else c.D
        others = [(q.s0, q.s1) for q in f.openings if q is not o and q.axis == o.axis and abs(q.coord - o.coord) < 0.05]
        for s in (o.s0 - 0.4, o.s1 + 0.28):
            if s < 0.2 or s + 0.12 > end - 0.2 or any(s < q1 + 0.3 and q0 - 0.3 < s + 0.12 for q0, q1 in others):
                continue
            bodies.append(wall.box(s, s + 0.12, t / 2, t / 2 + 0.13, 1.8, 2.2))
            glow += [wall.box(s + 0.02, s + 0.1, t / 2 + 0.01, t / 2 + 0.135, 1.78, 1.8),
                     wall.box(s + 0.02, s + 0.1, t / 2 + 0.01, t / 2 + 0.135, 2.2, 2.22)]
    c.add("DoorLights", bodies, _mat(c, "fascia", "trim", (0.05, 0.05, 0.06)))
    c.add("DoorLightGlow", glow, _mat(c, "lamp", "glass", (1.0, 0.75, 0.45)))


def _bollards(c):
    """Knee-high black bollards with a glowing band, along the front path and the driveway's
    garden side."""
    ent = _entrance(c)
    G = c.G
    spots = []
    if ent is not None:
        mid = (ent.s0 + ent.s1) / 2
        for y in (-FRONT_YARD + 0.6, -FRONT_YARD / 2 - 0.4):
            spots += [(mid - 1.05, y), (mid + 1.05, y)]
    if c.drive:
        x0, x1, _ = c.drive
        outer = x0 - 0.3 if (x0 + x1) / 2 < c.W / 2 else x1 + 0.3
        spots += [(outer, y) for y in (-FRONT_YARD + 0.6, -FRONT_YARD / 2, -0.6)]
    posts, glow = [], []
    for x, y in spots:
        posts += [(x - 0.05, y - 0.05, G, x + 0.05, y + 0.05, G + 0.48),
                  (x - 0.065, y - 0.065, G + 0.55, x + 0.065, y + 0.065, G + 0.62)]
        glow.append((x - 0.045, y - 0.045, G + 0.48, x + 0.045, y + 0.045, G + 0.55))
    c.add("Bollards", posts, _mat(c, "fascia", "trim", (0.05, 0.05, 0.06)))
    c.add("BollardGlow", glow, _mat(c, "lamp", "glass", (1.0, 0.75, 0.45)))


# --------------------------------------------------------------------------
# Carport footings
# --------------------------------------------------------------------------

def _footings(c):
    ob = c.coll.objects.get(f"{c.name}_CarportPosts")
    if ob is None:
        return
    boxes = []
    for k in range(0, len(ob.data.vertices), 8):            # one box (8 corners) per post
        vs = [ob.data.vertices[k + i].co - c.center for i in range(8)]
        x0, x1 = min(v.x for v in vs), max(v.x for v in vs)
        y0, y1 = min(v.y for v in vs), max(v.y for v in vs)
        boxes.append((x0 - 0.1, y0 - 0.1, c.G, x1 + 0.1, y1 + 0.1, c.G + 0.4))
    c.add("CarportFootings", boxes, _mat(c, "footing", "paving", (0.55, 0.54, 0.52)))


# --------------------------------------------------------------------------
# Front garden
# --------------------------------------------------------------------------

def _blob(x, y, z, rx, rz, rng):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=1, radius=1.0)
    verts = []
    for v in bm.verts:
        j = 1.0 + rng.uniform(-0.12, 0.12)
        verts.append(Vector((x + v.co.x * rx * j, y + v.co.y * rx * j, z + v.co.z * rz * j)))
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return verts, faces


def _cone(x, y, z, r, h, n=8):
    """A slim conifer: a short trunk-less cone with a rounded shoulder."""
    rings = [(0.0, r * 0.6), (h * 0.25, r), (h * 0.7, r * 0.55), (h, 0.0)]
    verts = [Vector((x + rr * math.cos(2 * math.pi * i / n), y + rr * math.sin(2 * math.pi * i / n), z + hh))
             for hh, rr in rings for i in range(n)]
    faces = [list(range(n))[::-1]]
    for k in range(len(rings) - 1):
        b = k * n
        faces += [[b + i, b + (i + 1) % n, b + n + (i + 1) % n, b + n + i] for i in range(n)]
    return verts, faces


def _plants(c, label, parts, mat):
    if not parts:
        return
    verts, faces = [], []
    for v, f in parts:
        base = len(verts)
        verts += [p + c.center for p in v]
        faces += [[base + i for i in face] for face in f]
    _obj(f"{c.name}_{label}", _solid(f"{c.name}_{label}", verts, faces), c.coll, c.root, [mat])


def _front_garden(c, rng):
    """A gravel strip along the front wall, then a planted bed either side of the door."""
    ent = _entrance(c)
    if ent is None:
        return
    W, te, G = c.W, c.te, c.G
    mid = (ent.s0 + ent.s1) / 2
    gap = (min(ent.s0 - 0.5, mid - 0.9), max(ent.s1 + 0.5, mid + 0.9))        # the step and the path
    wall, strip, deep = -te / 2, 0.45, 1.9
    lo, hi = -te / 2, W + te / 2
    if c.modern:                                           # clear of the stone fin's front block
        if c.upper.room(c.plan.villa["bay"]).x1 > W - EPS:
            hi -= 0.4
        else:
            lo += 0.4
    spans = [(lo, gap[0]), (gap[1], hi)]
    if c.drive:                                            # keep the driveway's mouth clear
        d0, d1 = c.drive[0] - 0.3, c.drive[1] + 0.3
        spans = [p for a, b in spans for p in ((a, min(b, d0)), (max(a, d1), b)) if p[1] > p[0]]
    spans = [(a, b) for a, b in spans if b - a > 0.8]
    gravel, beds, edging, shrubs, light, cones = [], [], [], [], [], []
    for a, b in spans:
        gravel.append((a, wall - strip, G, b, wall, G + 0.03))
        y0, y1 = wall - strip - deep, wall - strip
        beds.append((a + 0.05, y0 + 0.05, G, b - 0.05, y1 - 0.05, G + 0.07))
        e = 0.02
        edging += [(a, y0, G, b, y0 + e, G + 0.1), (a, y1 - e, G, b, y1, G + 0.1),
                   (a, y0, G, a + e, y1, G + 0.1), (b - e, y0, G, b, y1, G + 0.1)]
        # A row of shrubs along the bed, a slim conifer at each end of it
        n = max(1, int((b - a - 1.2) / 0.75))
        for k in range(n):
            x = a + 0.6 + (b - a - 1.2) * (k + 0.5) / n + rng.uniform(-0.12, 0.12)
            y = (y0 + y1) / 2 + rng.uniform(-0.35, 0.35)
            r = rng.uniform(0.28, 0.42)
            (shrubs if rng.random() < 0.6 else light).append(_blob(x, y, G + 0.07 + r * 0.55, r, r * 0.75, rng))
        for x in (a + 0.35, b - 0.35):
            cones.append(_cone(x, y1 - 0.45, G + 0.07, rng.uniform(0.24, 0.3), rng.uniform(1.3, 1.8)))
    c.add("Gravel", gravel, _mat(c, "gravel", "paving", (0.36, 0.33, 0.3)))
    c.add("Beds", beds, _mat(c, "mulch", "paving", (0.08, 0.055, 0.04)))
    c.add("BedEdging", edging, _mat(c, "fascia", "trim", (0.05, 0.05, 0.06)))
    dark = _mat(c, "shrub", "accent", (0.04, 0.15, 0.03))
    _plants(c, "Shrubs", shrubs + cones, dark)
    _plants(c, "ShrubsLight", light, _mat(c, "shrub_light", "accent", (0.1, 0.22, 0.05)))
