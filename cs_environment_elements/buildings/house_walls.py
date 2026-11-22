"""Walls and stairs derived from a floor's room rectangles. Pure Python.

Rooms tile the footprint rectangle. A room whose kind is in OUTDOOR (carport,
terrace, balcony) is open air: it gets no walls of its own, and the edge it
shares with an indoor room is an outside wall. That is how villas get a
carport cut out of the ground floor or a balcony recessed into the upper one.
"""

import math

try:
    from .villa_stair import GAP, stair_fence
except ImportError:  # run as a plain script, outside the addon package
    from villa_stair import GAP, stair_fence

OUTDOOR = ("carport", "terrace", "balcony")


def shared_edge(a, b):
    """('X', y, s0, s1) or ('Y', x, s0, s1) for the edge two rooms share, else None."""
    for ya, yb in ((a.y1, b.y0), (a.y0, b.y1)):
        if abs(ya - yb) < 1e-4:
            s0, s1 = max(a.x0, b.x0), min(a.x1, b.x1)
            if s1 - s0 > 1e-3:
                return ("X", ya, s0, s1)
    for xa, xb in ((a.x1, b.x0), (a.x0, b.x1)):
        if abs(xa - xb) < 1e-4:
            s0, s1 = max(a.y0, b.y0), min(a.y1, b.y1)
            if s1 - s0 > 1e-3:
                return ("Y", xa, s0, s1)
    return None


def _merge(segs):
    """Merge touching/overlapping collinear intervals: {key: [(a, b)]}."""
    out = {}
    for key, ivs in segs.items():
        ivs = sorted(ivs)
        merged = [list(ivs[0])]
        for a, b in ivs[1:]:
            if a <= merged[-1][1] + 1e-4:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        out[key] = [tuple(m) for m in merged]
    return out


def _wall_lines(plan, f):
    """{(axis, coord, exterior): [(a, b)]} for every wall line on this floor."""
    W, D = plan.W, plan.D
    inside = [r for r in f.rooms if r.kind not in OUTDOOR]
    outside = [r for r in f.rooms if r.kind in OUTDOOR]
    raw = {}

    def add(axis, c, ext, a, b):
        raw.setdefault((axis, round(c, 4), ext), []).append((a, b))

    for i, a in enumerate(inside):
        for b in inside[i + 1:]:
            if frozenset((a.name, b.name)) in f.open_pairs:
                continue
            e = shared_edge(a, b)
            if e:
                add(e[0], e[1], False, e[2], e[3])
        for b in outside:
            e = shared_edge(a, b)
            if e:
                add(e[0], e[1], True, e[2], e[3])
        if a.y0 < 1e-4:
            add("X", 0.0, True, a.x0, a.x1)
        if a.y1 > D - 1e-4:
            add("X", D, True, a.x0, a.x1)
        if a.x0 < 1e-4:
            add("Y", 0.0, True, a.y0, a.y1)
        if a.x1 > W - 1e-4:
            add("Y", W, True, a.y0, a.y1)
    return _merge(raw) if raw else {}


