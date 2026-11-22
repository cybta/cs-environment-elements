"""Bake the old cottage's texture maps into cs_environment_elements/core/assets/neighborhood/.

    blender -b --factory-startup --python tools/make_cottage_textures.py

Everything is derived from the bundled CC0 wood_floor scan or drawn from noise, so the
output is CC0 too. All maps are 1024 px squares that tile:

    cottage_logs_*     weathered "imitation beam" siding: 9 rounded boards, grey and stained
    cottage_wood_*     weathered planks with no profile (posts, rails, deck, fascias)
    cottage_lining_*   honey-coloured pine lining for the inside (diff + nor; rough from the scan)
    cottage_roof_*     corrugated sheet, 2 m square, 20 waves running down the slope:
                       _diff = the bare sheet (galvanised steel, rust streaks, nail heads),
                       _paint = R how long the paint lasts (rust spots, the lap and nails first),
                       G sun-faded crests, B shading (darker valleys and lap); the colour comes
                       from the mesh (core/paint.py), so one set serves every roof colour

Boards run along the image's x (U) axis, so on walls they lie horizontal.
"""

import os

import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                # organic_noise
OUT = os.path.normpath(os.path.join(HERE, "..", "cs_environment_elements", "core", "assets", "neighborhood"))
N = 1024
BOARDS = 9                      # planks across the wood_floor scan
rng = np.random.default_rng(1907)


# --------------------------------------------------------------------------
# I/O and noise
# --------------------------------------------------------------------------

def load(name):
    """(N, N, 3) float, rows from the bottom, values as stored (sRGB for colour maps)."""
    img = bpy.data.images.load(os.path.join(OUT, name))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)[..., :3].copy()


def save(name, rgb, data=False):
    """rgb: (h, w), (h, w, 3) or (h, w, 4); a 4th channel is written as alpha (PNG only)."""
    rgb = np.clip(rgb, 0.0, 1.0)
    if rgb.ndim == 2:
        rgb = np.repeat(rgb[..., None], 3, axis=2)
    h, w, c = rgb.shape
    img = bpy.data.images.new(name, w, h, alpha=c == 4)
    if data:
        img.colorspace_settings.name = "Non-Color"
    if c == 4:
        img.alpha_mode = "CHANNEL_PACKED"
    px = np.ones((h, w, 4), np.float32)
    px[..., :c] = rgb
    if c == 4:
        img.file_format = "PNG"
        img.filepath_raw = os.path.join(OUT, name)
        img.pixels.foreach_set(px.ravel())
        img.save()
        print("wrote", name)
        return
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, name)
    if name.endswith(".png"):           # data packed per channel: no JPEG chroma smearing
        img.file_format = "PNG"
        img.save()
    else:
        img.file_format = "JPEG"
        img.save(quality=92)
    print("wrote", name)


def durability(worn):
    """How long paint lasts, 0.05..0.95, from a 'how worn' field: rank-equalised, so a
    peeling of p takes the paint off about p of the surface (see core/paint.py)."""
    r = np.empty(worn.size, np.float32)
    r[np.argsort(worn.ravel(), kind="stable")] = np.linspace(1.0, 0.0, worn.size)
    return 0.05 + 0.9 * r.reshape(worn.shape)


