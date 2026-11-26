"""Round arches for the Mediterranean villa: the wall left above a round-topped opening,
arcade heads, curved bands (arch surrounds, window frames), arched glass and doors.

Shapes are drawn in a wall's own frame first: s along the wall, w across it (0 = the
wall's centre line, + = outdoors) and z up from the storey's floor. A Wall maps them into
the plan and builds the mesh.
"""

import math

from mathutils import Vector

from .mesh_utils import _mat_index, _obj, _solid

SEG = 18            # segments in a half circle


def arc(sm, zs, r, a0, a1, n=SEG):
    """Points on the circle round (sm, zs), from angle a0 to a1 (radians, 0 = along +s, pi/2 = up)."""
    k = max(2, round(n * abs(a1 - a0) / math.pi))
    return [(sm + r * math.cos(a0 + (a1 - a0) * i / k), zs + r * math.sin(a0 + (a1 - a0) * i / k))
            for i in range(k + 1)]


def round_top(s0, s1, z0, zs):
    """Outline of a round-topped opening: jambs from z0 up to the spring zs, then a half circle."""
    return [(s0, z0), (s1, z0)] + arc((s0 + s1) / 2, zs, (s1 - s0) / 2, 0.0, math.pi)


def spandrels(s0, s1, zs, top):
    """The wall between a round arch over [s0, s1] (springing at zs) and a square head at `top`:
    two pieces when the arch touches the head, one when there is wall above its crown."""
    r, sm = (s1 - s0) / 2, (s0 + s1) / 2
    if top - (zs + r) < 1e-3:
        left = [(s0, zs), (s0, top), (sm, top)] + arc(sm, zs, r, math.pi / 2, math.pi)[1:-1]
        right = [(sm, top), (s1, top), (s1, zs)] + arc(sm, zs, r, 0.0, math.pi / 2)[1:-1]
        return [left, right]
    return [[(s1, zs), (s1, top), (s0, top), (s0, zs)] + arc(sm, zs, r, math.pi, 0.0)[1:-1]]


def ray(sm, zs, r0, r1, angle, width):
    """A straight bar from radius r0 to r1 along `angle` (a fanlight glazing bar) -> outline."""
    c, s = math.cos(angle), math.sin(angle)
    h = width / 2
    return [(sm + r0 * c + h * s, zs + r0 * s - h * c), (sm + r1 * c + h * s, zs + r1 * s - h * c),
            (sm + r1 * c - h * s, zs + r1 * s + h * c), (sm + r0 * c - h * s, zs + r0 * s + h * c)]


# --------------------------------------------------------------------------
# Solids in wall coordinates: (verts as (s, w, z), faces)
# --------------------------------------------------------------------------

def prism(poly, w0, w1):
    """An (s, z) outline pushed through the wall from w0 to w1."""
    n = len(poly)
    verts = [(s, w0, z) for s, z in poly] + [(s, w1, z) for s, z in poly]
    faces = [list(range(n)), [n + i for i in reversed(range(n))]]
    faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return verts, faces


def box(s0, s1, w0, w1, z0, z1):
    return prism([(s0, z0), (s1, z0), (s1, z1), (s0, z1)], w0, w1)


def band(sm, zs, r_in, r_out, w0, w1, a0=0.0, a1=math.pi, n=SEG):
    """A curved band between two radii (an arch surround, the head of a window frame)."""
    outer, inner = arc(sm, zs, r_out, a0, a1, n), arc(sm, zs, r_in, a0, a1, n)
    k = len(outer)
    verts = []
    for (so, zo), (si, zi) in zip(outer, inner):
        verts += [(so, w0, zo), (si, w0, zi), (so, w1, zo), (si, w1, zi)]
    faces = []
    for i in range(k - 1):
        a, b = 4 * i, 4 * (i + 1)
        faces += [[a, b, b + 1, a + 1], [a + 2, a + 3, b + 3, b + 2],      # the two faces of the wall
                  [a, a + 2, b + 2, b], [a + 1, b + 1, b + 3, a + 3]]      # outer and inner curve
    e = 4 * (k - 1)
    faces += [[0, 1, 3, 2], [e, e + 2, e + 3, e + 1]]                      # the two ends
    return verts, faces


class Wall:
    """A wall line: axis 'X' runs along x at y = coord, 'Y' along y at x = coord. `out` (+1 / -1)
    is the side facing outdoors, `z0` the storey's floor (added to every z)."""

    def __init__(self, axis, coord, out, z0=0.0):
        self.axis, self.coord, self.out, self.z0 = axis, coord, out, z0
        self.normal = Vector((0, out, 0)) if axis == "X" else Vector((out, 0, 0))

    def point(self, s, w, z):
        a = self.coord + w * self.out
        return (s, a, z + self.z0) if self.axis == "X" else (a, s, z + self.z0)

    def box(self, s0, s1, w0, w1, z0, z1):
        """The same box as (x0, y0, z0, x1, y1, z1) in the plan, for _boxes_mesh."""
        p, q = self.point(s0, w0, z0), self.point(s1, w1, z1)
        return (min(p[0], q[0]), min(p[1], q[1]), p[2], max(p[0], q[0]), max(p[1], q[1]), q[2])

    def mesh(self, name, parts, center):
        verts, faces = [], []
        for v, f in parts:
            base = len(verts)
            verts += [Vector(self.point(*p)) + center for p in v]
            faces += [[base + i for i in face] for face in f]
        return _solid(name, verts, faces)


def add(c, label, wall, parts, out_mat, in_mat=None, side_mat=None):
    """One object from wall-frame solids: faces looking outdoors get `out_mat`, indoors `in_mat`,
    the rest (reveals, the curve under an arch, tops) `side_mat` (both default to `out_mat`)."""
    if not parts:
        return None
    me = wall.mesh(f"{c.name}_{label}", parts, c.center)
    i_out = _mat_index(me, out_mat)
    i_in = _mat_index(me, in_mat or out_mat)
    i_side = _mat_index(me, side_mat or out_mat)
    for p in me.polygons:
        d = p.normal.dot(wall.normal)
        p.material_index = i_out if d > 0.7 else i_in if d < -0.7 else i_side
    return _obj(f"{c.name}_{label}", me, c.coll, c.root)
