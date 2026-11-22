"""Random house floor plans. Pure Python (no Blender) so it can be tested alone.

Coordinates are metres on wall centrelines: origin at the south-west corner,
X along the footprint's width, Y along its depth. Every floor is a set of
rectangles (rooms) that tile the footprint exactly; walls, doors and windows
are then derived from the edges the rooms share (see house_walls).

The layout is a "double-loaded corridor": a public zone (open space) at one
end, and a private zone where a corridor runs through the middle with a row of
rooms on each side, so every room gets a corridor door and an outside wall
for windows. Upper floors are all private, and a two-flight stairwell sits in
the same spot on every floor.

    +-----------+--------+------+--------+
    |           | Stairs | Bath | Bed 2  |   north row
    |  Living / +--------+------+--------+
    |  Kitchen     corridor              |
    |           +-----------+------------+
    |           | Bedroom 3 | Bathroom   |   south row
    +-----------+-----------+------------+
       public          private zone
"""

import math
import random

try:
    from .house_walls import OUTDOOR, shared_edge, opening_box, _build_walls, _build_stair
except ImportError:  # run as a plain script, outside the addon package
    from house_walls import OUTDOOR, shared_edge, opening_box, _build_walls, _build_stair

EPS = 1e-6
SNAP = 0.05

# Target areas (m2) and minimum widths (m) per kind of room.
TARGET_AREA = {
    "master": 14.0, "bedroom": 11.0, "bathroom": 5.0, "wc": 2.6,
    "study": 9.0, "storage": 3.0, "stair": 0.0,
}
MIN_WIDTH = {
    "master": 3.0, "bedroom": 2.7, "bathroom": 1.7, "wc": 1.1,
    "study": 2.4, "storage": 1.0, "stair": 0.0,
}

CORRIDOR_W = 1.2
# Deepest footprint (m). Rooms take the full depth of their row, so a deep house
# gives long, narrow bathrooms (10.5 m deep -> ~1.8 x 4.5 m). Scripts can lower it
# (8.0 keeps rows ~3.4 m deep and bathrooms ~5-6 m2); houses then get wider instead.
MAX_DEPTH = 10.5
# Optional caps (m2) per kind of room, e.g. {"bathroom": 6.5, "wc": 3.0}. Empty = no caps
# (the old behaviour: spare row length is shared by weight, so bathrooms can get big).
MAX_AREA = {}
STAIR_LEN = 2.5        # stairwell length along the corridor (two flights side by side)
MIN_PUBLIC_W = 3.6     # narrowest the open space may get
MIN_OPEN_AREA = 18.0

# Opening sizes: (width, height, sill)
DOOR_W = {"bathroom": 0.75, "wc": 0.7, "storage": 0.7}
DOOR_W_DEFAULT = 0.85
DOOR_H = 2.1
ENTRANCE = (1.0, 2.2, 0.0)
ARCH = (1.4, 2.2, 0.0)
WINDOWS = {
    "master": (1.4, 1.3, 0.9),
    "bedroom": (1.4, 1.3, 0.9),
    "study": (1.2, 1.3, 0.9),
    "bathroom": (0.6, 0.6, 1.5),
    "wc": (0.5, 0.5, 1.5),
    "kitchen": (1.2, 1.0, 1.1),
    "living": (1.6, 1.4, 0.8),
    "corridor": (0.8, 1.2, 0.9),
}
PATIO = (2.4, 2.2, 0.0)


def _snap(v, step=SNAP):
    return round(v / step) * step


