"""Villa floor plans. Pure Python, built on house_layout's rooms, doors and walls.

Two styles here, both two storeys with the street at the front (y = 0); the third,
MEDITERRANEAN, has its own module (villa_med_layout) built on these helpers:

MODERN - a flat-roofed box, narrow and deep. A two-car carport is cut out of
the ground floor's front corner, the upper floor runs over it, and a balcony
is recessed into the upper floor above the carport.

GABLE - a steep gable facing the street. The upper floor sits inside the roof
(knee walls at the eaves, walls trimmed by the roof planes), with a balcony
recessed under the gable and a covered terrace cut out of the back corner.

Both are laid out the same way, then turned to face the street:

      back                                              front
    +---------+--------+-----------------+-------------------+
    |         | Stairs |   rooms         |   front room      |   north row
    | public  +--------+-----------------+----------+--------+
    |  zone      hallway ...............................  -> | entrance / balcony
    |         +-----------------+------------------+---------+
    |         |   rooms         | (ensuite) master | carport |   south row
    +---------+-----------------+------------------+ balcony +
"""

import math
import random

try:
    from . import house_layout as hl
except ImportError:  # run as a plain script, outside the addon package
    import house_layout as hl

CORRIDOR_W = 1.4
STAIR_LEN = hl.STAIR_LEN
HALL = "Hallway"

# Villa rooms are roomier than the house generator's: weights and targets in m2.
AREA = {"master": 20.0, "bedroom": 14.0, "bathroom": 6.0, "wc": 2.6, "study": 10.0, "storage": 4.0}
MAX_AREA = {"bathroom": 9.0, "wc": 3.5, "storage": 7.0}

MIN_AREA = {"MODERN": 185.0, "GABLE": 160.0, "MEDITERRANEAN": 380.0}     # (villa_med_layout.MIN_AREA)


class _Seg:
    """A stretch of one row, filled with rooms side by side."""

    def __init__(self, a, b, y0, y1, pinned=()):
        self.a, self.b, self.y0, self.y1 = a, b, y0, y1
        self.items = []
        self.pinned = list(pinned)      # kept in this order at the front end
        self.limit = None               # most rooms it may take besides the pinned ones

    @property
    def length(self):
        return self.b - self.a

    @property
    def cap(self):
        return self.length * (self.y1 - self.y0)

    def all(self):
        return self.items + self.pinned

    def free(self):
        return self.cap - sum(AREA[k] for _, k in self.all())

    def fits(self, kind=None):
        if kind and self.limit is not None and len(self.items) >= self.limit:
            return False
        ks = [k for _, k in self.all()] + ([kind] if kind else [])
        return sum(hl.MIN_WIDTH[k] for k in ks) <= self.length + hl.EPS


def _assign(rng, rooms, segs):
    """Biggest rooms first, each into the segment with the most space left."""
    for item in sorted(rooms, key=lambda r: -AREA[r[1]]):
        max(segs, key=lambda s: (s.fits(item[1]), s.free() * rng.uniform(0.9, 1.1))).items.append(item)


def _fill_spare(segs, spare, stores):
    """Give empty or half-empty segments a study or a store room."""
    spare, stores = iter(spare), iter(stores)
    for s in segs:
        if not s.all() and s.length > 0.6:
            big = s.cap >= 7.0 and s.length >= hl.MIN_WIDTH["study"]
            s.items.append((next(spare, "Study"), "study") if big else (next(stores, "Storage"), "storage"))
            continue
        while s.free() >= 10.0 and s.fits("study"):
            s.items.append((next(spare, "Study"), "study"))
        if s.free() >= 4.5 and s.fits("storage"):
            s.items.append((next(stores, "Storage"), "storage"))


def _place(rng, plan, fl, seg, no_door=()):
    """Turn a segment's items into rooms, each with a door onto the hallway."""
    rng.shuffle(seg.items)
    items = seg.all()
    if not items:
        return
    kinds = [k for _, k in items]
    widths = hl._distribute(seg.length, kinds, [AREA[k] for k in kinds], seg.y1 - seg.y0)
    x = seg.a
    for i, ((name, kind), w) in enumerate(zip(items, widths)):
        x1 = seg.b if i == len(items) - 1 else hl._snap(x + w)
        fl.rooms.append(hl.Room(name, kind, x, seg.y0, x1, seg.y1))
        if name not in no_door:
            fl.connections.append((name, HALL, "DOOR"))
        x = x1
    if not seg.fits():
        plan.warnings.append(f"{fl.label}: rooms squeezed below comfortable width")