def _build_walls(plan, f):
    W, D = plan.W, plan.D
    H = getattr(f, "wall_h", None) or plan.ceiling_h
    te, ti = plan.t_ext, plan.t_int
    lines = _wall_lines(plan, f)

    ext_y = [(c, a, b) for (axis, c, ext), ivs in lines.items() if axis == "Y" and ext for a, b in ivs]

    def at_outside_wall(x, y):
        """Does an outside wall running along Y pass through (x, y)?"""
        return any(abs(c - x) < 1e-4 and a - 1e-4 <= y <= b + 1e-4 for c, a, b in ext_y)

    # Every outside wall drops over the slab edge below it, so no gap shows where a balcony or
    # terrace slab meets the facade. No wall face may lie in the same plane as a slab face
    # (that flickers in the viewport), hence the 3 mm offsets.
    # Walls reach 3 mm up into the slab above, and an upper storey's outside walls start 3 mm
    # above the slab bottom, so a storey's walls meet the one below without overlapping it.
    drop = -plan.slab + (0.003 if f.index > 0 else -0.003)
    top = H + 0.003
    # Junctions: X-running walls go through, Y-running walls are cut around them.
    segments = []   # (axis, coord, a, b, thickness, z0, exterior)
    xs = []
    for (axis, c, ext), ivs in lines.items():
        if axis != "X":
            continue
        for a, b in ivs:
            if ext:                       # outside walls cover their corners
                a, b = a - te / 2, b + te / 2
            else:                         # inside walls stop at the inner face of an outside wall
                a = a + te / 2 if at_outside_wall(a, c) else a - ti / 2
                b = b - te / 2 if at_outside_wall(b, c) else b + ti / 2
            t = te if ext else ti
            xs.append((c, a, b, t, ext))
            segments.append(("X", c, a, b, t, drop if ext else 0.0, ext))
    for (axis, c, ext), ivs in lines.items():
        if axis != "Y":
            continue
        t = te if ext else ti
        for a, b in ivs:
            pieces = [(a, b)]
            for yc, xa, xb, tx, xext in xs:
                if xa - 1e-4 <= c <= xb + 1e-4 and (xext or not ext):
                    pieces = [p for p0, p1 in pieces for p in _cut(p0, p1, yc - tx / 2, yc + tx / 2)]
            for p0, p1 in pieces:
                if p1 - p0 > 1e-3:
                    segments.append(("Y", c, p0, p1, t, drop if ext else 0.0, ext))

    # Hand each opening to the wall piece that contains it
    holes = {i: [] for i in range(len(segments))}
    for o in f.openings:
        for i, (axis, c, a, b, t, z0, ext) in enumerate(segments):
            if axis == o.axis and abs(c - o.coord) < 1e-4 and a - 1e-4 <= o.s0 and o.s1 <= b + 1e-4:
                holes[i].append(o)
                o.exterior, o.thickness = ext, t
                break
        else:
            plan.warnings.append(f"{f.label}: opening {o.kind} at {o.axis}={o.coord:.2f} has no wall")

    boxes = []
    for i, (axis, c, a, b, t, z0, ext) in enumerate(segments):
        cur = a
        for o in sorted(holes[i], key=lambda o: o.s0):
            if o.s0 > cur + 1e-4:
                boxes.append(_wall_box(axis, c, t, cur, o.s0, z0, top))
            if o.z0 > z0 + 1e-4:
                # A threshold under a floor-level door stays just below the floor, not level with it
                boxes.append(_wall_box(axis, c, t, o.s0, o.s1, z0, o.z0 if o.z0 > 1e-4 else -0.004))
            if o.z1 < H - 1e-4:
                boxes.append(_wall_box(axis, c, t, o.s0, o.s1, o.z1, top))
            cur = max(cur, o.s1)
        if b > cur + 1e-4:
            boxes.append(_wall_box(axis, c, t, cur, b, z0, top))
    f.walls = boxes


def _cut(a, b, c0, c1):
    if c1 <= a or c0 >= b:
        return [(a, b)]
    out = []
    if c0 > a:
        out.append((a, c0))
    if c1 < b:
        out.append((c1, b))
    return out


def _wall_box(axis, c, t, s0, s1, z0, z1):
    if axis == "X":
        return (s0, c - t / 2, z0, s1, c + t / 2, z1)
    return (c - t / 2, s0, z0, c + t / 2, s1, z1)


def opening_box(o, depth):
    """Box filling an opening (for door leaves / glass), `depth` thick, centred in the wall."""
    return _wall_box(o.axis, o.coord, depth, o.s0, o.s1, o.z0, o.z1)


# --------------------------------------------------------------------------
# Stairs: two flights side by side with a half landing at the far end
# --------------------------------------------------------------------------

