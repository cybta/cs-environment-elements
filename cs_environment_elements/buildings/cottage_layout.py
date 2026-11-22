"""Old cottage floor plans. Pure Python, built on house_layout's rooms, doors and walls.

A small timber house on piles after the classic 6 x 6 m dacha: a ground floor, and
bedrooms up in a gambrel (mansard) roof whose ridge runs from the front gable to the
back one. A covered veranda runs across the front; cottage.py builds it.
The painted style (roof="GABLE") has the same plan under a plain open gable roof on
taller knee walls.

        back (y = D)
    +-------------+-------------+
    |  (Bathroom) |   Bedroom   |
    |-------------+------+------|  yk
    |             |Stairs| nook |  the stair climbs towards the living-room wall,
    |   Living    +------+------+  so it arrives upstairs in the middle of the attic
    |    Room     |   Kitchen   |
    +-------------+----door-----+  y = 0, the veranda in front
    0             xs            W

Upstairs the stairwell is a hole in the attic floor. Rooms must tile the footprint
with rectangles, so a room with the hole in it is cut into pieces around it; the
first piece carries the room's name, the others are `quiet` (no label, no light).
"""

import math
import random

try:
    from . import house_layout as hl
    from .villa_layout import _mirror
except ImportError:  # run as a plain script, outside the addon package
    import house_layout as hl
    from villa_layout import _mirror

MIN_AREA = 45.0
ATTIC_SHARE = 0.65      # attic floor area, counted against the footprint, for the area setting
STAIR_W = 0.9
FOOT_CLEAR = 0.9        # free floor between the bottom step and the outside wall
KNEE = 0.35             # roof underside above the attic floor, on the side walls' centre line
PITCH_LOW, PITCH_UP = 60.0, 27.0
GABLE_KNEE, GABLE_PITCH = 0.9, 40.0     # the painted cottage's plain gable roof
BATH_D = 1.6


def gambrel(W, knee=KNEE, p1=PITCH_LOW, p2=PITCH_UP):
    """The roof underside over the west half, in attic-floor heights:
    (bx, zb, zr) = break inset from the wall line, height at the break, height at the ridge."""
    bx = min(max(0.22 * W, 1.0), 1.6)
    zb = knee + bx * math.tan(math.radians(p1))
    zr = zb + (W / 2 - bx) * math.tan(math.radians(p2))
    return bx, zb, zr


def gable(W, knee=GABLE_KNEE, pitch=GABLE_PITCH):
    """A plain gable in the same terms as gambrel(): the 'break' is the wall line itself,
    so both slopes are the one pitch."""
    zr = knee + W / 2 * math.tan(math.radians(pitch))
    return 0.0, knee, zr


def _pieces(name, kind, rect, hole, first=None):
    """A room as rectangles around `hole` -> [Room]. `first` picks the piece that carries
    the name (and so the doors); by default the biggest."""
    x0, y0, x1, y1 = rect
    hx0, hy0, hx1, hy1 = hole
    cand = [(x0, y0, x1, hy0), (x0, hy1, x1, y1), (x0, hy0, hx0, hy1), (hx1, hy0, x1, hy1)]
    rects = [c for c in cand if c[2] - c[0] > 0.05 and c[3] - c[1] > 0.05]
    rects.sort(key=lambda c: -(c[2] - c[0]) * (c[3] - c[1]))
    if first:
        rects.sort(key=lambda c: not first(c))
    rooms = []
    for i, (a, b, c, d) in enumerate(rects):
        r = hl.Room(name if i == 0 else f"{name} ({i + 1})", kind if i == 0 else "nook", a, b, c, d)
        r.quiet = i > 0
        rooms.append(r)
    return rooms


def _open_up(fl, names):
    """No walls between any of these rooms."""
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            fl.open_pairs.add(frozenset((a, b)))


