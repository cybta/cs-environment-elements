"""Bake the shopping row's texture maps into cs_environment_elements/core/assets/neighborhood/.

    blender -b --factory-startup --python tools/make_shop_textures.py

Derived from the bundled CC0 wood_table_001 scan or drawn from noise, so CC0 too.
Both sets are neutral (near-white / grey) so one map serves every colour: the
materials multiply them by each shop's paint or canvas colour.

    shop_paintwood_*   1 m square: painted timber joinery. The scan's grain shows faintly
                       through the paint, brush strokes run with the grain, a few chips.
                       Grain runs along U, so lengthwise UVs lay it along each stile and rail.
    shop_canvas_*      0.5 m square: plain-weave awning canvas, 2 mm threads, uneven
                       threads and slubs, faint weathering streaks along U (down the slope).
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_cottage_textures import N, load, lum, normal_map, save, vnoise  # noqa: E402

rng = np.random.default_rng(311)


def make_paintwood():
    src = np.rot90(load("wood_table_001_diff.jpg")).copy()          # grain along x
    g = lum(src)
    g = (g - g.mean()) / (g.std() + 1e-6)                            # grain, zero mean
    strokes = vnoise(170, 5, 2) - 0.5                                # brush marks along the grain
    blot = vnoise(5, 5, 3) - 0.5                                     # uneven coats
    chips = np.clip((vnoise(48, 48, 2) - 0.8) * 10, 0, 1) * np.clip((vnoise(3, 3, 2) - 0.5) * 5, 0, 1)

    col = 0.8 + 0.012 * g + 0.012 * strokes + 0.025 * blot
    col = col * (1 - chips) + 0.42 * chips                           # older paint showing at chips
    save("shop_paintwood_diff.jpg", col)
    save("shop_paintwood_nor.jpg", normal_map(0.6 * g + 1.5 * strokes - 2.0 * chips, 0.45), data=True)
    save("shop_paintwood_rough.jpg", 0.32 + 0.06 * strokes + 0.08 * blot + 0.35 * chips, data=True)


def make_canvas():
    p = 4.0                                                          # px per thread (2 mm at 0.5 m / 1024)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32)
    u, v = x / p, y / p
    iu, iv = np.floor(u).astype(int), np.floor(v).astype(int)
    warp = np.sin(np.pi * (u - iu))                                  # warp threads run along y
    weft = np.sin(np.pi * (v - iv))
    over = (iu + iv) % 2 == 0                                        # plain weave: warp on top here
    h = np.where(over, warp * 1.0 + weft * 0.35, weft * 1.0 + warp * 0.35)

    nt = int(N / p)
    tw, tf = rng.random(nt)[iu % nt], rng.random(nt)[iv % nt]       # each thread a touch different
    shade = np.where(over, 0.95 + 0.05 * tw, 0.95 + 0.05 * tf)
    slubs = np.clip((vnoise(3, 180, 1) - 0.6) * 4, 0, 1)             # thick spots along the warp
    dirt = vnoise(3, 3, 4)
    streaks = vnoise(70, 3, 2)                                       # rain marks down the slope (along x)
    col = 0.86 * shade * (0.82 + 0.18 * h) * (0.9 + 0.14 * dirt) * (1 - 0.1 * np.clip(streaks * 2 - 0.8, 0, 1))
    col *= 1 + 0.06 * slubs
    save("shop_canvas_diff.jpg", col)
    save("shop_canvas_nor.jpg", normal_map(h * 1.6 + slubs * 0.8, 0.8), data=True)
    save("shop_canvas_rough.jpg", 0.78 + 0.12 * (1 - h) + 0.05 * dirt, data=True)


make_paintwood()
make_canvas()
