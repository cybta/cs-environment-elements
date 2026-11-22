"""Shopping-row floor plans. Pure Python, built on house_layout's rooms, doors and walls.

A terrace of two-storey shops side by side, after the old high-street shopfronts in the
user's references (Desktop\\shopping center): each shop has its own glazed front and
door on the street, and the shops at the two ends can wrap their display windows round
the corner. One bay holds the shared entrance: a hall, a stair, and beside it a passage
to a back corridor that runs the length of the upper floor with a door to every office.

    ground floor                                   upper floor
    +--------+--------+----+---+--------+          +-----------------------------------+
    | Store1 | Store2 | WC |   | Store3 |  y = D   |        Corridor (doors to all)    |
    |--door--|--door--+----+ B |--door--|          +--door--+--door--+----+   +--door--+
    | Shop 1 | Shop 2 |Stai| H | Shop 3 |  ye      |Off1|Off2|Off3|hole| P |Off4|Off5|
    |        |        |rs  |   |        |  ys      |        |        +----+---+        |
    |        |        |  Hall  |        |          |        |        | Landing|        |
    +--door--+--door--+--door--+--door--+  y = 0   +--------+--------+--------+--------+
                       entrance bay (stair + passage)

B = back hall with the service door, P = passage from the landing to the corridor.
Over each shop the upper floor is cut into offices 3 - 5.9 m wide (a 7 m shop gets two),
numbered Office 1, 2, 3... along the row.
The stair is the house's two flights with a half landing; its well stops at ye, so the
corridor never passes over it.

Notes for the exterior (shop.py) go in plan.shops; street and side openings carry a `role`.
"""

import math
import random

try:
    from . import house_layout as hl
    from .house_walls import shared_edge, _build_walls, _build_stair
except ImportError:  # run as a plain script, outside the addon package
    import house_layout as hl
    from house_walls import shared_edge, _build_walls, _build_stair

STAIR_W = 2.6           # two flights side by side
PASS_W = 1.2            # the passage beside the stair
ENT_W = STAIR_W + PASS_W
CORR_W = 1.6            # the back corridor upstairs
STORE_D = 2.4           # stockroom depth behind each shop
MIN_H = 2.8             # a shop needs room for a shopfront, awning and sign
SILL = 0.45             # display windows stand on a stall riser this high
PIER = 0.2              # wall left between two openings of one shopfront
EDGE = 0.45             # first opening from the bay line (pilaster + shopfront post)
SIDE_EDGE = 0.7         # first side window from the front corner (corner pilaster + post)
SIDE_PANE = 2.4         # widest single side window
DOOR_W = 1.0
ENTRY_W = 1.3           # the shared entrance: a pair of doors
OFFICE_MIN, OFFICE_MAX = 3.0, 5.9   # office widths upstairs: a wide shop gets two (or more) offices


def stair_length(plan):
    """Length of the stairwell for two flights with a half landing (house_walls._build_stair)."""
    n = max(4, math.ceil(plan.storey_h / 0.185))
    n1 = n // 2
    treads = max(n1 - 1, n - n1 - 1)
    return hl._snap(treads * 0.27 + 1.15 + plan.t_int / 2 + 0.05)


