"""The painted cottage's own exterior parts (cottage.py builds everything else).

After the references in Desktop/cottages styles/style-2: weathered painted boards on a
low brick plinth, and a plain open gable roof with a deep verge, white bargeboards
under its edges and a skirt board where the upright-boarded gable meets the siding below.

Same conventions as cottage.py: plan coordinates (front at y = 0, ground-floor top at
z = 0), boxes and extruded outlines, metric UVs.
"""

import math

from mathutils import Vector

from .cottage import EAVE, ROOF_T, _extrude, roof_paint

OPEN_VERGE = 0.5        # the roof runs this far past the gable walls
BARGE_H = 0.2           # bargeboard depth below the roof's underside
BARGE_T = 0.035
PLINTH_OUT = 0.03       # brick face proud of the siding


def plinth(c):
    """A low brick wall under the house in place of the old cottage's piles, with a
    concrete flashing on top that throws rain off the brickwork."""
    W, D, te = c.W, c.D, c.te
    top = -c.slab
    o = te / 2 + PLINTH_OUT
    w = te + PLINTH_OUT * 2

    def ring(o, w, z0, z1):
        return [(-o, -o, z0, W + o, -o + w, z1), (-o, D + o - w, z0, W + o, D + o, z1),
                (-o, -o + w, z0, -o + w, D + o - w, z1), (W + o - w, -o + w, z0, W + o, D + o - w, z1)]

    c.add("Plinth", ring(o, w, c.G - 0.1, top - 0.03), "plinth")
    c.add("PlinthCap", ring(o + 0.03, w + 0.06, top - 0.03, top + 0.01), "plinth_cap")


def roof(c):
    """Two straight slopes from the eaves to the ridge (running front to back)."""
    W, D, te, F1, k = c.W, c.D, c.te, c.F1, c.k
    p = math.radians(k["pitch_low"])
    T = ROOF_T
    x_e = -te / 2 - EAVE
    d, n = Vector((math.cos(p), math.sin(p))), Vector((-math.sin(p), math.cos(p)))
    E = Vector((x_e, F1 + k["knee"] + x_e * math.tan(p)))      # underside at the eave
    R = Vector((W / 2, F1 + k["zr"]))                         # underside at the ridge
    Eo = E + n * T
    Ro = Eo + d * ((W / 2 - Eo.x) / d.x)

    def m(v):
        return (W - v.x, v.y)

    outline = [tuple(E), tuple(R), m(E), m(Eo), tuple(Ro), tuple(Eo)]
    caps = [[0, 1, 4, 5], [1, 2, 3, 4]]
    y0, y1 = -te / 2 - OPEN_VERGE, D + te / 2 + OPEN_VERGE
    c.solid("Roof", [_extrude(outline, y0, y1, "Y", caps)], paint=roof_paint(c))
    c.add("RoofRidge", [(W / 2 - 0.12, y0, Ro.y - 0.05, W / 2 + 0.12, y1, Ro.y + 0.03)], "roof")
    c.ridge_top = Ro.y

    # Bargeboards: a board under each verge, from the eave up to the ridge, its top edge
    # just proud of the sheet, its bottom edge BARGE_H below the underside
    def at_x(P, x):
        return P + d * ((x - P.x) / d.x)

    top_line, bot_line = Eo + n * 0.02, E - n * BARGE_H
    quad = [at_x(bot_line, x_e), at_x(bot_line, W / 2), at_x(top_line, W / 2), at_x(top_line, x_e)]
    parts, signs = [], []
    for ya, yb in ((y0 - BARGE_T, y0 + 0.005), (y1 - 0.005, y1 + BARGE_T)):
        for sgn in (1, -1):
            pts = [(v.x, v.y) if sgn > 0 else m(v) for v in quad]
            if sgn < 0:
                pts.reverse()                                   # keep the winding outward
            parts.append(_extrude(pts, ya, yb, "Y"))
            signs.append(sgn)
    c.solid("Bargeboards", parts, "bargeboard",
            along=lambda i: Vector((d.x * signs[i // 6], 0.0, d.y)))


def gable_trim(c):
    """A skirt board across each gable at the attic floor, where the gable's upright boards
    stop over the siding below (on the gables only: the knee walls carry the siding on)."""
    W, D, te, F1 = c.W, c.D, c.te, c.F1
    o, dp = te / 2, 0.04
    z0, z1 = F1 - 0.16, F1 + 0.02
    x0, x1 = -o - 0.04, W + o + 0.04
    c.add("GableSkirt", [(x0, -o - dp, z0, x1, -o, z1), (x0, D + o, z0, x1, D + o + dp, z1)],
          "trim", lengthwise=True)
