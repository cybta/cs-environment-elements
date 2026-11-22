"""Bake the world's ground textures into cs_environment_elements/core/assets/neighborhood/.

    blender -b --factory-startup --python tools/make_world_textures.py

Everything is drawn from noise (numpy FFT noise is periodic, so every map tiles), so the
output is CC0. 1024 px squares, diff / nor (OpenGL) / rough:

    world_dirt_*     packed brown earth with small stones (terrain dirt, trails, worn yards)
    world_gravel_*   old dirt road: compacted earth with a lot of grit and stones
    world_rock_*     grey rock face with cracks, strata and lichen (steep slopes, boulders)
    world_sand_*     fine beach sand with faint ripples
    world_grass_*    short green meadow grass with dry and clover patches (terrain base)
"""

import os

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "cs_environment_elements", "core", "assets", "neighborhood"))
N = 1024
rng = np.random.default_rng(2611)


def save(name, rgb, data=False):
    rgb = np.clip(rgb, 0.0, 1.0)
    if rgb.ndim == 2:
        rgb = np.repeat(rgb[..., None], 3, axis=2)
    img = bpy.data.images.new(name, N, N, alpha=False)
    if data:
        img.colorspace_settings.name = "Non-Color"
    px = np.ones((N, N, 4), np.float32)
    px[..., :3] = rgb
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = os.path.join(OUT, name)
    img.file_format = "JPEG"
    img.save(quality=92)
    print("wrote", name)


def noise(beta, lo=1.0, hi=None):
    """Tileable fractal noise in [0, 1]: white noise shaped to a 1/f^beta spectrum,
    keeping only frequencies between lo and hi (cycles per tile)."""
    f = np.fft.fftfreq(N) * N
    k = np.sqrt(f[None, :] ** 2 + f[:, None] ** 2)
    amp = np.where(k >= lo, np.power(np.maximum(k, 1e-6), -beta), 0.0)
    if hi:
        amp *= np.exp(-(k / hi) ** 2)
    spec = np.fft.fft2(rng.standard_normal((N, N))) * amp
    a = np.real(np.fft.ifft2(spec))
    a -= a.min()
    return a / max(a.max(), 1e-9)


def stones(count, r0, r1):
    """(height, mask) of round stones scattered on the tile, wrapping at the edges."""
    h = np.zeros((N, N), np.float32)
    for _ in range(count):
        r = rng.uniform(r0, r1)
        cx, cy = rng.uniform(0, N, 2)
        e = rng.uniform(0.6, 1.0)                    # a little elongated
        ang = rng.uniform(0, np.pi)
        R = int(r * 1.6) + 2
        ys = (np.arange(int(cy) - R, int(cy) + R + 1)) % N
        xs = (np.arange(int(cx) - R, int(cx) + R + 1)) % N
        dy = (np.arange(int(cy) - R, int(cy) + R + 1) - cy)[:, None]
        dx = (np.arange(int(cx) - R, int(cx) + R + 1) - cx)[None, :]
        u = (dx * np.cos(ang) + dy * np.sin(ang)) / r
        v = (-dx * np.sin(ang) + dy * np.cos(ang)) / (r * e)
        d = np.clip(1.0 - (u * u + v * v), 0.0, 1.0)
        bump = np.sqrt(d) * rng.uniform(0.6, 1.0)
        block = h[np.ix_(ys, xs)]
        h[np.ix_(ys, xs)] = np.maximum(block, bump)
    return h, (h > 0.02).astype(np.float32)


