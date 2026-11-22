"""Materials for the shopping row, on top of the Neighborhood scene's own (neighborhood_materials).

Shopfronts and doors are painted timber: one neutral baked map (shop_paintwood: the wood
grain faintly through the paint, brush strokes along the grain, a few chips) multiplied by
each shop's colour, as in the references (teal, bottle green, navy, oxblood...). Awnings
are woven canvas (shop_canvas: plain weave, uneven threads, weathering) in a colour or
cream for the stripes, with a little sheen. Maps are baked by tools/make_shop_textures.py.
Mouldings (pilasters, cornice, belt course, window hoods) are a warm sandstone render.
All use metric UVs like the rest of the scene.
"""

import random

from ..core import neighborhood_materials as nm

# name -> base colour, for painted timber (shopfronts) and canvas (awnings)
PAINTS = {
    "C_shopfront_teal": (0.09, 0.3, 0.28),
    "C_shopfront_green": (0.05, 0.18, 0.1),
    "C_shopfront_navy": (0.04, 0.07, 0.17),
    "C_shopfront_oxblood": (0.25, 0.04, 0.04),
    "C_shopfront_black": (0.025, 0.025, 0.027),
    "C_shopfront_cream": (0.78, 0.72, 0.58),
    "C_shopfront_mustard": (0.6, 0.42, 0.08),
}
CANVAS = {
    "C_canvas_green": (0.07, 0.25, 0.14),
    "C_canvas_red": (0.45, 0.06, 0.05),
    "C_canvas_navy": (0.05, 0.09, 0.22),
    "C_canvas_teal": (0.08, 0.32, 0.3),
    "C_canvas_mustard": (0.65, 0.45, 0.08),
    "C_canvas_terracotta": (0.55, 0.2, 0.1),
}
CANVAS_STRIPE = "C_canvas_cream"
STRIPE_COLOUR = (0.85, 0.8, 0.68)
LIGHT_PAINTS = ("C_shopfront_cream", "C_shopfront_mustard")     # gilt letters won't read on these
DARK_PAINT = "C_shopfront_black"

# The baked maps are near white (paint ~0.6 linear, canvas ~0.5): tint = colour / that
_PAINT_GAIN, _CANVAS_GAIN = 1.65, 2.0


def _bsdf(mat):
    return next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")


def _paint(name, colour):
    mat = nm._build_textured(name, dict(tex="shop_paintwood", scale=1.0, base=colour, rough=0.35,
                                        tint=tuple(c * _PAINT_GAIN for c in colour)))
    mat.diffuse_color = (*colour, 1.0)
    return mat


def _canvas(name, colour):
    mat = nm._build_textured(name, dict(tex="shop_canvas", scale=2.0, base=colour, rough=0.85,
                                        tint=tuple(c * _CANVAS_GAIN for c in colour)))
    mat.diffuse_color = (*colour, 1.0)
    b = _bsdf(mat)
    for key, val in (("Sheen Weight", 0.12), ("Sheen Roughness", 0.6)):    # Blender 4.x fabric sheen
        if key in b.inputs:
            b.inputs[key].default_value = val
    return mat


nm.RECIPES.setdefault("C_shop_stone", dict(tex="white_stucco", scale=0.333, base=(0.86, 0.78, 0.64), rough=0.9,
                                           tint=(1.3, 1.17, 0.95)))
for _n, _c in PAINTS.items():
    nm._SPECIAL.setdefault(_n, lambda n, c=_c: _paint(n, c))
for _n, _c in list(CANVAS.items()) + [(CANVAS_STRIPE, STRIPE_COLOUR)]:
    nm._SPECIAL.setdefault(_n, lambda n, c=_c: _canvas(n, c))
nm._SPECIAL.setdefault("C_sign_gold", lambda n: nm._build_metal(n, (0.8, 0.6, 0.28), 0.3, 0.9))
nm._SPECIAL.setdefault("C_terracotta", lambda n: nm._build_smooth(n, (0.5, 0.22, 0.12), 0.8, 0.15))

SHOP_FACADES = ("CREAM", "PEACH", "SAGE", "BLUE", "BRICK", "WHITE")

# Pairs of a shopfront paint and the awning that goes with it
_LOOKS = (
    ("C_shopfront_teal", "C_canvas_teal"), ("C_shopfront_green", "C_canvas_green"),
    ("C_shopfront_navy", "C_canvas_navy"), ("C_shopfront_oxblood", "C_canvas_red"),
    ("C_shopfront_black", "C_canvas_terracotta"), ("C_shopfront_cream", "C_canvas_green"),
    ("C_shopfront_mustard", "C_canvas_mustard"), ("C_shopfront_green", "C_canvas_red"),
)


def facade_key(facade, seed):
    """The facade for a row: the user's pick, or a warm high-street colour from the seed."""
    if facade != "RANDOM":
        return facade
    return random.Random(seed * 7919 + 307).choice(SHOP_FACADES)


def looks(count, seed):
    """[(paint name, awning name, striped)] per shop: no two neighbours look alike."""
    rng = random.Random(seed * 131 + 9)
    out, last = [], None
    for _ in range(count):
        pick = rng.choice([lk for lk in _LOOKS if lk != last])
        out.append((pick[0], pick[1], rng.random() < 0.55))
        last = pick
    return out


def shop_roles(m, neighborhood):
    """Add the shopping row's roles to a house palette `m` (in place)."""
    from ..core.materials import _material

    if neighborhood:
        get = nm.ensure
    else:
        flat = dict(PAINTS, **CANVAS, **{CANVAS_STRIPE: STRIPE_COLOUR, "C_sign_gold": (0.8, 0.6, 0.28),
                                         "C_terracotta": (0.5, 0.22, 0.12), "C_shop_stone": (0.86, 0.78, 0.64),
                                         "C_sidewalk": (0.62, 0.6, 0.57), "C_curb": (0.6, 0.6, 0.58),
                                         "C_wall_cap": (0.5, 0.47, 0.43), "C_villa_trim": (0.05, 0.05, 0.06),
                                         "C_hedge_leaves": (0.04, 0.15, 0.03), "C_stair_wood": (0.35, 0.22, 0.12),
                                         "C_window_frame": (0.92, 0.92, 0.9), "C_roof_flat": (0.55, 0.55, 0.55)})

        def get(name):
            return _material(f"RoomGen_{name[2:]}", flat.get(name, (0.5, 0.5, 0.5)))

    m.update({
        "stone": get("C_shop_stone"),
        "frame": get("C_window_frame"),
        "cap": get("C_wall_cap"),
        "metal": get("C_villa_trim"),
        "gold": get("C_sign_gold"),
        "sidewalk": get("C_sidewalk"),
        "curb": get("C_curb"),
        "leaves": get("C_hedge_leaves"),
        "pot": get("C_terracotta"),
        "shelf": get("C_stair_wood"),
        "stripe": get(CANVAS_STRIPE),
    })
    m["get"] = get          # shop.py looks up each shop's own paint and canvas through this
    return m
