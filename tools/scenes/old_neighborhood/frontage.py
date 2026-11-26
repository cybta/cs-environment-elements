"""Lots by road frontage (pure Python + numpy): every side of every road (not the approach road to the bridge)
is cut into consecutive lots that touch, like the user's sketch of the old quarter.

  - each driveway of the map gets a lot ~15 m wide with the driveway near one edge (house beside it)
  - the stretches between them become road-facing lots without a driveway (12-16 m wide)
  - neighbours use the SAME dividing line, so they share one fence (the lot that has it as its side 4
    skips it); a lot inside a row shares both sides
  - fronts are FRONT (3.85 m) off the road centre line: 35 cm past the road edge
  - depth runs back to DEPTH_MAX, or half-way to the next road (the row from the other side meets it
    there), or up to the reserved playground / the water
"""
import numpy as np

from .layout import (DRIVE_HALF, FRONT, FRONT_TOL, Lot, densify, key, perimeter, polys_overlap, resample,
                     seg_dist)

STEP = 0.5
DEPTH_MAX = 20.0
DEPTH_MIN = 11.0
DRIVE_LOT_W, DRIVE_EDGE = 15.5, 3.2        # driveway lot width; driveway centre this far from one side
INFILL_MIN, INFILL_TARGET = 11.0, 14.0
BACK_GAP = 0.3                             # half the gap between two rows' back fences


def _inside(p, poly):
    """Point (2,) in convex CCW polygon."""
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        if (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) < 0:
            return False
    return True


class Row:
    """One side of one road chain, sampled every STEP metres."""

    def __init__(self, net, line, side, blocked, water):
        self.pts, self.tans, self.total = resample(densify(line, STEP), STEP)
        self.side = side
        self.n = np.stack([-self.tans[:, 1], self.tans[:, 0]], -1) * side
        self.front = self.pts + self.n * FRONT
        ok = seg_dist(self.front, net.road_seg) >= FRONT - FRONT_TOL
        if water is not None:
            ok &= ~water(self.front)
        for poly in blocked:
            ok &= ~np.array([_inside(p, poly) for p in self.front])
        self.ok = ok
        self.net, self.blocked, self.water = net, blocked, water
        self._depth = {}

    def s_of(self, i):
        return i * STEP

    def depth(self, i):
        """How deep a lot may reach behind front point i."""
        if i in self._depth:
            return self._depth[i]
        f, n = self.front[i], self.n[i]
        ts = np.arange(0.5, 2 * DEPTH_MAX + 4, 0.5)
        ray = f[None] + n[None] * ts[:, None]
        d = DEPTH_MAX
        hit = np.nonzero(seg_dist(ray, self.net.road_seg) < FRONT + 0.05)[0]
        if len(hit):
            d = min(d, ts[hit[0]] / 2 - BACK_GAP)            # meet the row from the other road half-way
        for poly in self.blocked:
            inside = np.nonzero([_inside(p, poly) for p in ray])[0]
            if len(inside):
                d = min(d, ts[inside[0]] - 1.5)
        if self.water is not None:
            wet = np.nonzero(self.water(ray))[0]
            if len(wet):
                d = min(d, ts[wet[0]] - 2.0)
        self._depth[i] = d
        return d

    def corner_pair(self, i, depth, off=0.0):
        f = self.front[i] + self.n[i] * off
        return f, f + self.n[i] * depth


def _runs(ok):
    """[(i0, i1)] index runs where ok is True."""
    runs, start = [], None
    for i, v in enumerate(ok):
        if v and start is None:
            start = i
        if not v and start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(ok) - 1))
    return runs


def frontage_lots(net, hero=None, water=None, blocked=(), log=print):
    """-> list of Lot (quads; shared sides in Lot.skip). `hero`: the existing cottage's lot is kept empty."""
    anchor = np.array(net.data["anchor"], float)
    drives = net.driveways()
    hero_i = None
    if hero is not None:
        hero_i = int(np.argmin([np.linalg.norm(e - np.array(hero)) for e, _, _ in drives]))
    lots = []
    for line in net.road_chains():
        if np.linalg.norm(line - anchor, axis=1).min() < 1.0:
            continue                                         # the approach road to the bridge stays open
        node_keys = [key(p) for p in line]
        for side in (1, -1):
            row = Row(net, line, side, list(blocked), water)
            # driveways leaving this chain on this side, at their arclength along it
            cum = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))])
            anchors = []
            for k, (e, j, path) in enumerate(drives):
                kj = key(j)
                if kj not in node_keys:
                    continue
                s = float(cum[node_keys.index(kj)])
                i = min(int(round(s / STEP)), len(row.pts) - 1)
                if float(np.dot(e - j, row.n[i])) <= 0:
                    continue
                anchors.append((s, k, e, j, path))
            anchors.sort(key=lambda a: a[0])
            lots += _cut_row(row, anchors, hero_i, len(lots), log)
    lots = _resolve_overlaps(net, lots, log)
    for k, L in enumerate(lots):
        L.idx = k
    _mark_shared(lots)
    log("frontage lots: %d (%d with a driveway, %d without), %d shared fence sides"
        % (len(lots), sum(not L.infill for L in lots), sum(L.infill for L in lots), sum(len(L.skip) for L in lots)))
    return lots