def _build_stair(rng, plan, f, above, style="HOUSE"):
    """`style` "VILLA" builds the villa stair (the user's design, see villa_stair): a 5 cm gap
    between the flights with a glass fence standing in it, instead of the house's rails."""
    st = next((r for r in f.rooms if r.kind == "stair"), None)
    corr = next((r for r in f.rooms if r.kind == "corridor"), None)
    if st is None or corr is None:
        return
    te, ti = plan.t_ext, plan.t_int
    Hs = plan.storey_h

    # Which side of the stairwell faces the corridor?
    if abs(st.y0 - corr.y1) < 1e-4:
        ys, sign, yfar = st.y0, 1.0, st.y1
    else:
        ys, sign, yfar = st.y1, -1.0, st.y0
    far_t = te if (yfar < 1e-4 or yfar > plan.D - 1e-4) else ti
    usable = abs(yfar - ys) - far_t / 2

    xa, xb = st.x0 + ti / 2, st.x1 - ti / 2
    xm = (xa + xb) / 2
    fw = xm - xa

    n = max(4, math.ceil(Hs / 0.185))
    r = Hs / n
    n1 = n // 2
    n2 = n - n1
    treads = max(n1 - 1, n2 - 1)
    landing = max(0.95, min(fw, 1.1))
    g = (usable - landing) / max(treads, 1)
    if g > 0.30:
        g = 0.30
        landing = usable - treads * g
    if g < 0.22:
        plan.warnings.append(f"{f.label}: stairwell is shallow, stairs are steep")

    def ybox(d0, d1):
        p0, p1 = ys + sign * d0, ys + sign * d1
        return min(p0, p1), max(p0, p1)

    first, second = ((xa, xm), (xm, xb)) if rng.random() < 0.5 else ((xm, xb), (xa, xm))
    villa = style == "VILLA"
    if villa:      # flight 1 gives up a strip along its inner edge: the gap the fence stands in
        first = (first[0], first[1] - GAP) if first[0] < xm else (first[0] + GAP, first[1])
    boxes = []
    thick = 0.18
    off = (treads - (n1 - 1)) * g
    for i in range(1, n1):                       # flight 1, away from the corridor
        y0, y1 = ybox(off + (i - 1) * g, off + i * g)
        top = i * r
        boxes.append((first[0], y0, max(0.0, top - r - thick), first[1], y1, top))
    y0, y1 = ybox(treads * g, usable)            # half landing
    top = n1 * r
    boxes.append((xa, y0, max(0.0, top - thick - 0.05), xb, y1, top))
    for k in range(n1 + 1, n):                   # flight 2, back towards the corridor
        y0, y1 = ybox((n - 1 - k) * g, (n - k) * g)
        top = k * r
        boxes.append((second[0], y0, max(0.0, top - r - thick), second[1], y1, top))
    f.stair = boxes
    if villa:
        dirn = 1.0 if first[0] >= xm - 1e-6 else -1.0         # side of the gap flight 1 is on
        outer = first[1] if dirn > 0 else first[0]
        f.fence = stair_fence(xm, dirn, outer, ys, sign, off, treads * g, n1 * r, Hs)
        return

    # Flight 2 runs alongside flight 1 one half-storey higher, so its inner edge gets a
    # balustrade that follows the stair: along the tread nosings, from the half landing
    # up to the floor above, where it meets the guard rail upstairs.
    xr = first[1] if first[0] < second[0] else first[0]
    xin = xr + (0.03 if second[0] >= xr - 1e-6 else -0.03)       # just onto flight 2
    d_land = (n - n1 - 1) * g                                       # landing edge of flight 2
    f.srails.append(((xin, ys + sign * d_land, (n - d_land / g) * r), (xin, ys, Hs)))

    # Guard rail upstairs across the drop above flight 1 (if nothing continues up from it)
    if above.index == len(plan.floors) - 1:
        y0, y1 = ybox(0.0, 0.05)
        above.rails.append((first[0], y0, 0.0, first[1], y1, 0.95))