def normal_map(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * 0.5 * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * 0.5 * strength
    n = np.stack([-dx, -dy, np.ones_like(h)], axis=-1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return n * 0.5 + 0.5


def lerp(a, b, t):
    t = t[..., None] if np.ndim(t) == 2 else t
    return np.asarray(a) * (1 - t) + np.asarray(b) * t


def bake_dirt(name, stone_count, grit):
    base = noise(1.6, 2)
    fine = noise(0.6, 40)
    st, sm = stones(stone_count, 2.5, 9.0)
    tone = np.clip(0.55 * base + 0.45 * fine, 0, 1)
    col = lerp((0.26, 0.19, 0.13), (0.42, 0.33, 0.23), tone)
    col = lerp(col, (0.2, 0.15, 0.1), np.clip((noise(1.8, 1, 8) - 0.62) * 3, 0, 1) * 0.7)   # damp patches
    gtone = noise(0.3, 120)
    col = lerp(col, (0.5, 0.46, 0.4), np.clip((gtone - (1 - grit)) * 4, 0, 1) * 0.6)         # grit
    scol = lerp((0.3, 0.28, 0.25), (0.52, 0.49, 0.44), noise(0.4, 30))
    col = lerp(col, scol, sm * np.clip(st * 3, 0, 1))
    h = 0.35 * base + 0.15 * fine + 0.9 * st
    rough = np.clip(0.88 + 0.08 * fine - 0.25 * sm, 0, 1)
    save(f"{name}_diff.jpg", col)
    save(f"{name}_nor.jpg", normal_map(h, 6.0), data=True)
    save(f"{name}_rough.jpg", rough, data=True)


def bake_rock():
    big = noise(1.9, 1)
    mid = noise(1.3, 6)
    ridged = 1.0 - np.abs(noise(1.5, 3, 28) - 0.5) * 2.0
    cracks = np.clip((ridged - 0.94) * 14, 0, 1)
    y = np.arange(N)[:, None] / N
    strata = 0.5 + 0.5 * np.sin((y + 0.08 * big) * np.pi * 2 * 7)
    tone = np.clip(0.45 * big + 0.35 * mid + 0.2 * strata, 0, 1)
    col = lerp((0.3, 0.29, 0.27), (0.6, 0.58, 0.54), tone)
    col = lerp(col, (0.22, 0.21, 0.19), cracks * 0.45)        # fine, not inked
    lichen = np.clip((noise(1.2, 4, 60) - 0.66) * 5, 0, 1) * np.clip((noise(0.5, 60) - 0.3) * 3, 0, 1)
    col = lerp(col, (0.42, 0.44, 0.27), lichen * 0.75)
    h = 0.6 * big + 0.3 * mid + 0.15 * strata - 0.25 * cracks
    rough = np.clip(0.78 + 0.15 * mid + 0.1 * lichen, 0, 1)
    save("world_rock_diff.jpg", col)
    save("world_rock_nor.jpg", normal_map(h, 9.0), data=True)
    save("world_rock_rough.jpg", rough, data=True)


def bake_sand():
    big = noise(1.8, 1)
    fine = noise(0.2, 100)
    y = np.arange(N)[:, None] / N
    x = np.arange(N)[None, :] / N
    ripple = 0.5 + 0.5 * np.sin((y * 14 + 0.6 * big + 0.15 * x) * np.pi * 2)
    tone = np.clip(0.6 * big + 0.32 * fine + 0.08 * ripple, 0, 1)
    col = lerp((0.62, 0.54, 0.4), (0.8, 0.73, 0.58), tone)
    st, sm = stones(60, 1.2, 3.0)                      # a few shell bits / pebbles
    col = lerp(col, (0.85, 0.82, 0.76), sm * 0.6)
    h = 0.4 * big + 0.12 * ripple + 0.2 * fine + 0.3 * st
    save("world_sand_diff.jpg", col)
    save("world_sand_nor.jpg", normal_map(h, 3.0), data=True)
    save("world_sand_rough.jpg", np.clip(0.9 + 0.08 * fine, 0, 1), data=True)


def bake_grass():
    big = noise(1.9, 1)
    mid = noise(1.2, 6)
    fine = noise(0.1, 150)
    # blades: noise stretched along one axis, then rotated in patches by mixing two directions
    a = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) *
                             np.exp(-((np.fft.fftfreq(N)[None, :] * N / 160) ** 2 + (np.fft.fftfreq(N)[:, None] * N / 30) ** 2))))
    b = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) *
                             np.exp(-((np.fft.fftfreq(N)[None, :] * N / 30) ** 2 + (np.fft.fftfreq(N)[:, None] * N / 160) ** 2))))
    blades = np.where(noise(1.5, 3) > 0.5, a, b)
    blades = (blades - blades.min()) / (blades.max() - blades.min())
    tone = np.clip(0.35 * mid + 0.4 * blades + 0.25 * fine, 0, 1)
    col = lerp((0.09, 0.17, 0.04), (0.3, 0.45, 0.12), tone)
    dry = np.clip((noise(1.6, 2, 30) - 0.6) * 4, 0, 1) * 0.55
    col = lerp(col, (0.42, 0.42, 0.2), dry)
    clover = np.clip((noise(1.0, 10, 80) - 0.68) * 6, 0, 1) * 0.5
    col = lerp(col, (0.07, 0.2, 0.06), clover)
    col *= (0.85 + 0.3 * big)[..., None]
    h = 0.6 * blades + 0.3 * fine + 0.2 * mid
    save("world_grass_diff.jpg", col)
    save("world_grass_nor.jpg", normal_map(h, 5.0), data=True)
    save("world_grass_rough.jpg", np.clip(0.85 + 0.1 * fine, 0, 1), data=True)


bake_grass()
bake_dirt("world_dirt", 260, 0.25)
bake_dirt("world_gravel", 900, 0.6)
bake_rock()
bake_sand()
