"""Raster and geometry helpers for reading and re-planning the east side (numpy + Pillow, no scipy):
morphology, connected components, outlines, hulls, rotated rectangles, and road centrelines (thinning + tracing).
Used by read_east_drawing.py and plan_east.py.
"""
import math

import numpy as np
from PIL import Image, ImageFilter


def pil_filter(m, f):
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(f)) > 127


def dilate(m, n):
    return pil_filter(m, ImageFilter.MaxFilter(n))


def erode(m, n):
    return pil_filter(m, ImageFilter.MinFilter(n))


def label(mask):
    """Connected components (4-neighbour): max-label propagation with pointer jumping. 0 = background."""
    h, w = mask.shape
    lab = np.where(mask, np.arange(1, h * w + 1, dtype=np.int64).reshape(h, w), 0)
    while True:
        new = lab.copy()
        new[1:] = np.maximum(new[1:], np.where(mask[1:], lab[:-1], 0))
        new[:-1] = np.maximum(new[:-1], np.where(mask[:-1], lab[1:], 0))
        new[:, 1:] = np.maximum(new[:, 1:], np.where(mask[:, 1:], lab[:, :-1], 0))
        new[:, :-1] = np.maximum(new[:, :-1], np.where(mask[:, :-1], lab[:, 1:], 0))
        for _ in range(6):
            new = np.where(mask, new.ravel()[np.maximum(new, 1) - 1], 0)
        if np.array_equal(new, lab):
            return lab
        lab = new


def dp(pts, eps):
    """Douglas-Peucker on an open polyline."""
    if len(pts) < 3:
        return list(pts)
    (x0, y0), (x1, y1) = pts[0], pts[-1]
    dx, dy = x1 - x0, y1 - y0
    n = math.hypot(dx, dy) or 1e-9
    far, k = -1, 0
    for i in range(1, len(pts) - 1):
        d = abs(dy * (pts[i][0] - x0) - dx * (pts[i][1] - y0)) / n
        if d > far:
            far, k = d, i
    if far <= eps:
        return [pts[0], pts[-1]]
    return dp(pts[:k + 1], eps)[:-1] + dp(pts[k:], eps)


_RING = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]    # clockwise on screen (y down)


def trace(mask):
    """The outer boundary of a mask's largest piece, as an ordered pixel loop (Moore-neighbour tracing)."""
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    sub = mask[y0:y1, x0:x1]
    lab = label(sub)
    ids, counts = np.unique(lab[lab > 0], return_counts=True)
    sub = lab == ids[np.argmax(counts)]
    h, w = sub.shape
    sy, sx = np.nonzero(sub)
    start = (int(sx[0]), int(sy[0]))                         # the top row's leftmost pixel: its west is empty
    loop, cur, back = [start], start, 4
    while len(loop) <= 4 * sub.size:                         # (a safety bound)
        for k in range(1, 9):
            d = (back + k) % 8
            nx, ny = cur[0] + _RING[d][0], cur[1] + _RING[d][1]
            if 0 <= nx < w and 0 <= ny < h and sub[ny, nx]:
                break
        else:
            break                                            # a single pixel
        if cur == start and len(loop) > 1 and (nx, ny) == loop[1]:
            break                                            # about to repeat the first move: round once
        bx, by = cur[0] + _RING[(d - 1) % 8][0], cur[1] + _RING[(d - 1) % 8][1]     # the last empty one seen
        back = _RING.index((bx - nx, by - ny))
        cur = (nx, ny)
        loop.append(cur)
    if len(loop) > 1 and loop[-1] == start:
        loop.pop()
    return [(x0 + x, y0 + y) for x, y in loop]


def outline(mk, k=1, ox=0.0, oy=0.0, eps=7.0, min_gap=9.0):
    """A shape's outline (its largest piece, traced round its boundary) as a simplified polygon. mk is on a grid of
    k px cells whose (0, 0) cell sits at (ox, oy)."""
    pts = [(ox + x * k + k / 2, oy + y * k + k / 2) for x, y in trace(mk)]
    i = max(range(len(pts)), key=lambda j: (pts[j][0] - pts[0][0]) ** 2 + (pts[j][1] - pts[0][1]) ** 2)
    poly = dp(pts[:i + 1], eps)[:-1] + dp(pts[i:] + [pts[0]], eps)[:-1]
    out = []
    for p in poly:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > min_gap:
            out.append(p)
    return out


def hull(pts):
    pts = sorted(set(pts))
    if len(pts) < 3:
        return pts

    def half(seq):
        h = []
        for p in seq:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (p[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0])) <= 0:
                h.pop()
            h.append(p)
        return h
    lo, hi = half(pts), half(pts[::-1])
    return lo[:-1] + hi[:-1]


