"""Old timber quay / jetty (ref: Desktop/ref/kay.jpg): a plank deck on joists and bearers,
standing on round piles; the piles along the outside edges rise above the deck as
posts. Optional: old tyres hung on the posts as fenders, and a steel ladder down into
the water. Straight, or T-shaped (a head across the end of the stem).

Same materials as the old fence: every board, beam and pile takes a random stretch of
one real plank of the fence's plank sheet (fence_geom.Parts), the ladder is the fence's
old iron, and the tyres are plain rubber.

Local frame: origin = the shore end of the stem, at the water line. The stem runs along
+Y; the deck top is `deck_height` above the water; the piles go `water_depth` (+0.3)
below it.
"""

import math

import bpy
from mathutils import Quaternion, Vector

from . import fence_geom as fg

UP = Vector((0.0, 0.0, 1.0))
WOOD, METAL, RUBBER = 0, 1, 2
MAT_RUBBER = "C_quay_rubber"

PLANK_T = 0.045                  # deck board thickness
JOIST_H, JOIST_W = 0.17, 0.075   # joists run along the run, under the boards
BEARER_H, BEARER_W = 0.2, 0.1    # bearers run across, one at each pile station
FASCIA_H, FASCIA_T = 0.24, 0.04  # edge board hiding the joist ends
JOIST_GAP = 0.6                  # most a deck board spans between joists


def rubber_material():
    mat = bpy.data.materials.get(MAT_RUBBER)
    if mat:
        return mat
    mat = bpy.data.materials.new(MAT_RUBBER)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.022, 0.022, 0.022, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.9
    mat.diffuse_color = (0.022, 0.022, 0.022, 1.0)
    return mat


def materials():
    return [fg.wood_material(), fg.metal_material(), rubber_material()]


# --------------------------------------------------------------------------
# Layout: the deck as straight runs
# --------------------------------------------------------------------------

class Run:
    """One rectangular run of deck, x0..x1 by y0..y1. `s` runs along it (its length, the
    way the joists go), `t` across it (the way the deck boards are laid)."""

    def __init__(self, x0, x1, y0, y1, axis):
        self.x0, self.x1, self.y0, self.y1, self.axis = x0, x1, y0, y1, axis
        if axis == "Y":
            self.along, self.across = Vector((0, 1, 0)), Vector((1, 0, 0))
            self.s, self.t = (y0, y1), (x0, x1)
        else:
            self.along, self.across = Vector((1, 0, 0)), Vector((0, 1, 0))
            self.s, self.t = (x0, x1), (y0, y1)
        self.stations = []

    def at(self, s, t, z=0.0):
        return Vector((t, s, z)) if self.axis == "Y" else Vector((s, t, z))

    def contains(self, p, eps=1e-4):
        return self.x0 - eps <= p.x <= self.x1 + eps and self.y0 - eps <= p.y <= self.y1 + eps

    def edges(self):
        """(start, end, outward normal) of its four sides."""
        a, b = Vector((self.x0, self.y0, 0)), Vector((self.x1, self.y0, 0))
        c, d = Vector((self.x1, self.y1, 0)), Vector((self.x0, self.y1, 0))
        return [(a, b, Vector((0, -1, 0))), (b, c, Vector((1, 0, 0))),
                (c, d, Vector((0, 1, 0))), (d, a, Vector((-1, 0, 0)))]


def runs(g):
    """The stem, plus the head across its far end for a T (as wide as the stem is)."""
    w, length = g.width, g.length
    out = [Run(-w / 2, w / 2, 0.0, length, "Y")]
    if g.shape == "T" and g.left + g.right > 0.01:
        out.append(Run(-w / 2 - g.left, w / 2 + g.right, length, length + w, "X"))
    return out


def fillet(pts, bend, seg=5):
    """Polyline with each inner corner rounded to radius `bend` (bent pipe)."""
    pts = [Vector(p) for p in pts]
    out = [pts[0]]
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        d1, d2 = (a - b).normalized(), (c - b).normalized()
        ang = d1.angle(d2)
        if ang > math.pi - 1e-3:
            out.append(b)
            continue
        r = min(bend, (a - b).length * 0.49 * math.tan(ang / 2), (c - b).length * 0.49 * math.tan(ang / 2))
        ctr = b + (d1 + d2).normalized() * (r / math.sin(ang / 2))
        v0, v1 = b + d1 * (r / math.tan(ang / 2)) - ctr, b + d2 * (r / math.tan(ang / 2)) - ctr
        axis = v0.cross(v1).normalized()
        sweep = v0.angle(v1)
        out += [ctr + Quaternion(axis, sweep * k / seg) @ v0 for k in range(seg + 1)]
    out.append(pts[-1])
    return out


