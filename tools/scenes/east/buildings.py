"""The east side's buildings from the add-on's generators (house._build with site=True) on east_plan.json's lots,
the front (each generator's -Y) toward the plan's front direction:

- houses: the House type, 100-140 m2 of floor in all, 2 floors (user, 2026-11-25: the pictures' 20 x 11 m
  houses were far too big);
- villas: Modern or Gable Villa (make_east.py's VILLA_STYLES), its own driveway and front path, a back patio, a pool
  in some;
- houses and villas stand with their facade GATE_GAP behind the lot's fence (user, 2026-11-25: 3-5 m): a villa's own
  driveway and front path are that long, so they end at the fence; sideways they keep the plan's (the pictures')
  line;
- the gate leads to a parking place and the fence's door is in line with the front door (user, 2026-11-25): a
  house gets a PAD_W x PAD_L parking space beside it (away from its door if there is room) that runs out through
  the gate to the street, and only layouts with the front door on the street side are kept; a villa's gate is on
  its own driveway (to the carport), its door at the end of its front path;
- the shop rows: Shopping Row, 3 shops of SHOP_W x SHOP_D (the user's 7 x 8 m), facing their parking or (the plan's
  faces = "street") the street, set forward so their own sidewalk meets the street's; signs from make_east.py's
  SHOP_SIGNS (Sam's Caffee, user 2026-11-25), numbered like the plan.
Each building sits on the middle of the ground under it (a shop row: its sidewalk level with the street's) and is
pulled into its lot if a part sticks out.
"""
import math
import random

import bpy
import numpy as np
from mathutils import Vector

from cs_environment_elements.buildings import house, shop_extras, villa
from cs_environment_elements.core import library
from old_neighborhood.drawn import inside
from old_neighborhood.lots import adopt

from .surfaces import WALK_TOP

OTHER_CAFES = ("CAFE", "TEA ROOM")          # generator sign names left out: the neighbourhood's café is Sam's
GATE_GAP = 4.0                              # facade to the lot's gate, m
PAD_W, PAD_L = 3.0, 6.0                     # a house's parking space inside its gate, m
PAD_GAP = 0.3                               # between it and the house's sidewalk ring
PAD_ROOM = PAD_GAP + PAD_W + 1.2            # needed beside the house: the space, and the gate's outer pillar


def _common(s, seed):
    s.add_labels, s.add_lights, s.add_inserts = False, False, True
    s.material_style, s.facade, s.roof_color = "NEIGHBORHOOD", "RANDOM", "RANDOM"
    s.seed = seed


def set_house(s, seed, attempt=0):
    """Two floors (user, 2026-11-25: "let all houses be 2 floor houses"). `attempt` > 0: another layout (seed) for
    the same size and roof."""
    rng = random.Random(seed)
    s.building_type = "HOUSE"
    _common(s, seed + 7919 * attempt)
    rng.choice((1, 2))               # (was the 1-or-2 floors draw: kept so each house keeps its size and roof)
    s.floors = 2
    s.total_area = 5 * round(rng.uniform(100.0, 140.0) / 5)          # all floors together
    big = s.total_area >= 120
    s.bedrooms, s.bathrooms, s.open_plan = (3, 2, True) if big else (2, 1, True)
    s.roof_type, s.ridge_dir = rng.choice(("GABLE", "HIP", "GABLE")), "LONG"
    s.sidewalk = True


def set_villa(s, seed, style):
    rng = random.Random(seed)
    s.building_type = "VILLA_" + style
    _common(s, seed)
    s.total_area = rng.uniform(280.0, 340.0) if style == "MODERN" else rng.uniform(300.0, 360.0)
    s.bedrooms, s.bathrooms = rng.choice((4, 5)), 3
    s.villa_site, s.villa_pool, s.villa_pitch = True, rng.random() < 0.5, 42.0