class Room:
    def __init__(self, name, kind, x0, y0, x1, y1):
        self.name, self.kind = name, kind
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    @property
    def area(self):
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    @property
    def center(self):
        return ((self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2)

    def __repr__(self):
        return f"<{self.name} {self.x1 - self.x0:.2f}x{self.y1 - self.y0:.2f}={self.area:.1f}m2>"


class Opening:
    """A hole in a wall. axis 'X' = wall runs along X at y=coord; 'Y' = along Y at x=coord."""

    def __init__(self, kind, axis, coord, s0, s1, z0, z1, rooms=(), leaf=True):
        self.kind = kind              # DOOR, ENTRANCE, ARCH, WINDOW, PATIO
        self.axis, self.coord = axis, coord
        self.s0, self.s1, self.z0, self.z1 = s0, s1, z0, z1
        self.rooms = rooms
        self.leaf = leaf              # gets a door leaf / glass pane
        self.exterior = False
        self.thickness = 0.0


class Floor:
    def __init__(self, index):
        self.index = index
        self.rooms = []
        self.open_pairs = set()       # frozenset({name_a, name_b}) with no wall between
        self.connections = []         # (name_a, name_b, kind)
        self.openings = []
        self.walls = []               # boxes (x0, y0, z0, x1, y1, z1), floor-local z
        self.stair = []               # boxes, floor-local z
        self.rails = []               # boxes, floor-local z
        self.srails = []              # sloped stair rails: ((x, y, z) low end, (x, y, z) high end), floor-local
        self.fence = []               # villa stair fence: (role, 8 corner points), floor-local (see villa_stair)
        self.base_z = 0.0
        self.wall_h = None            # wall height if not the plan's ceiling height (attic storeys)
        self.light_h = None           # ceiling-light height, same idea
        self.accents = []             # (x0, y0, x1, y1, role): facade zones in another material

    def room(self, name):
        return next(r for r in self.rooms if r.name == name)

    @property
    def label(self):
        return "GF" if self.index == 0 else f"F{self.index}"


class Plan:
    def __init__(self):
        self.W = self.D = 0.0
        self.floors = []
        self.warnings = []
        self.ceiling_h = 2.7
        self.slab = 0.2
        self.t_ext = 0.25
        self.t_int = 0.1
        self.clip = {}                # floor index -> [((x, y, z), (nx, ny, nz))]: roof planes that
                                      # trim that floor's walls (z from the floor, normals point out)
        self.villa = None             # villa_layout's notes for the exterior, None for plain houses

    @property
    def storey_h(self):
        return self.ceiling_h + self.slab

    def summary(self):
        lines = [f"{self.W:.2f} x {self.D:.2f} m, {len(self.floors)} floor(s), "
                 f"{self.W * self.D * len(self.floors):.0f} m2"]
        for f in self.floors:
            rooms = ", ".join(f"{r.name} {r.area:.1f}" for r in f.rooms)
            lines.append(f"  {f.label}: {rooms}")
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Room program
# --------------------------------------------------------------------------

def _program(floors, bedrooms, bathrooms):
    """Which private rooms go on which floor: (ground_list, [upper_lists])."""
    beds = []
    if bedrooms >= 1:
        beds.append(("Master Bedroom", "master"))
    beds += [(f"Bedroom {i}", "bedroom") for i in range(2, bedrooms + 1)]
    baths = [("Bathroom" if bathrooms == 1 else f"Bathroom {i + 1}", "bathroom") for i in range(bathrooms)]

    if floors == 1:
        return beds + baths, []

    n_up = floors - 1
    g_baths = baths[: bathrooms // 2]
    u_items = sorted(beds + baths[bathrooms // 2:], key=lambda r: -TARGET_AREA[r[1]])
    uppers = [[] for _ in range(n_up)]
    for item in u_items:  # balance the upper floors by area
        min(uppers, key=lambda lst: sum(TARGET_AREA[k] for _, k in lst)).append(item)
    ground = list(g_baths)
    if not ground:
        ground.append(("WC", "wc"))  # a multi-storey house always gets a ground-floor toilet
    return ground, uppers


# --------------------------------------------------------------------------
# Private zone (corridor + two rows of rooms, optional end room)
# --------------------------------------------------------------------------

def _distribute(length, kinds, weights, depth=None):
    """Split `length` into widths proportional to `weights`, honouring minimum widths
    (and, with MAX_AREA and the row `depth`, maximum widths: spare length goes to the
    rooms that aren't capped)."""
    mins = [MIN_WIDTH[k] for k in kinds]
    n = len(kinds)
    if sum(mins) > length + EPS:
        tot = sum(mins) or 1.0
        return [length * m / tot for m in mins]
    maxs = [max(mins[i], MAX_AREA[k] / depth) if (depth and k in MAX_AREA) else float("inf")
            for i, k in enumerate(kinds)]
    if sum(maxs) < length - EPS:          # every room capped and still too short: drop the caps
        maxs = [float("inf")] * n
    widths = [0.0] * n
    fixed = [False] * n
    while True:
        free_len = length - sum(widths[i] for i in range(n) if fixed[i])
        free_w = sum(weights[i] for i in range(n) if not fixed[i]) or 1.0
        changed = False
        for i in range(n):
            if not fixed[i]:
                widths[i] = free_len * weights[i] / free_w
        for i in range(n):
            if not fixed[i] and widths[i] < mins[i] - EPS:
                widths[i] = mins[i]
                fixed[i] = True
                changed = True
            elif not fixed[i] and widths[i] > maxs[i] + EPS:
                widths[i] = maxs[i]
                fixed[i] = True
                changed = True
        if not changed:
            return widths


def _min_two_rows(widths, extra):
    """Shortest zone length that fits these minimum widths split over two rows.

    `extra` is a fixed item (the stairwell) that must sit in one of the rows.
    Brute force: room counts are tiny.
    """
    widths = list(widths)[:14]
    best = float("inf")
    for mask in range(1 << len(widths)):
        a = sum(w for i, w in enumerate(widths) if mask >> i & 1) + extra
        b = sum(w for i, w in enumerate(widths) if not mask >> i & 1)
        best = min(best, max(a, b))
    return best if widths or extra else 0.0


class _Seg:
    def __init__(self, a, b, y0, y1):
        self.a, self.b, self.y0, self.y1 = a, b, y0, y1
        self.items = []

    @property
    def length(self):
        return self.b - self.a

    @property
    def cap(self):
        return self.length * (self.y1 - self.y0)

    def used(self):
        return sum(TARGET_AREA[k] for _, k in self.items)

    def min_len(self, extra=None):
        ks = [k for _, k in self.items] + ([extra] if extra else [])
        return sum(MIN_WIDTH[k] for k in ks)


def _layout_private(rng, fl, plan, rooms, xp0, xp1, rows, corridor_y, stair, allow_cap, fillers):
    """Lay out one floor's private zone into `fl`.

    rows: {'S': (y0, y1), 'N': (y0, y1)}; stair: (x0, x1, row) or None.
    """
    D = plan.D
    yc0, yc1 = corridor_y
    rooms = list(rooms)
    corridor_name = "Hallway"

    # Optional end room: the master spans the full depth at the far end,
    # with an ensuite bathroom tucked into one corner when there's a spare bath.
    cap = None
    master = next((r for r in rooms if r[1] == "master"), None)
    baths = [r for r in rooms if r[1] == "bathroom"]
    if allow_cap and master and len(rooms) >= 3 and rng.random() < 0.55:
        ensuite = baths[-1] if len(baths) >= 2 else None
        if ensuite or D <= 7.6:
            capw = _snap(min(max((14.0 + (5.0 if ensuite else 0.0)) * 1.1 / D, 3.0), 4.2))
            start = stair[1] if stair else xp0
            rest = [k for n, k in rooms if n != master[0] and (not ensuite or n != ensuite[0])]
            fits = _min_two_rows([MIN_WIDTH[k] for k in rest], STAIR_LEN if stair else 0.0)
            if xp1 - capw >= start + 2.6 and xp1 - capw - xp0 >= fits + 0.2:
                cap = (capw, master, ensuite)
                rooms.remove(master)
                if ensuite:
                    rooms.remove(ensuite)

    xc_end = xp1 - (cap[0] if cap else 0.0)

    # Segments along each row (the stairwell interrupts its row).
    segs = []
    for row in ("S", "N"):
        y0, y1 = rows[row]
        pieces = [(xp0, xc_end)]
        if stair and stair[2] == row:
            pieces = [(xp0, stair[0]), (stair[1], xc_end)]
        for a, b in pieces:
            if b - a > 0.6:
                segs.append(_Seg(a, b, y0, y1))

    # Biggest rooms first, each into the segment with the most room left.
    # Retry with fresh randomness until every segment fits its rooms' minimum widths.
    best = None
    for attempt in range(40):
        for s in segs:
            s.items = []
        order = sorted(rooms, key=lambda r: -TARGET_AREA[r[1]] * rng.uniform(0.9, 1.1))
        jitter = 0.15 + 0.02 * attempt
        for item in order:
            def score(s):
                fits = s.min_len(item[1]) <= s.length + EPS
                return (s.cap - s.used()) * rng.uniform(1 - jitter, 1 + jitter) + (0 if fits else -1e4)
            max(segs, key=score).items.append(item)
        over = sum(max(0.0, s.min_len() - s.length) for s in segs)
        if best is None or over < best[0]:
            best = (over, [list(s.items) for s in segs])
        if over <= EPS:
            break
    for s, items in zip(segs, best[1]):
        s.items = items

    # Fill empty segments, and (on a multi-storey ground floor) big leftovers.
    spare_names = iter(["Study", "Guest Room", "Office", "Hobby Room"])
    store_names = iter(["Storage", "Laundry", "Pantry", "Closet"])
    for s in segs:
        free = s.cap - s.used()
        if not s.items:
            if s.cap >= 7.0 and s.length >= MIN_WIDTH["study"]:
                s.items.append((next(spare_names, "Study"), "study"))
            else:
                s.items.append((next(store_names, "Storage"), "storage"))
        elif fillers and free >= 8.0 and s.min_len("study") <= s.length:
            s.items.append((next(spare_names, "Study"), "study"))
        elif fillers and free >= 3.5 and s.min_len("storage") <= s.length:
            s.items.append((next(store_names, "Storage"), "storage"))

    for s in segs:
        depth = s.y1 - s.y0
        if MAX_AREA and s.items and all(k in MAX_AREA for _, k in s.items):
            room_left = s.length - sum(max(MIN_WIDTH[k], MAX_AREA[k] / depth) for _, k in s.items)
            if room_left >= MIN_WIDTH["storage"]:      # only capped rooms here: a closet takes the rest
                s.items.append((next(store_names, "Storage"), "storage"))
        rng.shuffle(s.items)
        kinds = [k for _, k in s.items]
        widths = _distribute(s.length, kinds, [TARGET_AREA[k] for k in kinds], depth if MAX_AREA else None)
        x = s.a
        for i, ((name, kind), w) in enumerate(zip(s.items, widths)):
            x1 = s.b if i == len(widths) - 1 else _snap(x + w)
            fl.rooms.append(Room(name, kind, x, s.y0, x1, s.y1))
            fl.connections.append((name, corridor_name, "DOOR"))
            x = x1
        if s.min_len() > s.length + EPS:
            plan.warnings.append(f"{fl.label}: rooms squeezed below comfortable width")

    fl.rooms.append(Room(corridor_name, "corridor", xp0, yc0, xc_end, yc1))

    if stair:
        sx0, sx1, row = stair
        y0, y1 = rows[row]
        fl.rooms.append(Room("Stairs", "stair", sx0, y0, sx1, y1))
        fl.open_pairs.add(frozenset(("Stairs", corridor_name)))

    if cap:
        capw, (mname, mkind), ensuite = cap
        if ensuite:
            bd = _snap(min(max(5.5 / capw, 1.8), 2.6))
            if rng.random() < 0.5 and bd <= yc0 - 0.3:       # ensuite on the south side
                fl.rooms.append(Room(ensuite[0], "bathroom", xc_end, 0.0, xp1, bd))
                fl.rooms.append(Room(mname, mkind, xc_end, bd, xp1, D))
            elif D - bd >= yc1 + 0.3:                       # or the north side
                fl.rooms.append(Room(ensuite[0], "bathroom", xc_end, D - bd, xp1, D))
                fl.rooms.append(Room(mname, mkind, xc_end, 0.0, xp1, D - bd))
            else:
                fl.rooms.append(Room(ensuite[0], "bathroom", xc_end, 0.0, xp1, bd))
                fl.rooms.append(Room(mname, mkind, xc_end, bd, xp1, D))
            fl.connections.append((ensuite[0], mname, "DOOR"))
        else:
            fl.rooms.append(Room(mname, mkind, xc_end, 0.0, xp1, D))
        fl.connections.append((mname, corridor_name, "DOOR"))
    return corridor_name


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

def make_plan(area=100.0, floors=1, bedrooms=3, bathrooms=2, open_plan=True, seed=0,
              ceiling_h=2.7, slab=0.2, t_ext=0.25, t_int=0.1):
    rng = random.Random(seed)
    floors = max(1, int(floors))
    bedrooms = max(0, int(bedrooms))
    bathrooms = max(0, int(bathrooms))
    plan = Plan()
    plan.ceiling_h, plan.slab, plan.t_ext, plan.t_int = ceiling_h, slab, t_ext, t_int
    multi = floors > 1

    # Footprint
    A = area / floors
    aspect = rng.uniform(1.3, 1.7)
    D = math.sqrt(A / aspect)
    if A >= 40:
        D = min(max(D, 6.4), max(MAX_DEPTH, 6.4))
    D = _snap(D)
    W = _snap(A / D)
    plan.W, plan.D = W, D

    ground_rooms, upper_rooms = _program(floors, bedrooms, bathrooms)

    # Push bedrooms down if an upper floor can't physically fit them.
    for ups in upper_rooms:
        while ups and sum(MIN_WIDTH[k] for _, k in ups) > 2 * W - STAIR_LEN - 1.0:
            beds = [r for r in ups if r[1] in ("bedroom", "master")]
            if not beds:
                break
            ups.remove(beds[-1])
            ground_rooms.append(beds[-1])
            plan.warnings.append(f"{beds[-1][0]} moved to the ground floor (didn't fit upstairs)")

    # Rows either side of the corridor
    rows_total = D - CORRIDOR_W
    dS = _snap(rows_total * rng.uniform(0.42, 0.58))
    if multi:  # keep one row deep enough for comfortable stairs
        need = min(3.4, rows_total - 2.5)
        if max(dS, rows_total - dS) < need:
            dS = _snap(need) if dS >= rows_total - dS else _snap(rows_total - need)
    dN = rows_total - dS
    yc0, yc1 = dS, dS + CORRIDOR_W
    rows = {"S": (0.0, yc0), "N": (yc1, D)}
    stair_row = "N" if dN >= dS else "S"
    stair_depth = max(dN, dS)

    # How wide the private zone on the ground floor needs to be
    g_target = sum(TARGET_AREA[k] for _, k in ground_rooms)
    stair_area = STAIR_LEN * stair_depth if multi else 0.0
    P_need = (g_target + stair_area) / rows_total
    P_need = max(P_need, _min_two_rows([MIN_WIDTH[k] for _, k in ground_rooms],
                                       STAIR_LEN if multi else 0.0) + 0.3)
    if multi:
        P_need = max(P_need, STAIR_LEN)
        Wpub = rng.uniform(0.45, 0.58) * A / D            # main living floor
        Wpub = min(Wpub, W - P_need)
    else:
        Wpub = W - P_need
        Wpub = min(Wpub, rng.uniform(0.36, 0.46) * A / D)  # don't let the open space swallow the house
    need_pub = MIN_OPEN_AREA + (0.0 if open_plan else 9.0)
    Wpub = max(Wpub, MIN_PUBLIC_W, need_pub / D)
    max_pub = W - (STAIR_LEN if multi else 2.0)
    if Wpub > max_pub:
        Wpub = max_pub
        plan.warnings.append("House is very small for this room count; everything is tight")
    Wpub = _snap(Wpub)
    if multi and 0 < (W - Wpub) - STAIR_LEN < 1.2:
        Wpub = _snap(W - STAIR_LEN)   # no sliver room beside the stairwell
    if W - Wpub < P_need - 0.5:
        plan.warnings.append("Not enough area for the requested rooms; they are smaller than typical")

    stair = (Wpub, Wpub + STAIR_LEN, stair_row) if multi else None

    # Ground floor
    g = Floor(0)
    plan.floors.append(g)
    corr = _layout_private(rng, g, plan, ground_rooms, Wpub, W, rows, (yc0, yc1), stair,
                           allow_cap=True, fillers=multi)
    if open_plan:
        g.rooms.append(Room("Living / Kitchen", "living", 0.0, 0.0, Wpub, D))
        living = "Living / Kitchen"
    else:
        kd = _snap(min(max(10.0 / Wpub, 2.4), 4.0, yc0))
        g.rooms.append(Room("Kitchen", "kitchen", 0.0, 0.0, Wpub, kd))
        g.rooms.append(Room("Living Room", "living", 0.0, kd, Wpub, D))
        living = "Living Room"
        g.connections.append(("Kitchen", living, "ARCH"))
    g.open_pairs.add(frozenset((living, corr)))
    g.entrance_room = living

    # Upper floors
    for i, ups in enumerate(upper_rooms, start=1):
        f = Floor(i)
        plan.floors.append(f)
        _layout_private(rng, f, plan, ups, 0.0, W, rows, (yc0, yc1), stair,
                        allow_cap=True, fillers=False)
        f.entrance_room = None

    # Random mirroring for variety
    mx, my = rng.random() < 0.5, rng.random() < 0.5
    for f in plan.floors:
        for r in f.rooms:
            if mx:
                r.x0, r.x1 = W - r.x1, W - r.x0
            if my:
                r.y0, r.y1 = D - r.y1, D - r.y0

    for f in plan.floors:
        f.base_z = f.index * plan.storey_h
        _place_openings(rng, plan, f)
        _build_walls(plan, f)
    for f in plan.floors[:-1]:
        _build_stair(rng, plan, f, plan.floors[f.index + 1])
    return plan


# --------------------------------------------------------------------------
# Doors and windows
# --------------------------------------------------------------------------

def _exterior_edges(plan, r):
    W, D = plan.W, plan.D
    edges = []
    if r.y0 < 1e-4:
        edges.append(("X", 0.0, r.x0, r.x1))
    if r.y1 > D - 1e-4:
        edges.append(("X", D, r.x0, r.x1))
    if r.x0 < 1e-4:
        edges.append(("Y", 0.0, r.y0, r.y1))
    if r.x1 > W - 1e-4:
        edges.append(("Y", W, r.y0, r.y1))
    return edges


def _margins(plan, axis, s0, s1, extra):
    """Clearance needed at each end of an edge so openings keep off adjoining walls."""
    span = plan.W if axis == "X" else plan.D
    m0 = (plan.t_ext if s0 < 1e-4 else plan.t_int) / 2 + extra
    m1 = (plan.t_ext if s1 > span - 1e-4 else plan.t_int) / 2 + extra
    return s0 + m0, s1 - m1


def _place_door(rng, plan, edge, width, extra=0.08, where=None):
    axis, coord, s0, s1 = edge
    a, b = _margins(plan, axis, s0, s1, extra)
    if b - a < 0.6:
        return None
    w = min(width, b - a)
    where = where or rng.choices(("start", "end", "mid"), (0.4, 0.4, 0.2))[0]
    if where == "start":
        p = a
    elif where == "end":
        p = b - w
    elif where == "rand":
        p = rng.uniform(a, b - w)
    else:
        p = (a + b - w) / 2
    return (p, p + w)


def _spread(intervals, n, w):
    """Place `n` openings of width `w` evenly over free intervals -> [(s0, s1)]."""
    out = []
    intervals = [iv for iv in intervals if iv[1] - iv[0] > 0.5]
    total = sum(b - a for a, b in intervals)
    if n <= 0 or total <= 0:
        return out
    counts = [max(0, round(n * (b - a) / total)) for a, b in intervals]
    if sum(counts) == 0:
        counts[max(range(len(intervals)), key=lambda i: intervals[i][1] - intervals[i][0])] = 1
    for (a, b), c in zip(intervals, counts):
        if c == 0:
            continue
        slot = (b - a) / c
        ww = min(w, slot - 0.3)
        if ww < 0.4:
            continue
        for k in range(c):
            mid = a + slot * (k + 0.5)
            out.append((mid - ww / 2, mid + ww / 2))
    return out


def _subtract(interval, taken, pad=0.3):
    a, b = interval
    res = [(a, b)]
    for t0, t1 in taken:
        nxt = []
        for x0, x1 in res:
            if t1 + pad <= x0 or t0 - pad >= x1:
                nxt.append((x0, x1))
                continue
            if t0 - pad > x0:
                nxt.append((x0, t0 - pad))
            if t1 + pad < x1:
                nxt.append((t1 + pad, x1))
        res = nxt
    return res


def _place_openings(rng, plan, f):
    H = min(f.wall_h or plan.ceiling_h, plan.ceiling_h)
    names = {r.name: r for r in f.rooms}

    # Interior doors and arches
    for a, b, kind in f.connections:
        ra, rb = names[a], names[b]
        edge = shared_edge(ra, rb)
        if edge is None:
            plan.warnings.append(f"{f.label}: {a} and {b} don't touch; no door")
            continue
        if kind == "ARCH":
            span = _place_door(rng, plan, edge, ARCH[0], where="mid")
            z1, leaf = ARCH[1], False
        else:
            small = ra if ra.kind != "corridor" else rb
            w = DOOR_W.get(small.kind, DOOR_W_DEFAULT)
            span = _place_door(rng, plan, edge, w)
            z1, leaf = DOOR_H, True
        if span is None:
            plan.warnings.append(f"{f.label}: no room for a door between {a} and {b}")
            continue
        f.openings.append(Opening(kind if kind == "ARCH" else "DOOR", edge[0], edge[1],
                                  span[0], span[1], 0.0, min(z1, H - 0.1), (a, b), leaf))

    # Front door on the living room's facade (prefer the long sides)
    taken = {}   # (axis, coord) -> [(s0, s1)]
    ent = getattr(f, "entrance_room", None)
    if ent:
        edges = _exterior_edges(plan, names[ent])
        long_edges = [e for e in edges if e[0] == "X"] or edges
        e = rng.choice(long_edges)
        span = _place_door(rng, plan, e, ENTRANCE[0], extra=0.4, where="rand")
        if span:
            f.openings.append(Opening("ENTRANCE", e[0], e[1], span[0], span[1], 0.0, ENTRANCE[1], (ent,)))
            taken.setdefault((e[0], e[1]), []).append(span)

    # Windows on every outside wall a room has
    for r in f.rooms:
        spec = WINDOWS.get(r.kind)
        if spec is None:
            continue
        edges = _exterior_edges(plan, r)
        if not edges:
            continue
        edges.sort(key=lambda e: -(e[3] - e[2]))
        w, h, sill = spec
        patio_done = False
        for i, e in enumerate(edges):
            length = e[3] - e[2]
            if r.kind in ("bathroom", "wc", "corridor"):
                if i > 0:
                    break
                n = 1
            elif r.kind in ("master", "bedroom", "study"):
                if i > 0 and rng.random() < 0.5:
                    continue
                n = 2 if length > 5.0 else 1
            else:  # living, kitchen
                n = max(1, round(length / 3.0))
            a, b = _margins(plan, e[0], e[2], e[3], 0.25 if r.kind != "corridor" else 0.08)
            free = _subtract((a, b), taken.get((e[0], e[1]), []))
            spans = []
            if r.kind == "living" and not patio_done and length >= 4.5:
                big = max(free, key=lambda iv: iv[1] - iv[0], default=None)
                if big and big[1] - big[0] >= PATIO[0] + 0.2:
                    mid = (big[0] + big[1]) / 2
                    ps = (mid - PATIO[0] / 2, mid + PATIO[0] / 2)
                    f.openings.append(Opening("PATIO", e[0], e[1], ps[0], ps[1], 0.0, PATIO[1], (r.name,)))
                    free = _subtract((a, b), taken.get((e[0], e[1]), []) + [ps])
                    n = max(0, n - 1)
                    patio_done = True
            spans = _spread(free, n, w)
            for s0, s1 in spans:
                f.openings.append(Opening("WINDOW", e[0], e[1], s0, s1, sill, min(sill + h, H - 0.15), (r.name,)))
