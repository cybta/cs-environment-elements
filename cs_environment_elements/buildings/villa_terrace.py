"""The modern villa's back garden side, after the user's render of 2026-11-26:

- a black steel pergola off the back wall over the garden doors: posts at the outer corners,
  a frame of deep beams, an oak-slat roof (oak on top too) with downlights,
- a raised terrace of 60 cm travertine tiles under it, a step down round its front and sides
  (no furniture: the user adds props by hand),
- warm up-and-down wall lights either side of the garden doors and on the stone corner
  (villa_layout paints that corner of the back wall in the bay's travertine).

Plan coordinates as in villa.py: back wall's outer face at y = D + te / 2, ground at c.G.
"""

EPS = 1e-4
DEPTH = 3.6         # how far the pergola reaches out from the back wall
BEAM = 0.15


def _mat(c, role, fallback, color):
    from .villa_dress import _mat as get
    return get(c, role, fallback, color)


def back_doors(c):
    """The ground floor's glazed doors in the back wall, west to east."""
    D = c.D
    return sorted((o for o in c.ground.openings if o.exterior and o.kind == "PATIO" and o.axis == "X"
                   and abs(o.coord - D) < 0.05), key=lambda o: o.s0)


def span(c):
    """(x0, x1) of the pergola, centred on the garden doors (or the back wall)."""
    W, te = c.W, c.te
    doors = back_doors(c)
    if doors:
        a, b = doors[0].s0, doors[-1].s1
    else:
        a, b = W / 2 - 1.2, W / 2 + 1.2
    w = min(max(b - a + 3.5, 5.0), W - 0.6)
    x0 = min(max((a + b) / 2 - w / 2, -te / 2 + 0.3), W + te / 2 - 0.3 - w)
    return x0, x0 + w


def build(c):
    W, D, te, G, H = c.W, c.D, c.te, c.G, c.H
    x0, x1 = span(c)
    y0, y1 = D + te / 2, D + te / 2 + DEPTH
    steel = _mat(c, "fascia", "trim", (0.05, 0.05, 0.06))
    wood = _mat(c, "soffit_wood", "soffit", (0.5, 0.33, 0.2))
    lamp = _mat(c, "lamp", "glass", (1.0, 0.75, 0.45))

    # Terrace: a slab up to just under the floor, a step down round its front and sides
    zt = -0.02
    a0, a1, b1 = x0 - 0.6, x1 + 0.6, y1 + 0.6
    mid = (G + zt) / 2
    c.add("TerraceDeck", [(a0, y0, G, a1, b1, zt)], _mat(c, "deck_stone", "paving", (0.8, 0.74, 0.64)))
    c.add("TerraceStep", [(a0 - 0.35, y0, G, a0, b1 + 0.35, mid), (a1, y0, G, a1 + 0.35, b1 + 0.35, mid),
                          (a0, b1, G, a1, b1 + 0.35, mid)], _mat(c, "deck_stone", "paving", (0.8, 0.74, 0.64)))

    # Pergola: posts at the free corners, a beam frame, the slatted ceiling inside it
    z0, z1 = H - 0.15, H + 0.12
    c.add("PergolaFrame", [
        (x0, y1 - BEAM, z0, x1, y1, z1), (x0, y0, z0, x0 + BEAM, y1, z1), (x1 - BEAM, y0, z0, x1, y1, z1),
        (x0, y0, z0, x1, y0 + 0.1, z1),                                    # the ledger on the wall
        (x0, y1 - BEAM, G, x0 + BEAM, y1, z0), (x1 - BEAM, y1 - BEAM, G, x1, y1, z0)], steel)
    c.add("PergolaCeiling", [(x0 + BEAM, y0 + 0.1, z1 - 0.1, x1 - BEAM, y1 - BEAM, z1)],
          paint=(wood, wood, steel))
    lights = []
    n = max(2, round((x1 - x0) / 1.6))
    for row in (y0 + 0.1 + (y1 - y0) * 0.3, y0 + (y1 - y0) * 0.72):
        for k in range(n):
            x = x0 + BEAM + (x1 - x0 - 2 * BEAM) * (k + 0.5) / n
            lights.append((x - 0.05, row - 0.05, z1 - 0.106, x + 0.05, row + 0.05, z1 - 0.099))
    c.add("PergolaLights", lights, lamp)

    _lights(c, steel, lamp)


# --------------------------------------------------------------------------
# Wall lights on the back
# --------------------------------------------------------------------------

def _lights(c, steel, lamp):
    W, D, te = c.W, c.D, c.te
    y = D + te / 2
    xs = []           # (the garden doors' lights: villa_dress._door_lights)
    # on the stone corner: between its nearest window and the corner
    corner = c.plan.villa.get("stone_corner")
    if corner is not None:
        a, b = corner
        if b - a > 0.6:
            xs += [a + 0.2, b - 0.32] if b - a > 1.0 else [(a + b) / 2 - 0.06]
    bodies, glow = [], []
    for x in xs:
        bodies.append((x, y, 1.8, x + 0.12, y + 0.13, 2.2))
        glow += [(x + 0.02, y + 0.01, 1.78, x + 0.1, y + 0.135, 1.8), (x + 0.02, y + 0.01, 2.2, x + 0.1, y + 0.135, 2.22)]
    c.add("BackWallLights", bodies, steel)
    c.add("BackWallLightGlow", glow, lamp)