def set_shops(s, count, width, depth, seed, entrance="MIDDLE"):
    s.building_type = "SHOPS"
    _common(s, seed)
    g = s.shop
    g.count, g.width, g.depth, g.vary, g.entrance = count, width, depth, False, entrance
    g.signs, g.awnings, g.planters, g.sidewalk, g.fittings = True, True, True, True, True
    s.sidewalk = True


def generate(ctx, name, sign_names=None, ordered=False, front_yard=None):
    """Build what the panel settings say at the origin; its local bounds (front = -Y). Shop signs: drawn at random
    from `sign_names`, or (ordered) exactly those, shop by shop. `front_yard`: a villa's driveway / front path length
    (villa.FRONT_YARD, from the front wall's centre line)."""
    s = ctx.scene.house_gen
    ctx.scene.cursor.location = (0, 0, 0)
    saved = shop_extras.SIGN_NAMES, shop_extras.shop_names, villa.FRONT_YARD
    if sign_names and ordered:
        shop_extras.shop_names = lambda c, n: [sign_names[i % len(sign_names)] for i in range(n)]
    elif sign_names:
        shop_extras.SIGN_NAMES = tuple(sign_names)
    if front_yard is not None:
        villa.FRONT_YARD = front_yard
    try:
        plan = house._build(ctx, s, lambda *a: print(name, *a), name=name, site=True)
    finally:
        shop_extras.SIGN_NAMES, shop_extras.shop_names, villa.FRONT_YARD = saved
    root = bpy.data.objects[name]
    ctx.view_layer.update()
    lo, hi = library.bounds(root)
    return plan, root, (lo.x, lo.y, hi.x, hi.y)


class Placed:
    """A generated building turned so its -Y faces `front` and moved to `pos` (on the lowest ground under it)."""

    def __init__(self, root, box, front):
        self.root, self.box = root, box
        self.front = np.array(front, float) / np.linalg.norm(front)
        self.theta = math.atan2(self.front[0], -self.front[1])
        self.pos = np.zeros(2)

    def world(self, p):
        c, s = math.cos(self.theta), math.sin(self.theta)
        return self.pos + np.array([p[0] * c - p[1] * s, p[0] * s + p[1] * c])

    def footprint(self, box=None):
        x0, y0, x1, y1 = box or self.box
        return np.array([self.world(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1),
                                                 ((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1),
                                                 (x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2))])

    def settle(self, pos, terrain, lot=None, front_walk=False, fit=None):
        """Put the root at `pos`, pulled toward the lot's middle while any part of `fit` (a local box, default the
        whole building) is outside the lot. Height: the middle of the ground under it; a shop (front_walk) has its
        own sidewalk's top at the root, so that goes level with the street's sidewalk (WALK_TOP) at its front edge."""
        self.pos = np.array(pos, float)
        if lot is not None:
            mid = lot.mean(0)
            for _ in range(60):
                if inside(self.footprint(fit), lot).all():
                    break
                step = mid - self.pos
                self.pos = self.pos + step / (np.linalg.norm(step) or 1) * 0.25
        if front_walk:
            x0, y0, x1, _ = self.box
            z = float(terrain.height(np.array([self.world(p) for p in ((x0, y0), ((x0 + x1) / 2, y0), (x1, y0))]))
                      .max()) + WALK_TOP
        else:
            z = float(np.median(terrain.height(np.vstack([self.footprint(), self.pos]))))
        self.root.location = (self.pos[0], self.pos[1], z)
        self.root.rotation_euler.z = self.theta
        return float(np.linalg.norm(self.pos - np.array(pos, float)))


def ray_to_edge(p, d, poly):
    """How far from p along d to the polygon's boundary (inf if it never gets there)."""
    best = math.inf
    for a, b in zip(poly, np.roll(poly, -1, 0)):
        e = b - a
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-9:
            continue
        w = a - p
        t = (w[0] * e[1] - w[1] * e[0]) / den
        u = (w[0] * d[1] - w[1] * d[0]) / den
        if t > 0 and 0 <= u <= 1:
            best = min(best, t)
    return best


