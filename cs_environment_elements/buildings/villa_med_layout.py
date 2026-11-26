"""The Mediterranean villa's floor plan (villa_layout's third style). Pure Python.

A Spanish-style courtyard house after the user's reference (Desktop\\ref\\villas\\new
Mediterenian Villa, 74 x 74 ft): four wings round an open courtyard, and over the front
middle a small upper floor with the primary suite. Front at y = 0 (the street), x across:

    +---------+---------------------------------------+---------+  y = D
    | Kitchen |              Great Room               | Bed 1   |   back corners: their own gables
    +---------+---------------------------------------+---------+  ygr
    | Pantry  |  Loggia (arcade, lean-to roof)        | Closet  |
    +---------+--+---------------------------------+--+---------+  ylg
    | Dining  |G |                                 |G | Guest Ba|
    |         |a |          Courtyard              |a | Bed 2   |   wings: hip roofs that reach
    | Laundry |l.|                                 |l.| Powder  |   over the galleries
    +---------+--+-------+-----+----+-------+------+--+---------+  FD
    |  Study            | Lib | St | Pass. | Draw.|  Family     |   corner rooms: front gables
    |                   +-----+----+-------+------+  Lounge     |   middle: two storeys, hip roof,
    |                   |     | Entry      |      |             |   the entry bay a gable
    +-------------------+     +------------+      +-------------+  y = 0

Every block has its own roof at its own height (plan.villa["units"]); villa_med_roof builds
them. Rooms that open onto the courtyard, the galleries and the loggia get doors and windows
on those walls too. Round-topped openings (the front door and the French door over it) carry
`round = True` and no leaf: villa_med builds their arch, glass and door.
"""

import math
import random

try:
    from . import house_layout as hl
    from . import villa_layout as vl
    from .house_walls import OUTDOOR, shared_edge
except ImportError:  # run as a plain script, outside the addon package
    import house_layout as hl
    import villa_layout as vl
    from house_walls import OUTDOOR, shared_edge

PITCH = 22.0
MIN_AREA = 380.0
REF_AREA = 423.0        # the reference's 4,556 sq ft: the plan below at scale 1
MAX_SCALE = 1.3
STAIR_D = 3.4           # the stairwell, front to back (two flights and a half landing)
RECESS = 0.7            # library and drawing room (and the suite over them) sit back this much

# Raised blocks: how far their walls go up past the ground floor's ceiling
RAISE = {"corner_front": 1.0, "corner_back": 0.9, "great": 2.4}

# Bigger windows than the house generator's: (width, height, sill)
WINDOWS = {
    "master": (1.3, 1.9, 0.6), "bedroom": (1.2, 1.9, 0.6), "study": (1.2, 1.9, 0.6),
    "bathroom": (0.7, 0.9, 1.4), "wc": (0.6, 0.7, 1.5), "kitchen": (1.2, 1.3, 1.0),
    "living": (1.3, 2.0, 0.5), "corridor": (0.9, 1.6, 0.8),
}


def _arched(kind, axis, coord, s0, s1, z1, room):
    o = hl.Opening(kind, axis, coord, s0, s1, 0.0, z1, (room,), leaf=False)
    o.round = True
    return o


def _openings(rng, plan, f):
    """The house rules' doors and windows, with the walls onto the courtyard, galleries,
    loggia and voids counting as outside walls too."""
    outdoor = [r for r in f.rooms if r.kind in OUTDOOR]
    base = hl._exterior_edges

    def edges(p, r):
        out = list(base(p, r))
        if r.kind not in OUTDOOR:
            out += [e for e in (shared_edge(r, o) for o in outdoor) if e]
        return out

    saved = hl.WINDOWS
    hl.WINDOWS, hl._exterior_edges = WINDOWS, edges
    try:
        hl._place_openings(rng, plan, f)
    finally:
        hl.WINDOWS, hl._exterior_edges = saved, base


def _drop_windows_at_doors(f, pad=0.25):
    doors = [o for o in f.openings if o.kind in ("DOOR", "ARCH", "ENTRANCE")]
    f.openings = [o for o in f.openings if o.kind not in ("WINDOW", "PATIO") or not any(
        d.axis == o.axis and abs(d.coord - o.coord) < 1e-4 and d.s0 - pad < o.s1 and o.s0 < d.s1 + pad
        for d in doors)]


