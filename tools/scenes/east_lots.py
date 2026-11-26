"""Straight lot sides for the east side (user, 2026-11-25: "remove these bends from the fences, fences should be
completely straight").

plan_east.py traces the lots from the user's drawing on a raster, so every side is a chain of short edges with small
bends, neighbours' outlines lie 0.3-1 m apart (a shared side was fenced twice) and the cul-de-sac lots have spikes.
This rebuilds every lot from its real corners only:
- a corner is a turn of CORNER_TURN or more, of STREET_CORNER or more along a street (a corner lot's two streets),
  or where the outline changes between running along a street, a neighbour or nothing; except that a short side
  with no neighbour next to a street side is part of the front. So a lot's front along one street is one straight
  line, even round a road's end (user, 2026-11-25: "flatten the fences on house 5 and villa 1"), set back where it
  would cross the sidewalk;
- corners of different lots within MERGE are one point, and a corner lying on a neighbour's side is put into that
  side too, so neighbours share their sides exactly (one fence);
- a side that would cut into a sidewalk or road is moved back off it (its corners slide along the sides beside them),
  which leaves a strip of verge where the street curves;
- a street side along a straight stretch is then put exactly on the sidewalk's outer edge (user, 2026-11-25: "the
  fences should be aligned with the sidewalk"), its corners sliding along the sides beside it.
Pure numpy (Inkscape's Python runs plan_east.py).
"""
import math

import numpy as np

STREET_NEAR = 1.0       # m: an outline edge this close to a street's corridor runs along it
WIGGLE = 0.4            # m: traced jogs smaller than this are ironed out first
CORNER_TURN = 30.0      # deg
STREET_CORNER = 75.0    # deg
SHARED_NEAR = 1.5       # m: an outline edge this close to another lot's runs along that neighbour
ABSORB = 16.0           # m
MERGE = 1.5             # m
TEE = 0.8               # m
CLEAR = 0.1             # m kept between a fence line and a sidewalk / road
FLAT_TURN = 6.0         # deg: a corner turning less than this is taken out at the end
ALIGN_SPREAD = 0.6      # m: a street side goes onto the sidewalk's edge where its street runs this straight along it
ALIGN_TURN = 20.0       # deg: ... and this near parallel to it
ALIGN_MOVE = 9.0        # m: the most a corner moves to get there


def _seg_dist(p, a, b):
    d = b - a
    t = max(0.0, min(1.0, float(np.dot(p - a, d) / (np.dot(d, d) or 1e-9))))
    return float(np.linalg.norm(p - a - t * d)), t


def road_gap(p, roads):
    """How far p is outside every road's corridor (`roads`: [(points, reach from the centreline)]); < 0 inside."""
    return min(_seg_dist(p, a, b)[0] - reach for pts, reach in roads for a, b in zip(pts, pts[1:]))


def _turn(u, v):
    return math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], float(np.dot(u, v))))


def _despike(q):
    """Drop doubled points, needle spikes (a turn of nearly 180°) and the raster's small jogs (a point within WIGGLE
    of the line through its neighbours, the flattest first)."""
    q = [np.array(p, float) for p in q]
    again = True
    while again and len(q) > 3:
        again = False
        for k in range(len(q)):
            a, p, b = q[k - 1], q[k], q[(k + 1) % len(q)]
            if np.linalg.norm(p - a) < 0.05 or abs(_turn(p - a, b - p)) > 150.0:
                del q[k]
                again = True
                break
    while len(q) > 3:
        off = [_seg_dist(q[k], q[k - 1], q[(k + 1) % len(q)])[0] for k in range(len(q))]
        k = int(np.argmin(off))
        if off[k] >= WIGGLE:
            break
        del q[k]
    return q


def _poly_dist(p, poly):
    return min(_seg_dist(p, poly[i], poly[(i + 1) % len(poly)])[0] for i in range(len(poly)))