def min_rect(mask, ox=0, oy=0):
    """The smallest rotated rectangle round a mask's pixels: centre, angle of its u axis, size along u and v."""
    edge = mask & ~erode(mask, 3)
    ys, xs = np.nonzero(edge)
    hp = np.array(hull(list(zip((xs + ox).tolist(), (ys + oy).tolist()))), float)
    best = None
    for i in range(len(hp)):
        e = hp[(i + 1) % len(hp)] - hp[i]
        a = math.atan2(e[1], e[0])
        ca, sa = math.cos(a), math.sin(a)
        u, v = hp[:, 0] * ca + hp[:, 1] * sa, -hp[:, 0] * sa + hp[:, 1] * ca
        area = (u.max() - u.min()) * (v.max() - v.min())
        if best is None or area < best[0]:
            best = (area, a, u.min(), u.max(), v.min(), v.max())
    _, a, u0, u1, v0, v1 = best
    ca, sa = math.cos(a), math.sin(a)
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    return dict(c=(cu * ca - cv * sa, cu * sa + cv * ca), a=a, w=u1 - u0, h=v1 - v0)


def corners(c, a, w, h):
    ca, sa = math.cos(a), math.sin(a)
    return [(c[0] + su * w / 2 * ca - sv * h / 2 * sa, c[1] + su * w / 2 * sa + sv * h / 2 * ca)
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def sides(r):
    """A rectangle's 4 sides: outward normal, half-length along the side, half-depth across it."""
    ca, sa = math.cos(r["a"]), math.sin(r["a"])
    return [((ca, sa), r["h"] / 2, r["w"] / 2), ((-ca, -sa), r["h"] / 2, r["w"] / 2),
            ((-sa, ca), r["w"] / 2, r["h"] / 2), ((sa, -ca), r["w"] / 2, r["h"] / 2)]


def poly_area(poly):
    return abs(sum(poly[i][0] * poly[i - 1][1] - poly[i - 1][0] * poly[i][1] for i in range(len(poly)))) / 2


# ------------------------------------------------------------------ road centrelines
def thin(mask):
    """Zhang-Suen thinning to a 1 px skeleton."""
    img = np.pad(mask.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            p2, p3, p4 = img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:]
            p5, p6, p7 = img[2:, 2:], img[2:, 1:-1], img[2:, :-2]
            p8, p9, c = img[1:-1, :-2], img[:-2, :-2], img[1:-1, 1:-1]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9, p2]
            b = sum(n.astype(np.int16) for n in nb[:8])
            a = sum(((nb[i] == 0) & (nb[i + 1] == 1)).astype(np.int16) for i in range(8))
            if step == 0:
                m = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                m = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            kill = (c == 1) & (b >= 2) & (b <= 6) & (a == 1) & m
            if kill.any():
                c[kill] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def centerlines(mask, min_spur):
    """A road mask -> its centrelines as pixel polylines [(x, y), ...] that run junction to junction (or to a free
    end). Junction pixels next to each other are one junction; spurs shorter than min_spur px are dropped."""
    sk = thin(mask)
    ys, xs = np.nonzero(sk)
    P = set(zip(xs.tolist(), ys.tolist()))
    N8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    nb = {p: [(p[0] + dx, p[1] + dy) for dx, dy in N8 if (p[0] + dx, p[1] + dy) in P] for p in P}
    node = {p for p in P if len(nb[p]) != 2}
    cid, k = {}, 0
    for p in node:
        if p in cid:
            continue
        stack, cid[p] = [p], k
        while stack:
            q = stack.pop()
            for r in nb[q]:
                if r in node and r not in cid:
                    cid[r] = k
                    stack.append(r)
        k += 1
    edges, seen = [], set()
    for p in node:
        for q in nb[p]:
            if q in node or (p, q) in seen:
                continue
            line, prev, cur = [p, q], p, q
            while cur not in node:
                nxt = [r for r in nb[cur] if r != prev]
                if len(nxt) != 1:
                    break
                prev, cur = cur, nxt[0]
                line.append(cur)
            seen.add((p, q))
            seen.add((cur, prev))
            edges.append([cid[p], cid.get(cur, -1), line])
    edges = [e for e in edges if not (e[0] == e[1] and len(e[2]) < 12)]     # junction-blob crumbs

    def degree():
        d = {}
        for a, b, _ in edges:
            d[a] = d.get(a, 0) + 1
            d[b] = d.get(b, 0) + 1
        return d

    for _ in range(4):
        d = degree()
        edges = [e for e in edges if not ((d[e[0]] == 1 or d[e[1]] == 1) and len(e[2]) < min_spur)]
        d = degree()
        for c in [c for c, n in d.items() if n == 2 and c != -1]:    # a pass-through junction: join its 2 edges
            two = [e for e in edges if c in (e[0], e[1])]
            if len(two) != 2 or two[0] is two[1] or two[0][0] == two[0][1]:
                continue
            e1, e2 = two
            l1 = e1[2] if e1[1] == c else e1[2][::-1]
            l2 = e2[2] if e2[0] == c else e2[2][::-1]
            a = e1[0] if e1[1] == c else e1[1]
            b = e2[1] if e2[0] == c else e2[0]
            edges.remove(e1)
            edges.remove(e2)
            edges.append([a, b, l1 + l2])
    return [e[2] for e in edges]