def _cut_row(row, anchors, hero_i, first, log):
    """Cut one row into lots: driveway lots around their anchors, infill between."""
    out, all_pieces = [], []
    for i0, i1 in _runs(row.ok):
        s_lo, s_hi = i0 * STEP, i1 * STEP
        mine = [a for a in anchors if s_lo + 1.0 <= a[0] <= s_hi - 1.0]
        # driveway lot intervals: driveway DRIVE_EDGE from the side facing the nearer neighbour
        iv = []
        for k, (s, *_rest) in enumerate(mine):
            prev_s = mine[k - 1][0] if k else s_lo - 1e3
            next_s = mine[k + 1][0] if k + 1 < len(mine) else s_hi + 1e3
            if s - prev_s < next_s - s:
                iv.append([s - DRIVE_EDGE, s - DRIVE_EDGE + DRIVE_LOT_W])
            else:
                iv.append([s + DRIVE_EDGE - DRIVE_LOT_W, s + DRIVE_EDGE])
        for k in range(len(iv)):                              # clip to the run and to each other
            iv[k][0], iv[k][1] = max(iv[k][0], s_lo), min(iv[k][1], s_hi)
        for k in range(len(iv) - 1):
            if iv[k][1] > iv[k + 1][0]:
                m = (iv[k][1] + iv[k + 1][0]) / 2
                iv[k][1] = iv[k + 1][0] = m
        # the gaps: infill lots, or the neighbours take them
        pieces = []                                           # (s0, s1, anchor or None)
        cursor = s_lo
        for (a, b), anc in zip(iv, mine):
            pieces += _fill(cursor, a)
            # a driveway clipped against the run's end or a neighbour moves along the road to stay
            # DRIVE_EDGE inside its lot (the map's driveway paint is then off by a metre or two)
            s_adj = min(max(anc[0], a + DRIVE_EDGE), b - DRIVE_EDGE)
            pieces.append([a, b, (s_adj,) + tuple(anc[1:])])
            cursor = b
        pieces += _fill(cursor, s_hi)
        all_pieces += _absorb(pieces)
    pieces = [(min(int(round(s0 / STEP)), len(row.pts) - 1), min(int(round(s1 / STEP)), len(row.pts) - 1), anc)
              for s0, s1, anc in all_pieces]
    off = _front_offsets(row, pieces)
    for i0, i1, anc in pieces:
        L = _make_lot(row, i0, i1, anc, first + len(out), off)
        if L is None:
            continue
        if anc is not None and anc[1] == hero_i:
            L.hero = True
        out.append(L)
    return out


def _front_offsets(row, pieces):
    """On the outside of a curve a straight front fence between two corners bulges toward the road: push
    the corners out (shared corners move for both lots) until every front keeps FRONT - FRONT_TOL."""
    off = {}
    want = FRONT - FRONT_TOL
    for _ in range(6):
        moved = False
        for i0, i1, _a in pieces:
            f0 = row.front[i0] + row.n[i0] * off.get(i0, 0.0)
            f1 = row.front[i1] + row.n[i1] * off.get(i1, 0.0)
            chord = f0[None] + (f1 - f0)[None] * np.linspace(0, 1, 12)[:, None]
            deficit = want - seg_dist(chord, row.net.road_seg).min()
            if deficit > 0.005:
                for i in (i0, i1):
                    off[i] = off.get(i, 0.0) + deficit + 0.02
                moved = True
        if not moved:
            break
    return off


def _fill(a, b):
    span = b - a
    if span < 1e-6:
        return []
    if span < INFILL_MIN:
        return [[a, b, "gap"]]                                 # too small: a neighbour takes it
    n = max(1, int(round(span / INFILL_TARGET)))
    w = span / n
    return [[a + k * w, a + (k + 1) * w, None] for k in range(n)]


def _absorb(pieces):
    """Give small gaps to the neighbouring lot (a driveway lot first)."""
    out = []
    for k, p in enumerate(pieces):
        if p[2] != "gap":
            out.append(p)
            continue
        if out:
            out[-1][1] = p[1]
        elif k + 1 < len(pieces):
            pieces[k + 1][0] = p[0]
    return [p for p in out if p[1] - p[0] > 0.5]