def _corners(q, roads, others):
    """A lot's corner vertices, and which edges are its street front.

    The outline is cut into sides where it turns CORNER_TURN or more (STREET_CORNER along a street) or changes
    between running along a street, a neighbour (`others`: their outlines) or nothing. A side with no neighbour,
    shorter than ABSORB, next to a street side joins the front with no corner between: the bits that run round a
    road's end (House 5, Villa 1) or past the end of a street (House 4) become part of one straight front."""
    n = len(q)

    def along(k, near):
        return all(near(q[k] + (q[(k + 1) % n] - q[k]) * t) for t in (0.25, 0.5, 0.75))

    cls = ["street" if along(k, lambda p: road_gap(p, roads) < STREET_NEAR)
           else "shared" if along(k, lambda p: any(_poly_dist(p, o) < SHARED_NEAR for o in others))
           else "free" for k in range(n)]
    turn = [abs(_turn(q[k] - q[k - 1], q[(k + 1) % n] - q[k])) for k in range(n)]
    cuts = [k for k in range(n)
            if cls[k - 1] != cls[k] or turn[k] >= (STREET_CORNER if cls[k] == "street" else CORNER_TURN)]
    if not cuts:
        return [0], [c == "street" for c in cls]
    sides = [(s, cuts[(i + 1) % len(cuts)]) for i, s in enumerate(cuts)]
    m = len(sides)

    def edges(i):
        s, e = sides[i]
        return [(s + j) % n for j in range((e - s) % n or n)]

    def heading(i):
        s, e = sides[i]
        return q[e] - q[s]

    kinds = [cls[s] for s, _ in sides]
    front = [k == "street" for k in kinds]
    for i in range(m):
        if kinds[i] != "free" or sum(np.linalg.norm(q[(k + 1) % n] - q[k]) for k in edges(i)) >= ABSORB:
            continue
        before, after = kinds[i - 1] == "street", kinds[(i + 1) % m] == "street"
        if before and after and abs(_turn(heading(i - 1), heading((i + 1) % m))) >= STREET_CORNER:
            continue                                  # a corner lot's corner: keep it
        front[i] = before or after
    keep = [s for i, (s, _) in enumerate(sides)
            if not (front[i] and front[i - 1] and "free" in (kinds[i], kinds[i - 1]))]
    flags = [False] * n
    for i in range(m):
        for k in edges(i):
            flags[k] = front[i]
    return keep or [cuts[0]], flags


def _inward(poly_pts, a, b):
    """The unit normal of side a-b pointing into the polygon."""
    area = sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(poly_pts, poly_pts[1:] + poly_pts[:1]))
    d = (b - a) / (np.linalg.norm(b - a) or 1.0)
    left = np.array([-d[1], d[0]])
    return left if area > 0 else -left


def _dense(pts, step=1.0):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(np.linalg.norm(b - a) / step))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return np.array(out)


def _street_line(a, b, inward, roads):
    """The sidewalk's outer edge beside side a-b, as (point, direction), when one kind of street (one corridor
    width) runs along the whole side, straight (its centreline within ALIGN_SPREAD of a line) and near parallel;
    else None. The line just clears the corridor where it bulges most toward the lot."""
    L = float(np.linalg.norm(b - a))
    u = (b - a) / L
    picks, reaches = [], set()
    for pts, r in roads:
        q = _dense(pts)
        t, off = (q - a) @ u, (q - a) @ -inward
        sel = (t > 0.0) & (t < L) & (off > 0) & (off < r + 3.0)
        if sel.sum() >= 2:
            picks.append(q[sel])
            reaches.add(r)
    if not picks or len(reaches) != 1:
        return None
    P = np.vstack(picks)
    t = (P - a) @ u
    if t.max() - t.min() < 0.7 * L - 2.0:                    # the street doesn't run along the whole side
        return None
    m = P.mean(0)
    v = np.linalg.svd(P - m)[2][0]
    nv = np.array([-v[1], v[0]])
    nv = nv if np.dot(nv, inward) > 0 else -nv
    h = (P - m) @ nv
    if h.max() - h.min() > ALIGN_SPREAD or abs(float(np.dot(v, u))) < math.cos(math.radians(ALIGN_TURN)):
        return None
    return m + nv * (h.max() + reaches.pop() + CLEAR), v


def _meet(p, v, a, b):
    """Where the line through p along v meets the line through a and b (None if they run near parallel)."""
    e = b - a
    den = v[0] * e[1] - v[1] * e[0]
    if abs(den) < math.sin(math.radians(15.0)) * float(np.linalg.norm(e)):
        return None
    w = a - p
    return p + v * ((w[0] * e[1] - w[1] * e[0]) / den)


def _align_streets(seqs, nodes, roads, log):
    """User, 2026-11-25 (Houses 4-6): "the fences should be aligned with the sidewalk". A street side along a
    straight stretch goes exactly onto the sidewalk's outer edge (CLEAR off it); its corners slide along the sides
    beside it (so a corner shared with a neighbour stays shared), or straight across where those run parallel."""
    done, worst = 0, 0.0
    for _ in range(2):                                # twice: a corner lot's two street sides meet in their corner
        for seq in seqs:
            m = len(seq)
            for j in range(m):
                if not seq[j][1]:
                    continue
                ia, ib = seq[j][0], seq[(j + 1) % m][0]
                a, b = nodes[ia], nodes[ib]
                if np.linalg.norm(b - a) < 2.0:
                    continue
                line = _street_line(a, b, _inward([nodes[n] for n, _ in seq], a, b), roads)
                if line is None:
                    continue
                p, v = line
                new = []
                for node, other in ((ia, seq[j - 1][0]), (ib, seq[(j + 2) % m][0])):
                    q = _meet(p, v, nodes[other], nodes[node])
                    if q is None:                     # the side beside it runs along: straight across onto the line
                        q = p + v * float(np.dot(nodes[node] - p, v))
                    new.append(q)
                moves = [float(np.linalg.norm(q - nodes[n])) for q, n in zip(new, (ia, ib))]
                if max(moves) > ALIGN_MOVE:
                    continue
                nodes[ia], nodes[ib] = new
                worst = max([worst] + moves)
                done += 1
    log("street sides on the sidewalk's edge: %d moves, the largest %.1f m" % (done, worst))


