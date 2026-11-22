"""Bake the painted cottage's siding maps into cs_environment_elements/core/assets/neighborhood/.

    blender -b --factory-startup --python tools/make_cottage_paint_textures.py

Old painted timber after the references in Desktop/cottages styles/style-2: the paint
is chalky and faded, darker with grime under each board, and has flaked off in strips
along the grain, showing the grey weathered wood (the same weathered scan as the old
cottage's siding) underneath. Derived from the bundled CC0 wood_floor scan + noise.

    cottage_lap_*      lap siding (clapboard): 9 boards per 1.44 m, each a wedge whose
                       thick lower edge throws a shadow line onto the board below
    cottage_planks_*   flat tongue-and-groove boards with a V-groove at each seam
                       (laid upright by the material's 90 degree rotation)

Per pattern, shared by every paint colour (the colour and the peeling come from the
mesh, see core/paint.py):
    _diff    the bare weathered wood under the paint, with the boards' shading
    _paint   R how long the paint lasts (strips along the grain, the boards' lower edges
             first), G sun fade, B dirt and shading on the paint (PNG: exact per channel)
    _nor, _rough   the boards (roughness of the bare wood)
Boards run along the image's x (U) axis, as in make_cottage_textures.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_cottage_textures import BOARDS, N, boards, durability, normal_map, save, vnoise, weathered  # noqa: E402
from organic_noise import organic_wear  # noqa: E402

rng = np.random.default_rng(2611)
wear_rng = np.random.default_rng(5077)


def worn_field(t, ids):
    """How worn the paint is (higher = flakes off sooner): organic chips at every angle,
    the grain direction leading, in clumps; each board its own age; the boards' lower
    edges a little sooner."""
    chips = organic_wear(wear_rng, N, grain=0.0, grain_weight=0.4, chip=26.0, clump_weight=0.33)
    edge = np.clip((t - 0.75) / 0.25, 0, 1) ** 2                 # lower edge of each board
    age = wear_rng.uniform(-0.12, 0.12, BOARDS)[ids][:, None]    # some boards repainted later
    return chips + 0.18 * edge + age


def paint(pattern, t, profile, groove, upright):
    src, _, ids = boards()
    wood, L = weathered(src, ids, 0.7)
    worn = worn_field(t, ids)
    fade = vnoise(4, 6, 4)                                       # chalky, sun-bleached patches
    grime = vnoise(3, 20, 3) * (0.4 + 0.6 * np.clip(t, 0, 1))  # dirt collects on the lower part of each board
    # rain runs down the wall: across lap boards, along upright planks (the image is turned 90 degrees on them)
    streaks = vnoise(40, 2, 2) if upright else vnoise(2, 40, 2)
    tone = (0.93 + 0.1 * rng.random(9))[ids][:, None, None]
    grooves = np.broadcast_to(groove > 0.5, (N, N))

    save(f"cottage_{pattern}_nor.jpg", normal_map(profile + 0.3 * L - groove * 3.0, 1.0), data=True)
    save(f"cottage_{pattern}_rough.jpg", 0.82 + 0.08 * (1 - L) + 0.1 * groove, data=True)

    shade = 0.55 + 0.45 * np.clip(profile / max(profile.max(), 1e-6), 0, 1)
    under = wood * 0.95 * shade[..., None]
    under[grooves] *= 0.35
    save(f"cottage_{pattern}_diff.jpg", under)

    dirt = (tone[..., 0] * (0.97 + 0.04 * L) * (1 - 0.25 * grime)
            * (1 - 0.12 * np.clip(streaks * 2 - 1, 0, 1)) * shade)
    dirt[grooves] *= 0.35
    data = np.stack([durability(worn), 0.15 + 0.45 * fade, np.clip(dirt, 0, 1)], axis=2)
    save(f"cottage_{pattern}_paint.png", data, data=True)


def make_lap():
    _, t, _ = boards()
    t = np.broadcast_to(t, (N, N))
    profile = 2.0 + 10.0 * t                                     # wedge: thin at the top, thick at the lip
    shadow = np.clip(1 - t / 0.09, 0, 1) ** 1.5                  # under the lip of the board above
    profile = profile - 9.0 * shadow
    groove = (t < 0.012).astype(np.float32)
    paint("lap", t, profile, groove, False)


def make_planks():
    _, t, _ = boards()
    t = np.broadcast_to(t, (N, N))
    v = np.clip(np.minimum(t, 1 - t) / 0.03, 0, 1)              # chamfered V at each seam
    profile = 6.0 * v
    groove = ((t < 0.008) | (t > 0.992)).astype(np.float32)
    paint("planks", t, profile, groove, True)


make_lap()
make_planks()
