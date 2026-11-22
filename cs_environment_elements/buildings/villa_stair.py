"""The villa stair fence, after the user's hand-built version (stairs.blend, 2026-11-15).

The two flights stand GAP apart. Smoked-glass panels stand in that gap, one along
each flight and parallel to it, reaching down past the treads so the gap is hidden.
Slim black posts mark the bottom, the landing and the top, and a low glass guard runs
across the drop above flight 1 at the floor above. There is no handrail.

Pure Python: everything is returned as (role, 8 corner points) in the stair floor's
local coordinates, where `across` is X and the stair runs along Y from the corridor
edge `ys` in direction `sign` (distance from that edge = depth d).
Roles: "glass" and "post".
"""

GAP = 0.05          # between the flights
GLASS_T = 0.009     # glass thickness
POST = (0.048, 0.02)  # post: across the gap, along the stair

# Corner order: end (0 = first, 1 = second) x side (lo, hi across) x height (lo, hi).
FACES = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4]]


def stair_fence(xm, dirn, outer, ys, sign, d_start, d_land, z_land, Hs):
    """xm: inner edge of flight 2 (the gap runs from xm to xm + dirn * GAP).
    outer: outer edge of flight 1. d_start / d_land: depth where flight 1 starts and
    where the landing starts. z_land: landing top. Hs: height of the floor above."""

    def across(c, half):
        a, b = xm + dirn * (c - half), xm + dirn * (c + half)
        return min(a, b), max(a, b)

    def solid(x0, x1, d0, lo0, hi0, d1, lo1, hi1):
        pts = []
        for d, lo, hi in ((d0, lo0, hi0), (d1, lo1, hi1)):
            y = ys + sign * d
            for x in (x0, x1):
                for z in (lo, hi):
                    pts.append((x, y, z))
        return pts

    def post(d, z0, z1):
        x0, x1 = across(0.002 + POST[0] / 2, POST[0] / 2)
        return ("post", solid(x0, x1, d - POST[1] / 2, z0, z1, d + POST[1] / 2, z0, z1))

    g1 = across(0.0365, GLASS_T / 2)          # flight 1's panel, nearer flight 1
    g2 = across(0.0095, GLASS_T / 2)          # flight 2's panel, nearer flight 2
    top0, top1 = Hs - 0.196, Hs + 0.504       # the guard upstairs, hiding the slab edge
    gx0, gx1 = sorted((xm + dirn * 0.01, outer + dirn * 0.01))
    return [
        # flight 1: from the bottom step up to the landing
        ("glass", solid(*g1, d_start + 0.05, -0.11, 0.69, d_land - 0.034, z_land - 0.149, z_land + 0.651)),
        # flight 2: from the landing up to the floor above
        ("glass", solid(*g2, d_land - 0.027, z_land - 0.157, z_land + 0.643, 0.058, top0, top1)),
        # across the drop above flight 1, upstairs
        ("glass", solid(gx0, gx1, 0.051, top0, top1, 0.06, top0, top1)),
        post(d_start + 0.05, -0.11, 0.71),
        post(d_land - 0.03, z_land - 0.16, z_land + 0.66),
        post(0.05, Hs - 0.23, Hs + 0.54),
    ]