def _front_end(name, part):
    """The front middle of a villa part (`Driveway`, `FrontPath`) in the building's own frame, or None."""
    ob = bpy.data.objects.get("%s_%s" % (name, part))
    if ob is None:
        return None
    bb = [ob.matrix_local @ Vector(c) for c in ob.bound_box]
    return ((min(v.x for v in bb) + max(v.x for v in bb)) / 2, min(v.y for v in bb))


def _trim_front(name, part, pl, lot):
    """Pull a villa part's front edge (FrontPath) back inside the lot where a slanted fence cuts across it."""
    ob = bpy.data.objects.get("%s_%s" % (name, part))
    if ob is None:
        return
    x, y = _front_end(name, part)
    hx = (max(c[0] for c in ob.bound_box) - min(c[0] for c in ob.bound_box)) / 2
    over = 0.0
    for p in ((x - hx, y), (x, y), (x + hx, y)):
        q = pl.world(p)
        if not inside(q[None], lot)[0]:
            over = max(over, ray_to_edge(q, -pl.front, lot) + 0.05)
    if over and math.isfinite(over):
        me = ob.data
        y0 = min(v.co.y for v in me.vertices)
        for v in me.vertices:
            if v.co.y < y0 + 1e-4:
                v.co.y += over
        me.update()


def _entrance_x(plan):
    """The front door's middle (building frame, x), if the house has its entrance on the street front."""
    for o in plan.floors[0].openings:
        if o.kind == "ENTRANCE" and o.axis == "X" and o.coord < 0.01:
            return (o.s0 + o.s1) / 2 - plan.W / 2
    return None


def _room(pl, x, ys, d, lot):
    """Free ground beside the building: from local x sideways along d to the fence, the least at the depths ys."""
    return min(ray_to_edge(pl.world((x, y)), d, lot) for y in ys)


def _house_parking(pl, box, facade, door_x, lot, terrain):
    """A house's parking space: beside it, away from the front door if there is room there, else on the roomier
    side (the house moved over to make room if it must). Returns its middle line's x (building frame) and the
    sideways move."""
    side = np.array([-pl.front[1], pl.front[0]])
    ys = (facade - GATE_GAP + 0.4, facade, facade + PAD_L - GATE_GAP)       # by the gate, at the facade, its far end
    room = {1: _room(pl, box[2], ys, side, lot), -1: _room(pl, box[0], ys, -side, lot)}
    ok = [k for k in room if room[k] >= PAD_ROOM]
    if ok:                                                  # away from the front door first, then the roomier
        k = max(ok, key=lambda k: (k * (door_x or 0.0) < 0, room[k]))
    else:
        k = max(room, key=room.get)
    shift = 0.0
    if room[k] < PAD_ROOM and room[-k] - (PAD_ROOM - room[k]) >= 0.6:
        shift = PAD_ROOM - room[k]
        pl.settle(pl.pos - side * k * shift, terrain, lot)
    x = box[2] + PAD_GAP + PAD_W / 2 if k > 0 else box[0] - PAD_GAP - PAD_W / 2
    return x, shift


def _pad_start(pl, x, facade, lot):
    """The inner end of the parking space whose middle line is at x (building frame): PAD_L in from the fence."""
    face = pl.world((x, facade))
    reach = ray_to_edge(face, pl.front, lot)
    return face + pl.front * (reach - PAD_L) if math.isfinite(reach) else face


def _onto_street(to_road, start, front):
    end = to_road(start, front)
    return end is not None and np.linalg.norm(end - start) < PAD_L + 6.0