def make(area, bedrooms, bathrooms, seed, ceiling_h, slab, t_ext, t_int):
    rng = random.Random(seed * 31 + 11)
    plan = hl.Plan()
    plan.ceiling_h, plan.slab, plan.t_ext, plan.t_int = ceiling_h, slab, t_ext, t_int
    H = ceiling_h
    if area < MIN_AREA:
        plan.warnings.append(f"This villa needs about {MIN_AREA:.0f} m2 or more; built at its smallest size")
        area = MIN_AREA
    if int(bedrooms) != 3 or int(bathrooms) != 2:
        plan.warnings.append("The courtyard villa always has 3 bedrooms, 2 bathrooms and a powder room")
    k = min(math.sqrt(area / REF_AREA), MAX_SCALE)

    def sn(v):
        return hl._snap(v * k)

    # ---- The grid ---------------------------------------------------------------
    WG, GA, CW = sn(4.4), sn(2.0), sn(9.8)            # wing rooms, gallery, courtyard across
    xc = WG + GA                                      # courtyard edge; the corner rooms' width
    W = 2 * xc + CW
    EW = sn(3.8)                                      # entry, centred
    xe0, xe1 = hl._snap(W / 2 - EW / 2), hl._snap(W / 2 + EW / 2)
    xs1 = xe0 + 2.4                                   # stairwell beside the passage to the courtyard
    FD = max(sn(6.4), RECESS + 2.4 + STAIR_D - 0.7)   # front block depth
    yst = FD - STAIR_D
    ylg = FD + sn(9.2)                                # courtyard -> loggia
    ygr = ylg + sn(1.8)                               # loggia -> great room
    D = ygr + sn(5.2)
    plan.W, plan.D = W, D
    R = hl.Room

    # ---- Ground floor -----------------------------------------------------------
    g = hl.Floor(0)
    plan.floors.append(g)
    g.entrance_room = None
    yl = [FD, FD + sn(3.4), ylg]                       # left wing: laundry, dining
    yr = [FD, FD + sn(1.8), FD + sn(6.4), FD + sn(9.0), ygr]      # right: powder, bed 2, bath, closet
    g.rooms += [
        R("Entry", "corridor", xe0, 0.0, xe1, yst),   # first corridor: the stair runs off it
        R("Stairs", "stair", xe0, yst, xs1, FD),
        R("Passage", "corridor", xs1, yst, xe1, FD),
        R("Study", "study", 0.0, 0.0, xc, FD),
        R("Library", "study", xc, RECESS, xe0, FD),
        R("Drawing Room", "living", xe1, RECESS, W - xc, FD),
        R("Family Lounge", "living", W - xc, 0.0, W, FD),
        R("Laundry", "bathroom", 0.0, yl[0], WG, yl[1]),
        R("Dining Room", "living", 0.0, yl[1], WG, yl[2]),
        R("Pantry", "storage", 0.0, ylg, WG, ygr),
        R("Kitchen", "kitchen", 0.0, ygr, WG, D),
        R("Powder Room", "wc", W - WG, yr[0], W, yr[1]),
        R("Bedroom 2", "bedroom", W - WG, yr[1], W, yr[2]),
        R("Guest Bathroom", "bathroom", W - WG, yr[2], W, yr[3]),
        R("Bedroom 1 Closet", "storage", W - WG, yr[3], W, ygr),
        R("Bedroom 1", "bedroom", W - WG, ygr, W, D),
        R("Great Room", "living", WG, ygr, W - WG, D),
        R("Courtyard", "terrace", xc, FD, W - xc, ylg),
        R("Left Gallery", "terrace", WG, FD, xc, ylg),
        R("Right Gallery", "terrace", W - xc, FD, W - WG, ylg),
        R("Loggia", "terrace", WG, ylg, W - WG, ygr),
        R("Front Left", "void", xc, 0.0, xe0, RECESS),
        R("Front Right", "void", xe1, 0.0, W - xc, RECESS),
    ]
    g.open_pairs.update((frozenset(("Entry", "Stairs")), frozenset(("Entry", "Passage"))))
    g.connections += [
        ("Entry", "Library", "DOOR"), ("Entry", "Drawing Room", "DOOR"), ("Passage", "Courtyard", "DOOR"),
        ("Library", "Study", "DOOR"), ("Drawing Room", "Family Lounge", "DOOR"),
        ("Library", "Courtyard", "DOOR"), ("Drawing Room", "Courtyard", "DOOR"),
        ("Study", "Left Gallery", "DOOR"), ("Family Lounge", "Right Gallery", "DOOR"),
        ("Laundry", "Left Gallery", "DOOR"), ("Dining Room", "Left Gallery", "DOOR"),
        ("Pantry", "Kitchen", "DOOR"), ("Kitchen", "Great Room", "ARCH"),
        ("Powder Room", "Family Lounge", "DOOR"), ("Bedroom 2", "Right Gallery", "DOOR"),
        ("Guest Bathroom", "Right Gallery", "DOOR"), ("Bedroom 1 Closet", "Bedroom 1", "DOOR"),
        ("Bedroom 1", "Great Room", "DOOR"),
    ]

    # ---- Upper floor: the primary suite over the front middle -------------------
    u = hl.Floor(1)
    plan.floors.append(u)
    u.entrance_room = None
    ym = RECESS + hl._snap((FD - RECESS) * 0.45)
    u.rooms += [
        R("Upper Landing", "corridor", xe0, 0.0, xe1, yst),
        R("Stairs", "stair", xe0, yst, xs1, FD),
        R("Upper Hall", "corridor", xs1, yst, xe1, FD),
        R("Dressing Room", "study", xc, RECESS, xe0, ym),
        R("Primary Bathroom", "bathroom", xc, ym, xe0, FD),
        R("Primary Bedroom", "master", xe1, RECESS, W - xc, FD),
        R("Sky West", "void", 0.0, 0.0, xc, D),
        R("Sky East", "void", W - xc, 0.0, W, D),
        R("Sky Back", "void", xc, FD, W - xc, D),
        R("Sky Front Left", "void", xc, 0.0, xe0, RECESS),
        R("Sky Front Right", "void", xe1, 0.0, W - xc, RECESS),
    ]
    u.open_pairs.update((frozenset(("Upper Landing", "Stairs")), frozenset(("Upper Landing", "Upper Hall"))))
    u.connections += [("Dressing Room", "Upper Landing", "DOOR"), ("Primary Bathroom", "Dressing Room", "DOOR"),
                      ("Primary Bedroom", "Upper Landing", "DOOR")]

    # ---- Doors and windows -------------------------------------------------------
    for f in plan.floors:
        f.base_z = f.index * plan.storey_h
        _openings(rng, plan, f)

    top = H - 0.35
    mid = W / 2
    # Arched double front door, an arched French door over it onto a little balcony
    vl._clear(g, "X", 0.0, xe0, xe1)
    dw = min(1.4, EW - 0.6)
    g.openings.append(_arched("ENTRANCE", "X", 0.0, mid - dw / 2, mid + dw / 2, min(top + 0.05, 2.75), "Entry"))
    vl._clear(u, "X", 0.0, xe0, xe1)
    fw = min(1.2, EW - 0.8)
    u.openings.append(_arched("PATIO", "X", 0.0, mid - fw / 2, mid + fw / 2, min(H - 0.3, 2.65), "Upper Landing"))

    # The great room: French doors onto the loggia, in line with the arcade's bays, and tall
    # windows on the back wall
    vl._clear(g, "X", ygr, WG, W - WG)
    vl._clear(g, "X", D, WG, W - WG)
    n = 3
    for i in range(n):
        m = xc + CW * (i + 0.5) / n
        g.openings.append(hl.Opening("PATIO", "X", ygr, m - 0.8, m + 0.8, 0.0, min(2.5, top), ("Great Room",)))
    n = max(3, round((W - 2 * WG) / 3.2))
    for i in range(n):
        m = WG + (W - 2 * WG) * (i + 0.5) / n
        g.openings.append(hl.Opening("WINDOW", "X", D, m - 0.65, m + 0.65, 0.5, min(2.5, top), ("Great Room",)))
    # Upstairs, the side walls look straight onto the corner rooms' raised gable roofs
    vl._clear(u, "Y", xc, 0.0, D)
    vl._clear(u, "Y", W - xc, 0.0, D)
    for f in plan.floors:
        _drop_windows_at_doors(f)
        hl._build_walls(plan, f)
    hl._build_stair(rng, plan, g, u, style="VILLA")

    # ---- Roofs: every block its own, at its own height ----------------------------
    F1 = plan.storey_h
    top_main = F1 + H

    def unit(name, rect, top, kind, ridge, **kw):
        d = {"name": name, "rect": rect, "top": top, "kind": kind, "ridge": ridge}
        d.update(kw)
        return d

    plan.villa = {
        "style": "MEDITERRANEAN", "pitch": PITCH, "knee": None, "ridge_z": None, "bay": None,
        "court": (xc, FD, W - xc, ylg), "galleries": (WG, W - WG), "loggia": (WG, ylg, W - WG, ygr),
        "units": [
            unit("Main", (xc, RECESS, W - xc, FD), top_main, "HIP", "X", chimney=False),
            unit("EntryBay", (xe0, 0.0, xe1, RECESS), top_main, "GABLE", "Y",
                 roof_rect=(xe0, 0.0, xe1, yst),          # runs back into the hip, which hides its back end
                 slab=(xe0 - t_ext / 2, -t_ext / 2, xe1 + t_ext / 2, RECESS - t_ext / 2)),
            unit("Study", (0.0, 0.0, xc, FD), H + RAISE["corner_front"], "GABLE", "Y"),
            unit("Lounge", (W - xc, 0.0, W, FD), H + RAISE["corner_front"], "GABLE", "Y"),
            unit("WestWing", (0.0, FD, xc, ygr), H, "HIP", "Y"),
            unit("EastWing", (W - xc, FD, W, ygr), H, "HIP", "Y", chimney=True),
            unit("Kitchen", (0.0, ygr, WG, D), H + RAISE["corner_back"], "GABLE", "Y"),
            unit("Bedroom1", (W - WG, ygr, W, D), H + RAISE["corner_back"], "GABLE", "Y"),
            unit("GreatRoom", (WG, ygr, W - WG, D), H + RAISE["great"], "HIP", "X", chimney=True,
                 clerestory=(xc, W - xc)),
        ],
    }
    return plan