def _bays(rng, count, width, vary, entrance):
    """[(kind, x0, x1, shop index)] left to right; kind 'shop' or 'entry'."""
    widths = [hl._snap(width * (rng.uniform(0.85, 1.2) if vary else 1.0)) for _ in range(count)]
    at = {"LEFT": 0, "RIGHT": count}.get(entrance, count // 2)
    seq = [("shop", w, i) for i, w in enumerate(widths)]
    seq.insert(at, ("entry", ENT_W, -1))
    out, x = [], 0.0
    for kind, w, i in seq:
        out.append((kind, round(x, 4), round(x + w, 4), i))
        x += w
    return out


def _door(rng, plan, f, a, b, width=0.9, where=None):
    """An inside door between rooms a and b (names), placed on the wall they share."""
    ra, rb = f.room(a), f.room(b)
    edge = shared_edge(ra, rb)
    span = hl._place_door(rng, plan, edge, width, where=where) if edge else None
    if span is None:
        plan.warnings.append(f"{f.label}: no room for a door between {a} and {b}")
        return
    f.openings.append(hl.Opening("DOOR", edge[0], edge[1], span[0], span[1], 0.0,
                                 min(hl.DOOR_H, plan.ceiling_h - 0.1), (a, b)))


def _role(o, role):
    o.role = role
    return o


def _side_panes(a, b):
    """Split a side wall's glazing a..b into windows no wider than SIDE_PANE, PIER apart."""
    n = max(1, math.ceil((b - a + PIER) / (SIDE_PANE + PIER)))
    w = (b - a - (n - 1) * PIER) / n
    return [(a + i * (w + PIER), a + i * (w + PIER) + w) for i in range(n)] if w >= 0.6 else []


def make_shop_plan(count=4, width=5.0, depth=10.0, vary=True, entrance="MIDDLE", stockrooms=True,
                   side_windows=True, seed=0, ceiling_h=3.2, slab=0.25, t_ext=0.3, t_int=0.15):
    rng = random.Random(seed * 61 + 17)
    plan = hl.Plan()
    plan.ceiling_h, plan.slab, plan.t_ext, plan.t_int = ceiling_h, slab, t_ext, t_int
    H = ceiling_h
    if H < MIN_H:
        plan.warnings.append(f"Shops want a ceiling of {MIN_H:.1f} m or more; the shopfronts are squeezed")

    bays = _bays(rng, max(1, count), max(3.5, width), vary, entrance)
    W = bays[-1][2]
    L = stair_length(plan)
    D = hl._snap(max(depth, 6.0))
    need = hl._snap(L + CORR_W + 1.6)
    if D < need:
        plan.warnings.append(f"Depth raised to {need:.1f} m to fit the stair, hall and back corridor")
        D = need
    ye = D - CORR_W                     # back of the stairwell = front of the corridor upstairs
    ys = hl._snap(ye - L)               # front of the stairwell = back of the hall
    plan.W, plan.D = W, D
    stock = stockrooms and D - STORE_D >= 5.5
    if stockrooms and not stock:
        plan.warnings.append("Shops too shallow for stockrooms; left out")

    # Openings: the shopfront top, the upper windows (all in floor-local heights)
    top = min(2.45, H - 0.75)
    up_z1 = min(H - 0.7, 2.5)
    up_z0 = max(0.6, up_z1 - 1.85)

    g, u = hl.Floor(0), hl.Floor(1)
    plan.floors += [g, u]
    g.entrance_room = u.entrance_room = None
    u.rooms.append(hl.Room("Corridor", "corridor", 0.0, ye, W, D))
    notes = []          # per bay, for the exterior
    office_names = []
    sides = []          # end walls with display windows: ("Y", x)

    for kind, x0, x1, i in bays:
        if kind == "entry":
            left = rng.random() < 0.5                       # stair on the left or right of the bay
            sx = (x0, x0 + STAIR_W) if left else (x1 - STAIR_W, x1)
            px = (x0 + STAIR_W, x1) if left else (x0, x1 - STAIR_W)
            g.rooms += [hl.Room("Entrance Hall", "corridor", x0, 0.0, x1, ys),
                        hl.Room("Stairs", "stair", sx[0], ys, sx[1], ye),
                        hl.Room("Back Hall", "hall", px[0], ys, px[1], D),
                        hl.Room("WC", "wc", sx[0], ye, sx[1], D)]
            g.open_pairs.update((frozenset(("Stairs", "Entrance Hall")), frozenset(("Back Hall", "Entrance Hall"))))
            _door(rng, plan, g, "Back Hall", "WC", 0.75)
            span = hl._place_door(rng, plan, ("X", D, px[0], px[1]), 0.9, extra=0.05, where="mid")
            if span:
                g.openings.append(hl.Opening("ENTRANCE", "X", D, span[0], span[1], 0.0, 2.1, ("Back Hall",)))
            u.rooms += [hl.Room("Landing", "corridor", x0, 0.0, x1, ys),
                        hl.Room("Stairs", "stair", sx[0], ys, sx[1], ye),
                        hl.Room("Passage", "corridor", px[0], ys, px[1], ye)]
            u.open_pairs.update((frozenset(("Stairs", "Landing")), frozenset(("Passage", "Landing")),
                                 frozenset(("Passage", "Corridor"))))
            m = (x0 + x1) / 2
            g.openings.append(_role(hl.Opening("ENTRANCE", "X", 0.0, m - ENTRY_W / 2, m + ENTRY_W / 2, 0.0,
                                               min(top + 0.15, H - 0.45), ("Entrance Hall",), leaf=False), "entry"))
            u.openings.append(_role(hl.Opening("WINDOW", "X", 0.0, m - 0.55, m + 0.55, up_z0, up_z1, ("Landing",)), "upper"))
            notes.append(dict(kind="entry", x0=x0, x1=x1, stair=sx))
            continue

        n = i + 1
        shop = f"Shop {n}"
        yb = D - STORE_D if stock else D
        g.rooms.append(hl.Room(shop, "shop", x0, 0.0, x1, yb))
        if stock:
            g.rooms.append(hl.Room(f"Stockroom {n}", "storage", x0, yb, x1, D))
        # Upstairs: offices OFFICE_MIN..OFFICE_MAX wide over the shop, numbered along the row
        k = max(1, math.ceil((x1 - x0) / OFFICE_MAX - 1e-6))
        cuts = [x0] + [hl._snap(x0 + (x1 - x0) * j / k) for j in range(1, k)] + [x1]
        offices = []
        for ox0, ox1 in zip(cuts, cuts[1:]):
            offices.append(f"Office {len(office_names) + 1}")
            office_names.append(offices[-1])
            u.rooms.append(hl.Room(offices[-1], "office", ox0, 0.0, ox1, ye))

        # Shopfront: display windows and a glazed door, in one of the references' arrangements
        a, b = x0 + EDGE, x1 - EDGE
        layout = rng.choice(("mid", "left", "right") if b - a > DOOR_W + 2 * (PIER + 1.0) else ("left", "right"))
        d0 = {"left": a, "right": b - DOOR_W, "mid": (a + b - DOOR_W) / 2}[layout]
        d1 = d0 + DOOR_W
        g.openings.append(_role(hl.Opening("ENTRANCE", "X", 0.0, d0, d1, 0.0, top, (shop,), leaf=False), "door"))
        for s0, s1 in ((a, d0 - PIER), (d1 + PIER, b)):
            if s1 - s0 >= 0.6:
                g.openings.append(_role(hl.Opening("WINDOW", "X", 0.0, s0, s1, SILL, top, (shop,)), "display"))

        # The end shops: display windows round the corner, tall windows upstairs (panoramic)
        glazed = []
        if side_windows:
            glazed = [c for c, edge in ((0.0, x0 < 1e-4), (W, x1 > W - 1e-4)) if edge]
        for c in glazed:
            sides.append(c)
            for s0, s1 in _side_panes(SIDE_EDGE, yb - (t_int if stock else t_ext) / 2 - 0.45):
                g.openings.append(_role(hl.Opening("WINDOW", "Y", c, s0, s1, SILL, top, (shop,)), "display"))
            room = offices[0] if c < 1e-4 else offices[-1]
            nf = max(1, round((ye - 1.2) / 1.75))
            for s0, s1 in hl._spread([(0.6, ye - 0.3)], nf, 1.0):
                u.openings.append(_role(hl.Opening("WINDOW", "Y", c, s0, s1, up_z0, up_z1, (room,)), "upper"))
            # and the corridor's end gets a window too
            u.openings.append(hl.Opening("WINDOW", "Y", c, ye + CORR_W / 2 - 0.4, ye + CORR_W / 2 + 0.4,
                                         0.9, min(2.3, H - 0.3), ("Corridor",)))

        # Back: a service door (and a small window) in the stockroom, or straight into the shop
        back = f"Stockroom {n}" if stock else shop
        span = hl._place_door(rng, plan, ("X", D, x0, x1), 0.9, extra=0.3)
        if span:
            g.openings.append(hl.Opening("ENTRANCE", "X", D, span[0], span[1], 0.0, 2.1, (back,)))
            free = hl._subtract(hl._margins(plan, "X", x0, x1, 0.3), [span])
            for s0, s1 in hl._spread(free, 1, 0.8):
                g.openings.append(hl.Opening("WINDOW", "X", D, s0, s1, 1.45, min(2.1, H - 0.3), (back,)))
        if stock:
            _door(rng, plan, g, shop, back)

        # Upstairs: each office's tall street windows and its door onto the corridor; a corridor window behind
        for name in offices:
            r = u.room(name)
            nf = max(1, round((r.x1 - r.x0 - 0.9) / 1.75))
            for s0, s1 in hl._spread([(r.x0 + 0.5, r.x1 - 0.5)], nf, 1.0):
                u.openings.append(_role(hl.Opening("WINDOW", "X", 0.0, s0, s1, up_z0, up_z1, (name,)), "upper"))
            _door(rng, plan, u, name, "Corridor", where="mid")
        for s0, s1 in hl._spread([hl._margins(plan, "X", x0, x1, 0.3)], 1, 0.9):
            u.openings.append(hl.Opening("WINDOW", "X", D, s0, s1, 0.9, min(2.3, H - 0.3), ("Corridor",)))
        notes.append(dict(kind="shop", x0=x0, x1=x1, index=i, name=shop, layout=layout,
                          sides=glazed, offices=offices))

    for f in plan.floors:
        f.base_z = f.index * plan.storey_h
        _build_walls(plan, f)
    _build_stair(rng, plan, g, u)

    plan.shops = dict(bays=notes, top=top, sill=SILL, up_z0=up_z0, up_z1=up_z1, stock=stock, sides=sides,
                      sign0=top + 0.2, sign1=min(H + 0.05, top + 0.95))
    return plan