# --------------------------------------------------------------------------
# Builder
# --------------------------------------------------------------------------

class QuayBuilder:
    def __init__(self, g, rng):
        self.g, self.rng = g, rng
        self.parts = fg.Parts(rng)
        self.smooth = []                    # face indices shaded smooth (piles, pipes, tyres)
        self.runs = runs(g)
        self.top = g.deck_height
        self.piles = []                     # [position (z=0), outward normal or None]

    def outside(self, p):
        return not any(r.contains(p) for r in self.runs)

    def build(self):
        for r in self.runs:
            self.deck(r)
            self.frame(r)
        self.fascia()
        tops = [self.pile(p, n) for p, n in self.piles]
        if self.g.tyres:
            self.tyres(tops)
        if self.g.ladder:
            self.ladder()
        return self

    # -- deck ---------------------------------------------------------------
    def deck(self, r):
        g, rng = self.g, self.rng
        (s0, s1), (t0, t1) = r.s, r.t
        s = s0
        while s < s1 - 0.03:
            w = min(g.plank_width * rng.uniform(0.85, 1.15), s1 - s)
            if w < 0.06:
                break
            if rng.random() >= g.missing:
                lo, hi = t0 + rng.uniform(0, 0.015), t1 - rng.uniform(0, 0.015)     # ragged ends
                dz = rng.uniform(-0.008, 0.002) * (1 + g.wear * 2)                  # boards sag a little
                c = r.at(s + w / 2, (lo + hi) / 2, self.top - PLANK_T / 2 + dz)
                self.parts.box(c, r.across, r.along, hi - lo, w, PLANK_T, WOOD)
            s += w + g.gap

    def frame(self, r):
        """Joists along the run, a bearer across it at each pile station, and its piles."""
        g = self.g
        (s0, s1), (t0, t1) = r.s, r.t
        n = max(2, math.ceil((s1 - s0 - 0.2) / g.pile_spacing) + 1)
        r.stations = [s0 + 0.1 + i * (s1 - s0 - 0.2) / (n - 1) for i in range(n)]
        nj = max(2, math.ceil((t1 - t0 - 0.16) / JOIST_GAP) + 1)
        zj = self.top - PLANK_T - JOIST_H / 2
        for i in range(nj):
            t = t0 + 0.08 + i * (t1 - t0 - 0.16) / (nj - 1)
            self.parts.box(r.at((s0 + s1) / 2, t, zj), r.along, UP, s1 - s0, JOIST_H, JOIST_W, WOOD)
        zb = self.top - PLANK_T - JOIST_H - BEARER_H / 2
        reach = FASCIA_T + g.pile_radius
        for s in r.stations:
            self.parts.box(r.at(s, (t0 + t1) / 2, zb), r.across, UP, t1 - t0 + 2 * reach, BEARER_H, BEARER_W, WOOD)
            for t, sign in ((t0, -1), (t1, 1)):
                nrm = r.across * sign
                e = r.at(s, t)
                if self.outside(e + nrm * 0.05):            # outer edge: pile outside the edge board
                    self.add_pile(e + nrm * (reach + 0.005), nrm)
                else:                                       # where two runs meet: under the deck
                    self.add_pile(e, None)
            if t1 - t0 > 3.2:                               # a wide deck gets a middle row
                self.add_pile(r.at(s, (t0 + t1) / 2), None)

    def add_pile(self, p, nrm):
        for k, (q, qn) in enumerate(self.piles):
            if (q - p).length < 0.45:
                if nrm is not None and qn is None:          # an outer pile wins
                    self.piles[k] = [p, nrm]
                return
        self.piles.append([p, nrm])

    def fascia(self):
        """Edge boards along every outside stretch of every run."""
        z = self.top - FASCIA_H / 2
        cuts = sorted({c for r in self.runs for c in (r.x0, r.x1, r.y0, r.y1)})
        for r in self.runs:
            for a, b, nrm in r.edges():
                d = b - a
                length = d.length
                d /= length
                ts = sorted({0.0, length} | {(c - (a.x if abs(d.x) > 0.5 else a.y)) * (d.x + d.y)
                                             for c in cuts})
                ts = [t for t in ts if -1e-6 <= t <= length + 1e-6]
                spans = []
                for t0, t1 in zip(ts, ts[1:]):
                    if t1 - t0 > 1e-3 and self.outside(a + d * ((t0 + t1) / 2) + nrm * 0.05):
                        if spans and abs(spans[-1][1] - t0) < 1e-4:
                            spans[-1][1] = t1
                        else:
                            spans.append([t0, t1])
                for t0, t1 in spans:
                    # boards along X run on past an outside corner to cover the end of the
                    # board along Y there (butt joint: no overlapping faces to flicker)
                    if abs(d.x) > 0.5:
                        if self.outside(a + d * (t0 - 0.02) - nrm * 0.02):
                            t0 -= FASCIA_T
                        if self.outside(a + d * (t1 + 0.02) - nrm * 0.02):
                            t1 += FASCIA_T
                    mid = a + d * ((t0 + t1) / 2) + nrm * (FASCIA_T / 2)
                    mid.z = z
                    self.parts.box(mid, d, UP, t1 - t0, FASCIA_H, FASCIA_T, WOOD)

    # -- piles, posts -----------------------------------------------------------
    def pile(self, p, nrm):
        """A round pile from below the bed up to under the deck, or (outer, with posts)
        on up past it as a post. Returns its top (point, radius)."""
        g, rng = self.g, self.rng
        rad = g.pile_radius * rng.uniform(0.88, 1.1)
        if nrm is not None and g.posts:
            top = self.top + g.post_height * rng.uniform(0.7, 1.25)
        elif nrm is not None:
            top = self.top - 0.02
        else:
            top = self.top - PLANK_T - JOIST_H
        bottom = -g.water_depth - 0.3
        lean = Vector((rng.gauss(0, 0.012), rng.gauss(0, 0.012), 0)) * (1 + g.wear * 2)
        base = p + Vector((0, 0, bottom))
        tip = p + lean * (top - bottom) + Vector((0, 0, top))
        self.tube([base, tip], rad, segs=10, mat=WOOD, uv="plank", cap_start=False)
        return tip, rad, nrm

    def tube(self, pts, r, segs=8, mat=METAL, uv="metric", cap_start=True, cap_end=True):
        """Round bar through `pts` (shared verts, shaded smooth). uv="plank" lays one fence
        plank along it (piles); "metric" maps it in metres."""
        P = self.parts
        pts = [Vector(p) for p in pts]
        n = len(pts)
        tans = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
        nrm = tans[0].orthogonal().normalized()
        rings, dist = [], [0.0]
        for i, p in enumerate(pts):
            t = tans[i]
            nrm = (nrm - t * nrm.dot(t)).normalized()
            b = t.cross(nrm)
            rings.append(len(P.verts))
            for k in range(segs):
                a = 2 * math.pi * k / segs
                P.verts.append(tuple(p + (nrm * math.cos(a) + b * math.sin(a)) * r))
            if i:
                dist.append(dist[-1] + (p - pts[i - 1]).length)
        circ = 2 * math.pi * r
        if uv == "plank":
            u0, u1, v0, v1 = self.rng.choice(fg.STRIPS)
            span = (v1 - v0) * fg._IMG_H / fg._IMG_W / circ          # U per metre at true aspect
            du = min(dist[-1] * span, u1 - u0)
            us = self.rng.uniform(u0, u1 - du)
            uv_of = lambda d, k: (us + du * d / max(dist[-1], 1e-6), v0 + (v1 - v0) * k / segs)   # noqa: E731
            hv = (v1 - v0) * 0.4                                       # end grain: a disc inside the plank
            cap_c, cap_r = ((us + du / 2, (v0 + v1) / 2), (hv * fg._IMG_H / fg._IMG_W, hv))
        else:
            uv_of = lambda d, k: (d, circ * k / segs)                  # noqa: E731
            cap_c, cap_r = (0.0, 0.0), (r, r)
        for i in range(n - 1):
            A, B = rings[i], rings[i + 1]
            for k in range(segs):
                k2 = (k + 1) % segs
                self.smooth.append(len(P.faces))
                P.faces.append([A + k, A + k2, B + k2, B + k])
                P.uvs.append([uv_of(dist[i], k), uv_of(dist[i], k + 1), uv_of(dist[i + 1], k + 1),
                              uv_of(dist[i + 1], k)])
                P.mats.append(mat)
        for ring, on, flip in ((rings[0], cap_start, True), (rings[-1], cap_end, False)):
            if not on:
                continue
            idx = [ring + k for k in range(segs)]
            if flip:
                idx.reverse()
            P.faces.append(idx)
            ks = range(segs - 1, -1, -1) if flip else range(segs)
            P.uvs.append([(cap_c[0] + cap_r[0] * math.cos(2 * math.pi * k / segs),
                           cap_c[1] + cap_r[1] * math.sin(2 * math.pi * k / segs)) for k in ks])
            P.mats.append(mat)

    # -- extras -----------------------------------------------------------------
    def torus(self, center, axis, R, r, seg=16, sides=8, mat=RUBBER):
        P = self.parts
        axis = Vector(axis).normalized()
        u = axis.orthogonal().normalized()
        v = axis.cross(u)
        base = len(P.verts)
        for i in range(seg):
            a = 2 * math.pi * i / seg
            radial = u * math.cos(a) + v * math.sin(a)
            for j in range(sides):
                b = 2 * math.pi * j / sides
                P.verts.append(tuple(center + radial * (R + r * math.cos(b)) + axis * (r * math.sin(b))))
        for i in range(seg):
            i2 = (i + 1) % seg
            for j in range(sides):
                j2 = (j + 1) % sides
                self.smooth.append(len(P.faces))
                P.faces.append([base + i * sides + j, base + i2 * sides + j, base + i2 * sides + j2,
                                base + i * sides + j2])
                P.uvs.append([(i / seg, j / sides), (i2 / seg, j / sides), (i2 / seg, j2 / sides),
                              (i / seg, j2 / sides)])
                P.mats.append(mat)

    def tyres(self, tops):
        """Old tyres hung flat against the outside of evenly picked outer posts."""
        outer = [t for t in tops if t[2] is not None]
        if not outer:
            return
        count = min(self.g.tyres, len(outer))
        for k in range(count):
            tip, rad, nrm = outer[int((k + 0.5) * len(outer) / count)]
            c = Vector((tip.x, tip.y, self.top - 0.18)) + nrm * (rad + 0.1)
            self.torus(c, nrm, 0.3, 0.1)

    def ladder(self):
        """Steel ladder on the stem's left or right edge, between two piles: rails from
        below the water up into hoops that come down onto the deck, rungs every 0.3 m."""
        g = self.g
        r = self.runs[0]
        st = r.stations
        want = r.s[0] + (r.s[1] - r.s[0]) * g.ladder_pos
        mids = [(a + b) / 2 for a, b in zip(st, st[1:])] or [want]
        s = min(mids, key=lambda m: abs(m - want))
        sign = -1 if g.ladder_side == "LEFT" else 1
        nrm = r.across * sign
        t = r.t[1] if sign > 0 else r.t[0]
        hoop = self.top + 0.6
        rails = []
        for off in (-0.22, 0.22):
            e = r.at(s + off, t)
            out, inn = e + nrm * (FASCIA_T + 0.06), e - nrm * 0.3
            low = out + Vector((0, 0, -min(0.9, g.water_depth)))
            path = fillet([low, out + Vector((0, 0, hoop)), inn + Vector((0, 0, hoop)), inn + Vector((0, 0, self.top))],
                          0.14)
            self.tube(path, 0.021, segs=8, mat=METAL)
            rails.append(out)
        z = -min(0.9, g.water_depth) + 0.15
        while z < self.top - 0.15:
            a, b = rails[0] + Vector((0, 0, z)), rails[1] + Vector((0, 0, z))
            self.tube([a, b], 0.016, segs=6, mat=METAL)
            z += 0.3


def build_mesh(g, rng, name):
    """The quay as one mesh (all three materials) -> (mesh, deck length summary)."""
    q = QuayBuilder(g, rng).build()
    me = q.parts.mesh(name)
    for m in materials():
        me.materials.append(m)
    flags = [False] * len(me.polygons)
    for i in q.smooth:
        flags[i] = True
    me.polygons.foreach_set("use_smooth", flags)
    me.update()
    area = sum((r.x1 - r.x0) * (r.y1 - r.y0) for r in q.runs)
    return me, f"{area:.1f} m² deck, {len(q.piles)} piles"
