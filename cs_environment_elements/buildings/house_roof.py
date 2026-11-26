"""Roofs for the plain house: gable, hip, shed and parapet."""

import math

from mathutils import Vector

from . import roof_edge
from .mesh_utils import _boxes_mesh, _obj, _paint_by_normal, _solid


# --------------------------------------------------------------------------
# Roofs (house-centred coordinates, z0 = top of the top ceiling slab)
# --------------------------------------------------------------------------

def _prism(poly_yz, x0, x1, base=0):
    """Convex (y, z) polygon extruded along X from x0 to x1 -> (verts, faces)."""
    n = len(poly_yz)
    verts = [(x0, y, z) for y, z in poly_yz] + [(x1, y, z) for y, z in poly_yz]
    faces = [[base + i for i in range(n)], [base + n + i for i in reversed(range(n))]]
    faces += [[base + i, base + (i + 1) % n, base + n + (i + 1) % n, base + n + i] for i in range(n)]
    return verts, faces


def _merge_parts(parts):
    verts, faces = [], []
    for v, f in parts:
        b = len(verts)
        verts += v
        faces += [[b + i for i in face] for face in f]
    return verts, faces


def _roof_geometry(kind, hx, hy, z0, pitch, o, t, te):
    """Roof and infill-wall solids with the ridge along X.

    hx / hy: half the outer footprint along / across the ridge.
    Returns (roof (verts, faces), walls (verts, faces) or None).
    """
    tn = math.tan(math.radians(pitch))
    dt = t / math.cos(math.radians(pitch))
    X, Y = hx + o, hy + o
    walls = None

    if kind == "GABLE":
        zE, zR = z0 - o * tn, z0 + hy * tn
        b = [(-X, -Y, zE), (X, -Y, zE), (X, Y, zE), (-X, Y, zE), (-X, 0, zR), (X, 0, zR)]
        verts = b + [(x, y, z + dt) for x, y, z in b]
        faces = [
            [6, 7, 11, 10], [10, 11, 8, 9],          # top slopes
            [0, 4, 5, 1], [4, 3, 2, 5],              # undersides
            [0, 1, 7, 6], [2, 3, 9, 8],              # eave fascias
            [0, 6, 10, 4], [4, 10, 9, 3],            # verge, -X end
            [1, 5, 11, 7], [5, 2, 8, 11],            # verge, +X end
        ]
        tri = [(-hy, z0), (hy, z0), (0.0, zR)]
        walls = _merge_parts([_prism(tri, -hx, -hx + te), _prism(tri, hx - te, hx)])
        return (verts, faces), walls

    if kind == "HIP":
        zE = z0 - o * tn
        zR = zE + Y * tn
        rx = X - Y
        b = [(-X, -Y, zE), (X, -Y, zE), (X, Y, zE), (-X, Y, zE)]
        if rx > 1e-3:
            b += [(-rx, 0, zR), (rx, 0, zR)]
            n = 6
            top_faces = [[0, 1, 5, 4], [2, 3, 4, 5], [3, 0, 4], [1, 2, 5]]
        else:  # square house: pyramid
            b += [(0, 0, zR)]
            n = 5
            top_faces = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]]
        verts = b + [(x, y, z + dt) for x, y, z in b]
        faces = [[i + n for i in f] for f in top_faces] + [list(reversed(f)) for f in top_faces]
        faces += [[i, (i + 1) % 4, (i + 1) % 4 + n, i + n] for i in range(4)]
        return (verts, faces), None

    if kind == "SHED":
        zL = z0 - o * tn
        zH = zL + 2 * Y * tn
        b = [(-X, -Y, zL), (X, -Y, zL), (X, Y, zH), (-X, Y, zH)]
        verts = b + [(x, y, z + dt) for x, y, z in b]
        faces = [[4, 5, 6, 7], [3, 2, 1, 0]] + [[i, (i + 1) % 4, (i + 1) % 4 + 4, i + 4] for i in range(4)]
        under = lambda y: z0 + (y + hy) * tn  # roof underside height over the footprint
        tri = [(-hy, z0), (hy, z0), (hy, under(hy))]
        high = [(hy - te, z0), (hy, z0), (hy, under(hy)), (hy - te, under(hy - te))]
        walls = _merge_parts([
            _prism(tri, -hx, -hx + te), _prism(tri, hx - te, hx),
            _prism(high, -hx + te, hx - te),
        ])
        return (verts, faces), walls

    return None, None


def _build_roof(s, plan, z0, coll, root, mats, name):
    te = plan.t_ext
    if s.roof_type == "FLAT":
        return
    if s.roof_type == "PARAPET":
        hx, hy, h = plan.W / 2 + te / 2, plan.D / 2 + te / 2, s.parapet_height
        boxes = [
            (-hx, -hy, z0, hx, -hy + te, z0 + h), (-hx, hy - te, z0, hx, hy, z0 + h),
            (-hx, -hy + te, z0, -hx + te, hy - te, z0 + h), (hx - te, -hy + te, z0, hx, hy - te, z0 + h),
        ]
        me = _paint_by_normal(_boxes_mesh(f"{name}_Parapet", boxes, Vector()),
                              mats["roof_flat"], mats["wall_out"], mats["wall_out"])  # concrete coping on top
        _obj(f"{name}_Parapet", me, coll, root)
        return

    long_x = plan.W >= plan.D
    along_x = long_x if (s.ridge_dir == "LONG" or s.roof_type == "HIP") else not long_x
    ox, oy = plan.W / 2 + te / 2, plan.D / 2 + te / 2
    hx, hy = (ox, oy) if along_x else (oy, ox)

    roof, walls = _roof_geometry(s.roof_type, hx, hy, z0, s.roof_pitch, s.roof_overhang, s.roof_thickness, te)
    if roof is None:
        return

    def orient(vf):
        v, f = vf
        if not along_x:  # built with the ridge on X; swap axes to put it on Y
            v = [(y, x, z) for x, y, z in v]
        return v, f

    # Tiles on top, the roof's edge strip on the edges, painted soffit boards underneath
    me = roof_edge.paint(_solid(f"{name}_Roof", *orient(roof)), mats)
    _obj(f"{name}_Roof", me, coll, root)
    roof_edge.edge_uvs(me, mats)
    if walls:
        _obj(f"{name}_GableWalls", _solid(f"{name}_GableWalls", *orient(walls)), coll, root, [mats["wall_out"]])