def straighten(outlines, roads, log=print):
    """`outlines`: the lots' traced outlines (world m); `roads`: [(centreline points, corridor half-width)].
    Returns the straight outlines, in the same order."""
    roads = [(np.array(p, float), r) for p, r in roads]
    nodes, members = [], []                           # node positions, and the points merged into each
    seqs = []                                         # per lot: [(node, the side after it runs along a street)]
    raw = [np.array(o, float) for o in outlines]
    for li, o in enumerate(outlines):
        q = _despike(o)
        ks, street = _corners(q, roads, [r for j, r in enumerate(raw) if j != li])
        seq = []
        for k in ks:
            p = q[k]
            near = [(float(np.linalg.norm(nodes[i] - p)), i) for i in range(len(nodes))]
            near = [c for c in near if c[0] < MERGE]
            if near:
                i = min(near)[1]
                members[i].append(p)
                nodes[i] = np.mean(members[i], axis=0)
            else:
                nodes.append(p.copy())
                members.append([p])
                i = len(nodes) - 1
            if seq and seq[-1][0] == i:
                seq[-1] = (i, street[k])
            else:
                seq.append((i, street[k]))
        while len(seq) > 1 and seq[0][0] == seq[-1][0]:
            seq.pop()
        seqs.append(seq)

    # a corner on a neighbour's side goes into that side
    for ni, p in enumerate(nodes):
        for seq in seqs:
            if any(n == ni for n, _ in seq):
                continue
            for j in range(len(seq)):
                a, b = nodes[seq[j][0]], nodes[seq[(j + 1) % len(seq)][0]]
                d, t = _seg_dist(p, a, b)
                if d < TEE and np.linalg.norm(p - a) > MERGE and np.linalg.norm(p - b) > MERGE:
                    seq.insert(j + 1, (ni, seq[j][1]))
                    break

    # sides off the sidewalks and roads
    moved = np.zeros(len(nodes))
    for _ in range(80):                               # small steps: a front pushed back off a turning circle
        worst = 0.0
        for seq in seqs:
            pts = [nodes[n] for n, _ in seq]
            m = len(seq)
            for j in range(m):
                ia, ib = seq[j][0], seq[(j + 1) % m][0]
                a, b = nodes[ia], nodes[ib]
                L = float(np.linalg.norm(b - a))
                ts = np.linspace(0, 1, max(2, int(L / 0.5) + 1))
                if not seq[j][1]:              # not a street side: its corners are the street sides' business
                    edge = min(0.45, 1.0 / max(L, 1e-6))
                    ts = ts[(ts > edge) & (ts < 1 - edge)]
                    if not len(ts):
                        continue
                gap = min(road_gap(a + (b - a) * t, roads) for t in ts)
                need = CLEAR - gap
                if need <= 0.005:
                    continue
                worst = max(worst, need)
                inward = _inward(pts, a, b)
                for node, other, other_street in ((ia, seq[j - 1][0], seq[j - 1][1]),
                                                  (ib, seq[(j + 2) % m][0], seq[(j + 1) % m][1])):
                    p, o = nodes[node], nodes[other]
                    along = (o - p) / (np.linalg.norm(o - p) or 1.0)
                    sin = float(np.dot(along, inward))
                    if not other_street and sin > 0.2:        # slide along the side beside it
                        step = min(need / sin, 1.0, max(np.linalg.norm(o - p) - 0.5, 0.0))
                        nodes[node] = p + along * step
                    else:
                        step = need
                        nodes[node] = p + inward * step
                    moved[node] += step
        if worst <= 0.005:
            break
    else:
        log("WARNING: some lot sides still touch a sidewalk or road (%.2f m)" % worst)
    _align_streets(seqs, nodes, roads, log)

    # last: a corner that hardly turns goes (or, if a neighbour's corner, onto the straight line)
    again = True
    while again:
        again = False
        for seq in seqs:
            m = len(seq)
            for j in range(m):
                a, v, b = nodes[seq[j - 1][0]], nodes[seq[j][0]], nodes[seq[(j + 1) % m][0]]
                if m <= 3 or abs(_turn(v - a, b - v)) >= FLAT_TURN:
                    continue
                if sum(any(n == seq[j][0] for n, _ in s) for s in seqs) > 1:
                    _, t = _seg_dist(v, a, b)
                    nodes[seq[j][0]] = a + (b - a) * t
                else:
                    del seq[j]
                    again = True
                    break

    out = [[tuple(round(float(v), 2) for v in nodes[n]) for n, _ in seq] for seq in seqs]
    log("lots straightened: %d -> %d corners; %d corners moved off the sidewalks (at most %.1f m)" % (
        sum(len(o) for o in outlines), sum(len(o) for o in out), int((moved > 0.01).sum()), moved.max()))
    return out