def _slide_to_street(pl, box, facade, x_pad, lot, to_road):
    """Where the street ends in front of a house (a road's end), its parking strip can miss it: slide the house
    sideways (either way, either side for the parking) until the strip runs straight onto the street, house and
    parking inside the lot. Returns the parking's x and the slide, or None."""
    side = np.array([-pl.front[1], pl.front[0]])
    x_other = box[0] - PAD_GAP - PAD_W / 2 if x_pad > 0 else box[2] + PAD_GAP + PAD_W / 2
    base = pl.pos.copy()
    for d in np.arange(0.5, 10.01, 0.5):
        for x in (x_pad, x_other):
            for sgn in (1, -1):
                pl.pos = base + side * sgn * d
                pad = (x - PAD_W / 2, facade - GATE_GAP + 0.3, x + PAD_W / 2, facade - GATE_GAP + PAD_L)
                if (inside(pl.footprint(), lot).all() and inside(pl.footprint(pad), lot).all()
                        and _onto_street(to_road, _pad_start(pl, x, facade, lot), pl.front)):
                    return x, float(d)
    pl.pos = base
    return None


def build_lot(ctx, L, terrain, coll, seed, style=None, to_road=None):
    """One house or villa (style MODERN / GABLE) on its lot. `to_road(start, front)`: where a driveway from `start`
    along `front` reaches the asphalt (or None). Returns the
    placed building and what the fences, the driveways, the paths and the built record need:
    - drive_start: where the car strip starts (a house: the far end of its parking space beside it; a villa: the
      front end of its own driveway, at the fence), running along the front through the gate to the street;
    - door_start: where the walk to the street starts (a house: in front of its front door; a villa: the end of its
      own front path), so the fence's door is in line with the house's."""
    b = L["building"]
    lot = np.array(L["outline"], float)
    sid = seed * 101 + int("".join(ch for ch in L["name"] if ch.isdigit()) or 0) + (50 if L["kind"] == "villa" else 0)
    s = ctx.scene.house_gen
    is_villa = L["kind"] == "villa"
    name = "east-%s" % L["name"].lower().replace(" ", "-")
    if is_villa:
        style = style or "GABLE"
        set_villa(s, sid, style)
        plan, root, box = generate(ctx, name, front_yard=GATE_GAP)
    else:
        style = "HOUSE"
        for attempt in range(16):         # the front door on the street side, and (two floors this small) stairs
            set_house(s, sid, attempt)                                          # that aren't too steep
            plan, root, box = generate(ctx, name)
            if _entrance_x(plan) is not None and not any("stair" in w for w in plan.warnings):
                break
        else:
            print("  %s: no layout with the front door on the street and easy stairs; kept the last" % name)
    for w in plan.warnings:
        print("  %s: %s" % (name, w))
    adopt(bpy.data.collections[name], coll)
    pl = Placed(root, box, b["front_dir"])
    hw, hd = plan.W / 2 + plan.t_ext / 2, plan.D / 2 + plan.t_ext / 2         # outer wall faces
    facade = -hd
    drive = _front_end(name, "Driveway")                  # a villa's own driveway (GATE_GAP long: to the fence)
    aim, gap = (drive, 0.05) if drive else ((0.0, facade), GATE_GAP)
    side = np.array([-pl.front[1], pl.front[0]])          # the building's +X
    centre = np.array(b["centre"], float)
    # on the plan's line (the pictures'), or, if a villa's driveway would then miss the street, with the driveway on
    # it; then forward (or back) along the front until the facade is GATE_GAP behind the fence
    for lateral in ((0.0, -aim[0]) if drive else (0.0,)):
        pl.pos = centre + side * lateral
        shift = ray_to_edge(pl.world(aim), pl.front, lot) - gap
        want = pl.pos + pl.front * shift if math.isfinite(shift) else pl.pos
        pl.pos = want
        if drive and to_road:
            start = pl.world(drive)
            end = to_road(start, pl.front)
            if end is not None and np.linalg.norm(end - start) < gap + 5.0:         # ~5 m past the gate
                break
    fit = (box[0], facade, box[2], box[3]) if is_villa else None          # the front yard may meet a slanted fence
    moved = pl.settle(want, terrain, lot, fit=fit)
    pad_shift = 0.0
    if is_villa:
        _trim_front(name, "FrontPath", pl, lot)
        start = pl.world(drive)
        path = _front_end(name, "FrontPath")
        door_start, door_x = (pl.world(path), path[0]) if path else (None, drive[0])
        gate_x = drive[0]
    else:
        door_x = _entrance_x(plan)
        x_pad, pad_shift = _house_parking(pl, box, facade, door_x, lot, terrain)
        start = _pad_start(pl, x_pad, facade, lot)
        if to_road and not _onto_street(to_road, start, pl.front):
            slid = _slide_to_street(pl, box, facade, x_pad, lot, to_road)
            if slid:
                x_pad, d = slid
                pad_shift += d
                pl.settle(pl.pos, terrain, lot)
                start = _pad_start(pl, x_pad, facade, lot)
        door_x = 0.0 if door_x is None else door_x
        door_start = pl.world((door_x, box[1]))
        gate_x = door_x
    gate = ray_to_edge(pl.world((gate_x, facade)), pl.front, lot)
    walls = [tuple(round(float(v), 2) for v in pl.world(p)) for p in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]
    return dict(name=name, kind=L["kind"], style=style, placed=pl, moved=moved, W=plan.W, D=plan.D,
                floors=len(plan.floors), area=round(s.total_area), walls=walls, gate_m=gate, drive_start=start,
                door_start=door_start, lateral=lateral, pad_shift=pad_shift)