def make_cottage_plan(area=60.0, bedrooms=2, bathrooms=0, seed=0, ceiling_h=2.5, slab=0.2,
                      t_ext=0.18, t_int=0.1, roof="GAMBREL"):
    rng = random.Random(seed * 53 + 11)
    plan = hl.Plan()
    plan.ceiling_h, plan.slab, plan.t_ext, plan.t_int = ceiling_h, slab, t_ext, t_int
    if area < MIN_AREA:
        plan.warnings.append(f"A cottage needs about {MIN_AREA:.0f} m2 or more; built at its smallest size")
        area = MIN_AREA

    # Footprint: W across the gable (x), D from the front gable to the back one (y)
    fp = area / (1.0 + ATTIC_SHARE)
    W = hl._snap(min(max(math.sqrt(fp) * rng.uniform(0.94, 1.04), 6.0), 8.0))
    D = hl._snap(min(max(fp / W, 5.5), 10.0))
    plan.W, plan.D = W, D

    # A straight, steep cottage stair along the kitchen / bedroom wall. n risers; the last
    # one steps onto the attic floor, so the flight has n - 1 treads.
    Hs = plan.storey_h
    n = max(6, math.ceil(Hs / 0.21))
    # Room to stand at the foot of the stair (the balusters close its open side, so you
    # step on and off at the end): FOOT_CLEAR to the inner face of the outside wall.
    foot = FOOT_CLEAR + t_ext / 2
    xs = hl._snap(W * rng.uniform(0.47, 0.53))
    going = min(max((W - xs - foot) / (n - 1), 0.185), 0.24)
    run = going * (n - 1) + t_int / 2
    if xs + run + foot > W:
        xs = math.floor((W - run - foot) / hl.SNAP) * hl.SNAP
    if xs < 2.4:
        plan.warnings.append("Cottage is narrow for its stair; the living room is tight")
    yk = hl._snap(min(max(D * 0.52, 3.0), D - 2.6))
    hole = (xs, yk - STAIR_W, xs + run, yk)

    # ---- Ground floor ---------------------------------------------------------
    g = hl.Floor(0)
    plan.floors.append(g)
    bath = bathrooms >= 1 and D - BATH_D - yk >= 1.25
    if bathrooms >= 1 and not bath:
        plan.warnings.append("No room for a bathroom in a cottage this small")
    yl = D - BATH_D if bath else D
    g.rooms.append(hl.Room("Living Room", "living", 0.0, 0.0, xs, yl))
    if bath:
        g.rooms.append(hl.Room("Bathroom", "bathroom", 0.0, yl, xs, D))
        g.connections.append(("Bathroom", "Living Room", "DOOR"))
    kitchen = _pieces("Kitchen", "kitchen", (xs, 0.0, W, yk), hole, first=lambda c: c[1] < 1e-4)
    g.rooms += kitchen
    g.rooms.append(hl.Room("Stairs", "stair", *hole))
    back = ("Bedroom", "bedroom") if bedrooms >= 2 else ("Study", "study")
    g.rooms.append(hl.Room(back[0], back[1], xs, yk, W, D))
    g.connections += [("Kitchen", "Living Room", "DOOR"), (back[0], "Living Room", "DOOR")]
    _open_up(g, [r.name for r in kitchen] + ["Stairs"])
    g.entrance_room = "Kitchen"

    # ---- Attic ------------------------------------------------------------------
    u = hl.Floor(1)
    plan.floors.append(u)
    u.entrance_room = None
    gabled = roof == "GABLE"
    knee, p_low, p_up = (GABLE_KNEE, GABLE_PITCH, GABLE_PITCH) if gabled else (KNEE, PITCH_LOW, PITCH_UP)
    bx, zb, zr = gable(W) if gabled else gambrel(W)
    u.wall_h = zr + 0.3                                 # gable walls run up to the roof, which trims them
    u.light_h = min(zr - 0.4, 2.4)
    two = bedrooms >= 3 and D - 2.4 >= yk + 1.0
    if bedrooms >= 3 and not two:
        plan.warnings.append("Only one bedroom fits in this attic")
    ya = hl._snap(min(max(D * 0.56, yk + 1.0), D - 2.4)) if two else D
    front = "Attic Bedroom 1" if two else "Attic Bedroom"
    attic = _pieces(front, "bedroom", (0.0, 0.0, W, ya), hole,
                    first=(lambda c: c[3] > ya - 1e-4) if two else None)
    u.rooms += attic
    u.rooms.append(hl.Room("Stairs", "stair", *hole))
    _open_up(u, [r.name for r in attic] + ["Stairs"])
    if two:
        u.rooms.append(hl.Room("Attic Bedroom 2", "bedroom", 0.0, ya, W, D))
        u.connections.append((front, "Attic Bedroom 2", "DOOR"))

    # ---- Doors and windows -------------------------------------------------------
    for f in plan.floors:
        f.base_z = f.index * plan.storey_h
        hl._place_openings(rng, plan, f)
    _cottage_windows(plan, g)

    # Upstairs: no windows in the knee walls, one in each gable, the door in the middle
    u.openings = [o for o in u.openings if o.kind not in ("WINDOW", "PATIO")]
    for y, edge in ((0.0, lambda r: r.y0 < 1e-4), (D, lambda r: r.y1 > D - 1e-4)):
        owner = next(r for r in u.rooms if edge(r) and r.x0 < W / 2 < r.x1)
        w = 0.8 if W < 6.5 else 1.0
        u.openings.append(hl.Opening("WINDOW", "X", y, W / 2 - w / 2, W / 2 + w / 2, 0.9, 2.0, (owner.name,)))
    for o in u.openings:
        if o.kind == "DOOR":
            w = o.s1 - o.s0
            o.s0, o.s1 = W / 2 - w / 2, W / 2 + w / 2

    for f in plan.floors:
        hl._build_walls(plan, f)

    # ---- Mirror for variety, then the notes cottage.py builds from ----------------
    up = -1.0                                           # the stair climbs towards -x (the living room)
    if rng.random() < 0.5:
        _mirror(plan, "X")
        hole = (W - hole[2], hole[1], W - hole[0], hole[3])
        up = 1.0
    p1, p2 = math.radians(p_low), math.radians(p_up)
    plan.clip[1] = [
        ((0.0, 0.0, knee), (-math.sin(p1), 0.0, math.cos(p1))),
        ((W, 0.0, knee), (math.sin(p1), 0.0, math.cos(p1))),
    ]
    if not gabled:
        plan.clip[1] += [
            ((bx, 0.0, zb), (-math.sin(p2), 0.0, math.cos(p2))),
            ((W - bx, 0.0, zb), (math.sin(p2), 0.0, math.cos(p2))),
        ]
    else:   # the gable triangles take upright boards (a role the painted palette fills)
        u.accents += [(-1.0, -1.0, W + 1.0, 0.0, "wall_gable"), (-1.0, D, W + 1.0, D + 1.0, "wall_gable")]
    plan.cottage = {
        "roof": roof, "knee": knee, "pitch_low": p_low, "pitch_up": p_up, "bx": bx, "zb": zb, "zr": zr,
        "hole": hole, "up": up, "risers": n,
        "veranda": 1.5 if W < 6.5 else rng.choice((1.8, 2.0)),
        "chimney_y": hl._snap(D * rng.uniform(0.3, 0.45)),
    }
    return plan


def _cottage_windows(plan, g):
    """Small old casement windows: the house rules' sizes, cut down, and no patio doors."""
    kinds = {r.name: r.kind for r in g.rooms}
    H = plan.ceiling_h
    for o in g.openings:
        if o.kind not in ("WINDOW", "PATIO"):
            continue
        o.kind = "WINDOW"
        kind = kinds.get(o.rooms[0], "")
        w, z0, z1 = {"bathroom": (0.6, 1.4, 1.95), "wc": (0.5, 1.4, 1.95),
                     "kitchen": (1.0, 1.0, 2.05)}.get(kind, (1.0, 0.85, 2.05))
        w = min(w, o.s1 - o.s0)
        m = (o.s0 + o.s1) / 2
        o.s0, o.s1, o.z0, o.z1 = m - w / 2, m + w / 2, z0, min(z1, H - 0.2)