def _clear(f, axis, coord, s0, s1):
    """Drop the windows the house rules put on a stretch of wall."""
    f.openings = [o for o in f.openings if not (
        o.kind in ("WINDOW", "PATIO") and o.axis == axis and abs(o.coord - coord) < 1e-4
        and o.s1 > s0 + 1e-4 and o.s0 < s1 - 1e-4)]


def _glaze(f, room, axis, coord, s0, s1, z0, z1, kind="PATIO", width=None, pad=0.35):
    """One big pane on a room's wall between s0 and s1 (centred, at most `width` wide)."""
    _clear(f, axis, coord, s0, s1)
    a, b = s0 + pad, s1 - pad
    if b - a < 0.6:
        return
    if width and b - a > width:
        m = (a + b) / 2
        a, b = m - width / 2, m + width / 2
    f.openings.append(hl.Opening(kind, axis, coord, a, b, z0, z1, (room,)))


# --------------------------------------------------------------------------
# Turning the finished plan (rooms, openings and boxes together)
# --------------------------------------------------------------------------

def _side_balcony_doors(u, Wd, per_side=2, slab_out=0.35):
    """Modern villa: on each side wall upstairs (the engine's X walls at y = 0 and y = Wd), the two
    widest bedroom / study windows become floor-length French doors onto a small balcony
    (villa_dress builds the balconies), kept apart so the balconies don't touch."""
    rooms = ("master", "bedroom", "study")
    for coord in (0.0, Wd):
        cands = sorted((o for o in u.openings if o.kind == "WINDOW" and o.axis == "X" and abs(o.coord - coord) < 1e-3
                        and u.room(o.rooms[0]).kind in rooms), key=lambda o: o.s0 - o.s1)
        picked = []
        for o in cands:
            if len(picked) == per_side:
                break
            if all(o.s1 + slab_out + 1.0 < q.s0 - slab_out or q.s1 + slab_out + 1.0 < o.s0 - slab_out for q in picked):
                picked.append(o)
        for o in picked:
            o.kind, o.z0, o.z1 = "PATIO", 0.0, 2.3


def _transpose(plan):
    """Swap X and Y."""
    def sw(b):
        return (b[1], b[0], b[2], b[4], b[3], b[5])

    plan.W, plan.D = plan.D, plan.W
    for f in plan.floors:
        for r in f.rooms:
            r.x0, r.y0, r.x1, r.y1 = r.y0, r.x0, r.y1, r.x1
        for o in f.openings:
            o.axis = "Y" if o.axis == "X" else "X"
        f.walls, f.stair, f.rails = [sw(b) for b in f.walls], [sw(b) for b in f.stair], [sw(b) for b in f.rails]
        f.srails = [tuple((p[1], p[0], p[2]) for p in pair) for pair in f.srails]
        f.fence = [(role, [(p[1], p[0], p[2]) for p in pts]) for role, pts in f.fence]


def _mirror(plan, axis):
    """Flip along 'X' (x -> W - x) or 'Y' (y -> D - y)."""
    span = plan.W if axis == "X" else plan.D

    def mb(b):
        if axis == "X":
            return (span - b[3], b[1], b[2], span - b[0], b[4], b[5])
        return (b[0], span - b[4], b[2], b[3], span - b[1], b[5])

    for f in plan.floors:
        for r in f.rooms:
            if axis == "X":
                r.x0, r.x1 = span - r.x1, span - r.x0
            else:
                r.y0, r.y1 = span - r.y1, span - r.y0
        for o in f.openings:
            if o.axis == axis:      # runs along the flipped axis: its span flips
                o.s0, o.s1 = span - o.s1, span - o.s0
            else:
                o.coord = span - o.coord
        f.walls, f.stair, f.rails = [mb(b) for b in f.walls], [mb(b) for b in f.stair], [mb(b) for b in f.rails]
        f.srails = [tuple(((span - p[0], p[1], p[2]) if axis == "X" else (p[0], span - p[1], p[2])) for p in pair)
                    for pair in f.srails]
        f.fence = [(role, [(span - p[0], p[1], p[2]) if axis == "X" else (p[0], span - p[1], p[2]) for p in pts])
                   for role, pts in f.fence]


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def make_villa_plan(style="MODERN", area=240.0, bedrooms=4, bathrooms=3, seed=0,
                    ceiling_h=2.7, slab=0.2, t_ext=0.25, t_int=0.1, pitch=42.0, knee=1.2):
    saved = hl.MAX_AREA
    hl.MAX_AREA = MAX_AREA
    try:
        if style == "MEDITERRANEAN":        # its own plan (villa_med_layout), on this module's helpers
            try:
                from . import villa_med_layout as med
            except ImportError:
                import villa_med_layout as med
            return med.make(area, bedrooms, bathrooms, seed, ceiling_h, slab, t_ext, t_int)
        return _make(style, area, bedrooms, bathrooms, seed, ceiling_h, slab, t_ext, t_int, pitch, knee)
    finally:
        hl.MAX_AREA = saved


