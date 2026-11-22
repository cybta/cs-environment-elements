"""Plank-textured parts shared by the old-wood prop scripts (yard furniture, clothesline).
Every board, post or round leg takes one plank strip of the fence sheet (fence_geom), so all
old wood matches the fences and the quay.

Load with exec() after bentwood_lib / playground_lib, with `fg` (fence_geom), `rng` and the
slot index WOOD_I defined in the calling script.
"""
import math
from mathutils import Vector

def strip():
    u0, u1, v0, v1 = rng.choice(fg.STRIPS)
    return u0, u1, v0, v1

def plank(lo, hi, grain=0, bevel=0.003):
    """A board from corner lo to hi, its grain along axis `grain` (0 x, 1 y, 2 z): one fence
    plank strip, broad faces showing the whole plank width, edges a sliver, ends a patch."""
    fs = box(lo, hi, bevel=bevel, segs=1)
    lo, hi = Vector(lo), Vector(hi)
    size = hi - lo
    u0, u1, v0, v1 = strip()
    across = max((a for a in range(3) if a != grain), key=lambda a: size[a])   # the board's width
    thick = 3 - grain - across
    span = (v1 - v0) * fg._IMG_H / fg._IMG_W / max(size[across], 1e-4)        # U per metre at true aspect
    du = min(size[grain] * span, u1 - u0)
    us = rng.uniform(u0, u1 - du)
    flip = rng.random() < 0.5
    for f in fs:
        f.normal_update()
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        for l in f.loops:
            p = l.vert.co
            tg = (p[grain] - lo[grain]) / max(size[grain], 1e-6)
            ta = (p[across] - lo[across]) / max(size[across], 1e-6)
            tt = (p[thick] - lo[thick]) / max(size[thick], 1e-6)
            if ax == grain:                                   # end grain
                u, v = us + du * 0.5 + ta * 0.01, v0 + (v1 - v0) * (0.3 + 0.4 * tt)
            elif ax == thick:                                 # broad face
                u, v = us + du * tg, v0 + (v1 - v0) * ta
            else:                                             # edge
                u, v = us + du * tg, v0 + (v1 - v0) * tt * min(size[thick] / max(size[across], 1e-4), 1.0)
            if flip:
                v = v0 + v1 - v
            l[uvl].uv = (u, v)
        f.material_index = WOOD_I
        f.smooth = False
    return fs

def round_leg(a, b, r0, r1, sides=8):
    """Tapered round leg from a to b with one plank strip along it."""
    fs = new_faces(tube, [Vector(a), Vector(b)], lambda t: r0 + (r1 - r0) * t, sides=sides)
    us_ = [l[uvl].uv[0] for f in fs if len(f.verts) == 4 for l in f.loops]
    vs_ = [l[uvl].uv[1] for f in fs if len(f.verts) == 4 for l in f.loops]
    ulo, uhi, vlo, vhi = min(us_), max(us_), min(vs_), max(vs_)
    u0, u1, v0, v1 = strip()
    length, circ = (uhi - ulo) * TILE, (vhi - vlo) * TILE
    du = min(length * (v1 - v0) * fg._IMG_H / fg._IMG_W / max(circ, 1e-3), u1 - u0)
    s = rng.uniform(u0, u1 - du)
    for f in fs:
        for l in f.loops:
            if len(f.verts) == 4:
                u, v = l[uvl].uv
                l[uvl].uv = (s + du * (u - ulo) / (uhi - ulo), v0 + (v1 - v0) * (v - vlo) / (vhi - vlo))
            else:
                l[uvl].uv = (s + du * 0.5, (v0 + v1) / 2)
        f.material_index = WOOD_I
    return fs