def _make_lot(row, i0, i1, anc, idx, off):
    if i1 - i0 < 4:
        return None
    o0, o1 = off.get(i0, 0.0), off.get(i1, 0.0)
    d0, d1 = row.depth(i0) - o0, row.depth(i1) - o1
    if min(d0, d1) < DEPTH_MIN:
        return None
    f0, b0 = row.corner_pair(i0, d0, o0)
    f1, b1 = row.corner_pair(i1, d1, o1)
    im = (i0 + i1) // 2
    p, t = row.pts[im], row.tans[im]
    if anc is not None:
        _, _, e, j, path = anc
        # the driveway runs straight in from the road (the map's can leave at an angle and cross a fence)
        ij = min(int(round(anc[0] / STEP)), len(row.pts) - 1)
        length = max(float(np.linalg.norm(e - j)), FRONT + 4.0)
        j = row.pts[ij]
        e = j + row.n[ij] * length
        L = Lot(idx, e, j, np.array([j, e]), [j + row.tans[ij], j - row.tans[ij]])
    else:
        L = Lot(idx, row.front[im], p, np.array([p, row.front[im]]), [p + t, p - t])
        L.infill = True
    # corner order: front-left (-u), front-right, back-right, back-left; u = +s on side +1, -s on side -1
    quad = np.array([f0, f1, b1, b0]) if row.side > 0 else np.array([f1, f0, b0, b1])
    L.quad = quad
    L.row = (id(row), i0, i1)
    L.side = row.side
    _fit_rect(L)
    return L


def _fit_rect(L):
    """The lot's own rectangle (wl, wr, v0, v1), inside its quad: what the yard is laid out in."""
    uv = L.local(L.quad)
    L.wl = float(min(-uv[0, 0], -uv[3, 0]))
    L.wr = float(min(uv[1, 0], uv[2, 0]))
    L.v0 = float(max(uv[0, 1], uv[1, 1]))
    L.v1 = float(min(uv[2, 1], uv[3, 1]))


def _resolve_overlaps(net, lots, log):
    """Lots of different rows that overlap (round junctions) or reach into a road: pull their backs in,
    drop what gets too shallow."""
    def bad_road(L):
        per = perimeter(L.quad, 0.7)
        return seg_dist(per, net.road_seg).min() < FRONT - FRONT_TOL - 0.05

    def overlap(A, B):
        if A.row[0] == B.row[0] and (A.row[1] == B.row[2] or A.row[2] == B.row[1]):
            return False                                     # neighbours in a row share an edge
        return polys_overlap(A.quad, B.quad, 0.0)

    def shrink(L):
        if L.depth > DEPTH_MIN + 1.0:
            _pull_back(L, 1.0)
        else:
            L.ok = False
            log("lot at (%.0f, %.0f): no room, dropped" % tuple(L.quad[:2].mean(0)))

    for _ in range(40):
        changed = False
        for A in lots:
            if A.ok and bad_road(A):
                shrink(A)
                changed = True
        for A in lots:
            for B in lots:
                if A is not B and A.ok and B.ok and overlap(A, B):
                    shrink(A if A.depth >= B.depth else B)
                    changed = True
        if not changed:
            break
    return [L for L in lots if L.ok]


def _pull_back(L, by):
    q = L.quad
    for f, b in ((0, 3), (1, 2)):
        v = q[b] - q[f]
        n = np.linalg.norm(v)
        q[b] = q[f] + v / n * max(n - by, 1.0)
    _fit_rect(L)


def _mark_shared(lots):
    """Neighbours in a row share their dividing line (same front corner, same direction): ONE fence. The lot
    with the shorter side there skips it (the other one's fence covers it); nothing is skipped next to the
    existing cottage's lot, which builds no fence."""
    at = {}
    for L in lots:
        rid, i0, i1 = L.row
        side_at_i0, side_at_i1 = (4, 2) if L.side > 0 else (2, 4)
        at.setdefault((rid, i0), []).append((L, side_at_i0))
        at.setdefault((rid, i1), []).append((L, side_at_i1))
    for owners in at.values():
        if len(owners) != 2:
            continue
        (A, sa), (B, sb) = owners

        def length(L, s):
            q = L.quad
            a, b = ((1, 2) if s == 2 else (3, 0))
            return float(np.linalg.norm(q[a] - q[b]))

        if A.hero or B.hero:
            continue
        L, s, other = (A, sa, B) if length(A, sa) <= length(B, sb) else (B, sb, A)
        L.skip.add(s)
        L.shared_with = getattr(L, "shared_with", set()) | {other.idx}
        other.shared_with = getattr(other, "shared_with", set()) | {L.idx}