def _make(style, area, bedrooms, bathrooms, seed, ceiling_h, slab, t_ext, t_int, pitch, knee):
    modern = style == "MODERN"
    rng = random.Random(seed * 31 + (3 if modern else 7))
    bedrooms, bathrooms = max(1, int(bedrooms)), max(0, int(bathrooms))
    plan = hl.Plan()
    plan.ceiling_h, plan.slab, plan.t_ext, plan.t_int = ceiling_h, slab, t_ext, t_int
    H = ceiling_h
    if area < MIN_AREA[style]:
        plan.warnings.append(f"This villa needs about {MIN_AREA[style]:.0f} m2 or more; built at its smallest size")
        area = MIN_AREA[style]

    # Footprint: L from back to front, Wd across. The carport / terrace and the
    # balcony are open air, so the footprint is that much bigger than the rooms.
    if modern:
        bd, dS, cd = 1.6, 5.2, 5.6                      # balcony depth; carport across x deep
        cut = dS * cd + (dS + CORRIDOR_W) * bd
        Wd = hl._snap(min(max(math.sqrt((area + cut) / 2 / 1.35), 10.0), 13.0))
        L = hl._snap(max((area + cut) / 2 / Wd, 11.2))
    else:
        bd, td = 1.8, 2.8                               # balcony depth; terrace depth
        Wd = hl._snap(min(max(math.sqrt((area + 26.0) / 2 / 1.2), 9.0), 11.6))
        dS = hl._snap((Wd - CORRIDOR_W) / 2)
        cut = (td + bd) * (dS + CORRIDOR_W)
        L = hl._snap(max((area + cut) / 2 / Wd, 10.2))
    yc0, yc1 = dS, dS + CORRIDOR_W
    plan.W, plan.D = L, Wd                              # the engine's frame until we turn it

    if modern:
        xp = hl._snap(min(max(0.33 * L, 3.8), L - cd - 1.6))
    else:
        xp = hl._snap(min(max(0.48 * L, 4.6), L - 5.5))
    xs = xp + STAIR_LEN                                 # stairs: north row, right after the public zone

    def stairwell(fl):
        fl.rooms.append(hl.Room("Stairs", "stair", xp, yc1, xs, Wd))
        fl.open_pairs.add(frozenset(("Stairs", HALL)))

    # ---- Ground floor -----------------------------------------------------
    g = hl.Floor(0)
    plan.floors.append(g)
    g.entrance_room = None
    g.rooms.append(hl.Room(HALL, "corridor", xp, yc0, L, yc1))
    stairwell(g)
    if modern:
        g.rooms.append(hl.Room("Kitchen / Dining", "living", 0.0, 0.0, xp, Wd))
        g.rooms.append(hl.Room("Living Room", "living", xs, yc1, L, Wd))
        g.rooms.append(hl.Room("Carport", "carport", L - cd, 0.0, L, dS))
        g.open_pairs.update((frozenset(("Kitchen / Dining", HALL)), frozenset(("Living Room", HALL))))
        # Beside the carport: a WC off the hallway, and behind it a store reached from the carport
        q = L - cd - xp
        sw = q if q < 3.4 else 1.6
        g.rooms.append(hl.Room("WC", "wc", L - cd - sw, dS - 2.2, L - cd, dS))
        g.rooms.append(hl.Room("Garage Store", "storage", L - cd - sw, 0.0, L - cd, dS - 2.2))
        g.connections += [("WC", HALL, "DOOR"), ("Garage Store", "Carport", "DOOR")]
        rest = _Seg(xp, L - cd - sw, 0.0, dS)
        if rest.length >= 1.8:
            if rest.length < 2.4:
                rest.items = [("Laundry", "storage")]
            elif rest.length < 4.6:
                rest.items = [("Study", "study")]
            else:
                rest.items = [("Laundry", "storage"), ("Study", "study")]
                if rest.length >= 7.5:
                    rest.items.append(("Guest Room", "bedroom"))
            _place(rng, plan, g, rest)
        front_ground = "Living Room"
    else:
        g.rooms.append(hl.Room("Terrace", "terrace", 0.0, 0.0, td, yc1))
        g.rooms.append(hl.Room("Kitchen / Dining", "kitchen", td, 0.0, xp, yc1))
        g.rooms.append(hl.Room("Living Room", "living", 0.0, yc1, xp, Wd))
        g.open_pairs.update((frozenset(("Kitchen / Dining", HALL)), frozenset(("Kitchen / Dining", "Living Room"))))
        south = _Seg(xp, L, 0.0, dS, pinned=[("Office", "study")])
        south.items = [("Utility", "storage"), ("WC", "wc")]
        if south.length >= 8.0:
            south.items.append(("Guest Room", "bedroom"))
        north = _Seg(xs, L, yc1, Wd, pinned=[("Study", "study")])
        if north.length >= 5.4:
            north.items.append(("Play Room", "study"))
        _place(rng, plan, g, south)
        _place(rng, plan, g, north)
        front_ground = "Study"

    # ---- Upper floor ------------------------------------------------------
    u = hl.Floor(1)
    plan.floors.append(u)
    u.entrance_room = None
    u.rooms.append(hl.Room(HALL, "corridor", 0.0, yc0, L - bd, yc1))
    stairwell(u)
    u.rooms.append(hl.Room("Balcony", "balcony", L - bd, 0.0, L, yc1))
    front_upper = ("Bedroom 2", "bedroom") if bedrooms >= 2 else ("Lounge", "study")
    suite = ([("Ensuite", "bathroom")] if bathrooms >= 2 else []) + [("Master Bedroom", "master")]
    south = _Seg(0.0, L - bd, 0.0, dS, pinned=suite)
    n_back = _Seg(0.0, xp, yc1, Wd)
    n_front = _Seg(xs, L, yc1, Wd, pinned=[front_upper])
    # The front room needs a stretch of hallway for its door, so it shares its segment sparingly
    n_front.limit = 0 if n_front.length < 6.2 else 1 if n_front.length < 9.5 else 2
    shared = bathrooms - 1 if bathrooms >= 2 else bathrooms
    others = [(f"Bedroom {i}", "bedroom") for i in range(3, bedrooms + 1)]
    others += [("Bathroom" if shared == 1 else f"Bathroom {i + 1}", "bathroom") for i in range(shared)]
    segs = [south, n_back, n_front]
    _assign(rng, others, segs)
    _fill_spare(segs, ["Study", "Guest Room", "Office", "Hobby Room"], ["Dressing", "Linen", "Storage", "Closet"])
    for s in segs:
        _place(rng, plan, u, s, no_door=("Ensuite",))
    if bathrooms >= 2:
        u.connections.append(("Ensuite", "Master Bedroom", "DOOR"))

    tn = math.tan(math.radians(pitch))
    if not modern:
        u.wall_h = knee + (Wd / 2) * tn + 0.3           # walls run up to the roof, which trims them
        u.light_h = min(H, 2.5)

    # ---- Doors, windows, walls, stairs (still in the engine's frame) --------
    for f in plan.floors:
        f.base_z = f.index * plan.storey_h
        hl._place_openings(rng, plan, f)

    # Front door at the end of the hallway
    _clear(g, "Y", L, yc0, yc1)
    mid = (yc0 + yc1) / 2
    g.openings.append(hl.Opening("ENTRANCE", "Y", L, mid - 0.5, mid + 0.5, 0.0, 2.2, (HALL,)))

    top = u.wall_h or H                                 # glazing under the gable runs up to the roof
    if modern:
        _glaze(g, "Living Room", "Y", L, yc1, Wd, 0.0, H - 0.25, "WINDOW", width=2.6, pad=0.5)
        _glaze(u, front_upper[0], "Y", L, yc1, Wd, 0.0, H - 0.25, "WINDOW", width=2.6, pad=0.5)
        _glaze(u, "Master Bedroom", "Y", L - bd, 0.0, yc0, 0.0, 2.3, width=3.4, pad=0.5)
        _glaze(u, HALL, "Y", L - bd, yc0, yc1, 0.0, 2.3, pad=0.2)
    else:
        _glaze(g, "Kitchen / Dining", "Y", td, 0.0, yc1, 0.0, 2.2, width=3.2, pad=0.5)
        _glaze(g, "Living Room", "X", yc1, 0.0, td, 0.0, 2.2, width=2.0, pad=0.4)
        _glaze(u, "Master Bedroom", "Y", L - bd, 0.0, yc0, 0.0, top, pad=0.5)
        _glaze(u, HALL, "Y", L - bd, yc0, yc1, 0.0, top, pad=0.2)
        # No windows in the knee walls (the roof gets skylights instead), and the
        # ones in the gable ends keep clear of the roof slopes.
        _clear(u, "X", 0.0, 0.0, L)
        _clear(u, "X", Wd, 0.0, L)
        _clear(u, "Y", L, yc1, Wd)
        m = (2.5 + 0.25 - knee) / tn
        if Wd - m - (yc1 + 0.4) >= 0.8:
            u.openings.append(hl.Opening("WINDOW", "Y", L, yc1 + 0.4, min(Wd - m, yc1 + 3.0), 0.0, 2.5, (front_upper[0],)))
        keep = []
        for o in u.openings:
            if o.kind == "WINDOW" and o.axis == "Y" and abs(o.coord) < 1e-4:
                r = u.room(o.rooms[0])
                m = (o.z1 + 0.25 - knee) / tn
                lo, hi = max(r.y0 + 0.3, m), min(r.y1 - 0.3, Wd - m)
                if hi - lo < 0.6:
                    continue
                w = min(o.s1 - o.s0, hi - lo)
                c = min(max((o.s0 + o.s1) / 2, lo + w / 2), hi - w / 2)
                o.s0, o.s1 = c - w / 2, c + w / 2
            keep.append(o)
        u.openings = keep

    if modern:
        _side_balcony_doors(u, Wd)
    for f in plan.floors:
        hl._build_walls(plan, f)
    hl._build_stair(rng, plan, g, u, style="VILLA")

    # ---- Turn it so the front faces the street (y = 0) ----------------------
    _transpose(plan)
    _mirror(plan, "Y")
    if rng.random() < 0.5:
        _mirror(plan, "X")
    W, te = plan.W, plan.t_ext

    # Facade zones in a second material: the flush front bay (stone / timber),
    # and the wall set back behind the balcony.
    bay = u.room(front_upper[0])
    bal = u.room("Balcony")
    front = (bay.x0 - te, -te, bay.x1 + te, te, "accent")
    g.accents.append(front)
    u.accents.append(front)
    u.accents.append((bal.x0 - te, bal.y1 - te, bal.x1 + te, bal.y1 + te, "accent" if not modern else "recess"))
    stone_corner = None
    if modern:          # the walls round the carport: dark timber slats
        cp = next(r for r in g.rooms if r.kind == "carport")
        g.accents.append((cp.x0, cp.y0 - 1.0, cp.x1, cp.y1, "carport_wall"))
        # The back corner away from the garden doors: the bay's stone, from its last window round
        # onto the side wall
        Dp = plan.D
        back = [o for o in g.openings if o.axis == "X" and abs(o.coord - Dp) < 0.05]
        doors = [(o.s0 + o.s1) / 2 for o in back if o.kind == "PATIO"]
        east = (sum(doors) / len(doors) if doors else W / 2) <= W / 2
        if east:
            a = max([o.s1 for o in back] + [W - 1.4])
            g.accents.append((a + 0.01, Dp - 1.4, W + te + 0.1, Dp + te + 0.1, "accent"))
            stone_corner = (a, W + te / 2)
        else:
            b = min([o.s0 for o in back] + [1.4])
            g.accents.append((-te - 0.1, Dp - 1.4, b - 0.01, Dp + te + 0.1, "accent"))
            stone_corner = (-te / 2, b)
    else:               # the gable villa's ground floor: dark stacked stone wherever the timber bay isn't
        g.accents.append((-te - 1.0, -te - 1.0, W + te + 1.0, plan.D + te + 1.0, "base_stone"))

    ridge_z = None
    if not modern:
        ridge_z = knee + (W / 2) * tn                   # roof underside at the ridge, above the upper floor
        s, c = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
        plan.clip[1] = [((W / 2, 0.0, ridge_z), (s, 0.0, c)), ((W / 2, 0.0, ridge_z), (-s, 0.0, c))]

    plan.villa = {
        "style": style, "pitch": pitch, "knee": knee, "ridge_z": ridge_z,
        "bay": front_upper[0], "bay_ground": front_ground, "stone_corner": stone_corner,
    }
    return plan