def vnoise(cy, cx, octaves=1):
    """Tileable value noise in [0, 1]: cy x cx cells (doubling per octave)."""
    out = np.zeros((N, N), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        ny, nx = cy * 2 ** o, cx * 2 ** o
        g = rng.random((ny, nx)).astype(np.float32)

        def axis(n):
            c = np.arange(N) * n / N
            i0 = np.floor(c).astype(int)
            f = c - i0
            return i0 % n, (i0 + 1) % n, f * f * (3 - 2 * f)

        y0, y1, fy = axis(ny)
        x0, x1, fx = axis(nx)
        rows = g[:, x0] * (1 - fx) + g[:, x1] * fx
        out += amp * (rows[y0] * (1 - fy)[:, None] + rows[y1] * fy[:, None])
        tot += amp
        amp *= 0.5
    return out / tot


def normal_map(h, strength=1.0):
    """Tangent-space normal map (OpenGL, green up) from a height field in pixels."""
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    n = np.stack([-dx, -dy, np.ones_like(h)], axis=2)
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def lum(rgb):
    return rgb @ np.array([0.299, 0.587, 0.114], np.float32)


# --------------------------------------------------------------------------
# Wood
# --------------------------------------------------------------------------

def boards():
    """Scan turned so the planks lie along x; t = 0..1 across each board (0 at a seam)."""
    src = np.rot90(load("wood_floor_diff.jpg")).copy()
    bh = N / BOARDS
    rows = (N - 1 - np.arange(N)) % bh / bh
    ids = ((N - 1 - np.arange(N)) // bh).astype(int)
    return src, rows.astype(np.float32)[:, None], ids


def weathered(src, ids, amount=0.6):
    """Old grey timber: the scan's grain, bleached to silver-brown, uneven from board to board."""
    L = lum(src)
    L = (L - L.mean()) * 1.25 + 0.47
    grey = L[..., None] * np.array([1.08, 1.0, 0.88], np.float32)
    w = np.clip(amount + 0.3 * (vnoise(3, 2, 3) - 0.5), 0, 1)[..., None]
    col = src * (1 - w) + grey * w
    tone = (0.82 + 0.3 * rng.random(BOARDS))[ids][:, None, None]
    col = col * tone
    streaks = vnoise(3, 24, 3) * (0.5 + vnoise(2, 5))   # rain-washed stains running down, patchy
    col *= 1.0 - 0.22 * np.clip(streaks * 2.0 - 0.9, 0, 1)[..., None]
    dirt = vnoise(6, 6, 3)
    col *= (0.85 + 0.2 * dirt)[..., None]
    return col, L


def make_logs():
    src, t, ids = boards()
    col, L = weathered(src, ids, 0.62)
    prof = np.sqrt(np.clip(1 - (2 * t - 1) ** 2, 0, 1)) ** 0.6     # rounded face of each board
    groove = (t < 0.035) | (t > 0.965)
    col *= (0.5 + 0.5 * prof)[..., None]
    col[np.broadcast_to(groove, (N, N))] *= 0.4
    save("cottage_logs_diff.jpg", col)
    save("cottage_logs_nor.jpg", normal_map(prof * 14.0 + L * 1.2 - groove * 3.0), data=True)
    rough = 0.78 + 0.18 * (1 - L) + 0.1 * groove
    save("cottage_logs_rough.jpg", rough, data=True)


def make_wood():
    src, t, ids = boards()
    col, L = weathered(src, ids, 0.55)
    seam = (t < 0.012) | (t > 0.988)
    col[np.broadcast_to(seam, (N, N))] *= 0.45
    save("cottage_wood_diff.jpg", col)
    save("cottage_wood_nor.jpg", normal_map(L * 2.0 - seam * 4.0), data=True)
    save("cottage_wood_rough.jpg", 0.75 + 0.2 * (1 - L) + 0.1 * seam, data=True)


def make_lining():
    """Pine lining gone honey-yellow with age: the scan's grain recoloured, a small V-groove per board."""
    src, t, ids = boards()
    L = lum(src)
    L = np.clip((L - L.mean()) * 1.6 + 0.5, 0, 1)
    dark, light = np.array([0.45, 0.27, 0.11], np.float32), np.array([0.86, 0.66, 0.37], np.float32)
    col = dark + (light - dark) * L[..., None]
    col *= (0.88 + 0.2 * rng.random(BOARDS))[ids][:, None, None]
    col *= (0.9 + 0.15 * vnoise(4, 4, 3))[..., None]
    edge = np.clip(np.minimum(t, 1 - t) / 0.05, 0, 1)
    col *= (0.55 + 0.45 * edge)[..., None]
    save("cottage_lining_diff.jpg", col)
    save("cottage_lining_nor.jpg", normal_map(edge * 4.0 + L * 0.8), data=True)


# --------------------------------------------------------------------------
# Corrugated roof sheet
# --------------------------------------------------------------------------

def make_roof():
    WAVES = 20                                                      # over 2 m
    u = np.arange(N, dtype=np.float32) / N
    v = np.arange(N, dtype=np.float32) / N
    U, V = np.meshgrid(u, v)
    crest = 0.5 + 0.5 * np.cos(2 * np.pi * WAVES * U)               # 1 on the crests
    amp_px = 0.018 * N / 2                                          # 18 mm half-height, in pixels
    height = crest * 2 * amp_px

    # Overlap of the next sheet up at the top of the tile, nail heads on every other crest
    lap = np.clip(1 - V / 0.006, 0, 1)
    nails = np.zeros((N, N), np.float32)
    halo = np.zeros((N, N), np.float32)
    nail_rng = np.random.default_rng(911)
    for k in range(0, WAVES, 2):
        for vy in (0.03, 0.28, 0.53, 0.78):
            d = np.hypot((U - k / WAVES) * N, (V - vy) * N)
            d = np.minimum(d, np.hypot((U - k / WAVES - 1) * N, (V - vy) * N))
            nails = np.maximum(nails, np.clip(1 - d / 3.0, 0, 1) > 0)
            r = nail_rng.uniform(6.0, 16.0)                         # each nail rusts its own amount
            halo = np.maximum(halo, np.clip(1 - d / r, 0, 1) * nail_rng.random() ** 2)
    height = height - lap * 6.0 + nails * 2.0

    # Rust: organic patches (and round some nails, along the lap) that bleed down the valleys
    from organic_noise import organic_wear
    wear_rng = np.random.default_rng(6151)
    # rust spots all over the tile: the material only lets them show inside the big wear
    # zones (wear_zones.png), so they gather in one or two areas of a roof, not everywhere
    patches = organic_wear(wear_rng, N, grain=np.pi / 2, grain_weight=0.35, chip=22.0, clump_weight=0.3)
    seed = np.clip((patches - 0.6) * 3.0, 0, 1) * (0.5 + 0.5 * (1 - crest))
    seed = np.maximum(seed, lap * 0.8 * (0.4 + 0.6 * patches) + halo * (0.3 + 0.6 * vnoise(16, 16, 2)))
    streak = seed.copy()
    for i in range(N - 2, -1, -1):                                  # downhill = towards row 0
        streak[i] = np.maximum(streak[i], streak[i + 1] * (0.99 - 0.015 * crest[i]))
    rust = np.clip(streak * (0.45 + 0.7 * vnoise(60, 8, 2)), 0, 1)

    fade = vnoise(8, 10, 4)
    nor = normal_map(height)
    save("cottage_roof_nor.jpg", nor, data=True)
    # roughness of the bare sheet (the paint's own is a constant in the material)
    save("cottage_roof_rough.jpg", 0.42 + 0.1 * fade, data=True)

    # Under the paint: clean galvanised steel (the rust is in the paint map's alpha, see above)
    galv = np.stack([0.5 + 0.08 * fade, 0.51 + 0.08 * fade, 0.52 + 0.07 * fade], axis=2)
    under = galv * (1.0 - 0.15 * (1 - crest))[..., None]
    under *= (1.0 - 0.4 * lap)[..., None]
    under = under * (1 - nails[..., None]) + 0.45 * nails[..., None]
    save("cottage_roof_diff.jpg", under)

    # the sun-baked crests lose their paint first, the valleys keep it longest; organic chips
    # at every angle (down the slope leading), in clumps
    chips = organic_wear(wear_rng, N, grain=np.pi / 2, grain_weight=0.45, chip=30.0, clump_weight=0.45)
    worn = 0.3 * rust + 0.45 * chips + 0.07 * crest + 0.6 * lap + nails
    data = np.stack([
        durability(worn),
        np.clip(0.35 * crest ** 3 * (0.5 + fade), 0, 1),               # sun-faded crests
        np.clip((0.82 + 0.3 * fade) * (1.0 - 0.18 * (1 - crest)) * (1.0 - 0.4 * lap) / 1.15, 0, 1),
        rust,                                                           # A: rust streaks (bleed down the valleys)
    ], axis=2)
    save("cottage_roof_paint.png", data, data=True)


def make_wear_zones():
    """wear_zones.png: 256 px of very soft, organic, tileable blobs (rank-equalised 0..1). The
    peeling-paint materials stretch it over ~16 m, so one building gets one or two areas
    where the paint is far more worn (and roofs rust), instead of the same wear everywhere."""
    from organic_noise import fbm, warp
    zrng = np.random.default_rng(4421)
    n = 256
    z = fbm(zrng, n, 4.0, lo=1.2)
    z = warp(z, (fbm(zrng, n, 4.0, lo=1.5) - 0.5) * 60, (fbm(zrng, n, 4.0, lo=1.5) - 0.5) * 60)
    r = np.empty(z.size, np.float32)
    r[np.argsort(z.ravel(), kind="stable")] = np.linspace(0.0, 1.0, z.size)
    save("wear_zones.png", r.reshape(n, n), data=True)


if __name__ == "__main__":          # make_shop_textures imports the helpers above
    make_logs()
    make_wood()
    make_lining()
    make_roof()
    make_wear_zones()