def build_shops(ctx, row, pad, terrain, coll, seed, width, depth, signs=None):
    """A shop row on its pad. `signs`: the shops' names in the plan's numbering (None = one of the generator's)."""
    s = ctx.scene.house_gen
    sid = seed * 101 + 900 + row["first_number"]
    set_shops(s, row["shops"], width, depth, sid)
    pool = [n for n in shop_extras.SIGN_NAMES if n not in OTHER_CAFES]        # the café is Sam's
    random.Random(sid).shuffle(pool)
    names = [n or pool.pop() for n in (signs or [None] * row["shops"])]
    # the generator names its shops along its own +X; the plan numbers them along axis_dir
    pl = Placed(None, None, row["front_dir"])
    flip = math.cos(pl.theta) * row["axis_dir"][0] + math.sin(pl.theta) * row["axis_dir"][1] < 0
    name = "east-shops-%d-%d" % (row["first_number"], row["first_number"] + row["shops"] - 1)
    plan, root, box = generate(ctx, name, names[::-1] if flip else names, ordered=True)
    adopt(bpy.data.collections[name], coll)
    pl.root, pl.box = root, box
    centre = np.array(row["centre"], float)
    if row.get("faces") == "street":     # forward, so its own sidewalk meets the street's at the pad's edge
        reach = ray_to_edge(centre, pl.front, np.array(pad["outline"], float))
        if math.isfinite(reach):
            centre = centre + pl.front * (reach - (-box[1]) - 0.05)
    pl.settle(centre, terrain, front_walk=True)
    hw, hd = plan.W / 2 + plan.t_ext / 2, plan.D / 2 + plan.t_ext / 2
    bays = [n for n in plan.shops["bays"] if n["kind"] == "shop"]
    if flip:
        bays = bays[::-1]
    shops = [dict(number=row["first_number"] + i, sign=nm,
                  door=tuple(round(float(v), 2) for v in pl.world(((n["x0"] + n["x1"]) / 2 - plan.W / 2, -hd))))
             for i, (nm, n) in enumerate(zip(names, bays))]
    walls = [tuple(round(float(v), 2) for v in pl.world(p)) for p in ((-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd))]
    return dict(name=name, placed=pl, W=plan.W, D=plan.D, walls=walls, shops=shops)
