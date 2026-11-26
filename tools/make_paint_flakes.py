"""Bake the shared paint-flake texture: cs_environment_elements/core/assets/neighborhood/paint_flakes.png

One tileable RGB picture over FLAKE_SIZE metres (core/paint.py), shared by the cottages' siding, their
corrugated roofs and the old fences. Peeling paint breaks along cracks into flakes, so each channel is
built from cells (a periodic, domain-warped Voronoi), not from smooth noise; thresholding it gives
crisp, ragged flake outlines instead of soft blobs:
    R  wood: flakes long along the grain (U), big flakes broken into smaller ones
    G  cracks in the paint (1 = none, 0 = a crack): the big wood flakes' borders, some of them
    B  metal: rounder flakes and small chips (roofs)
R and B are rank-equalised (uniform 0..1). Where the paint goes is mostly decided in the shader by big,
soft weather patches; these flakes only make the edge of a peeled area break up like real paint.

    blender -b --factory-startup --python tools/make_paint_flakes.py     (or any Python with numpy)
"""

import os
import struct
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from organic_noise import fbm, warp  # noqa: E402

OUT = os.path.join(os.path.dirname(HERE), "cs_environment_elements", "core", "assets", "neighborhood",
                   "paint_flakes.png")
N = 2048
SEED = 4242


def cells(rng, gx, gy, dx, dy):
    """Periodic Voronoi on a jittered gx x gy grid, sampled at (pixel + warp). Cells are cw x ch pixels,
    so gx < gy makes them long along U. Returns (random value per cell, gap to the next cell in grid
    units: 0 on a border)."""
    cw, ch = N / gx, N / gy
    jx, jy = rng.uniform(0.05, 0.95, (gy, gx)), rng.uniform(0.05, 0.95, (gy, gx))
    val = rng.random((gy, gx))
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    u, v = (xx + dx) / cw, (yy + dy) / ch
    i0, j0 = np.floor(u).astype(np.int32), np.floor(v).astype(np.int32)
    d1 = np.full((N, N), 1e9, np.float32)
    d2 = np.full((N, N), 1e9, np.float32)
    best = np.zeros((N, N), np.float32)
    for dj in (-1, 0, 1):
        for di in (-1, 0, 1):
            i, j = i0 + di, j0 + dj
            iw, jw = i % gx, j % gy
            d = np.hypot(u - (i + jx[jw, iw]), v - (j + jy[jw, iw]))
            closer = d < d1
            d2 = np.where(closer, d1, np.minimum(d2, d))
            best = np.where(closer, val[jw, iw], best)
            d1 = np.minimum(d1, d)
    return best, d2 - d1


def rank(f):
    out = np.empty(f.size, np.float32)
    out[np.argsort(f.ravel(), kind="stable")] = np.linspace(0.0, 1.0, f.size, dtype=np.float32)
    return out.reshape(f.shape)


def write_png_rgb(path, rgb):
    a = np.clip(rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    raw = b"".join(b"\x00" + a[i].tobytes() for i in range(a.shape[0]))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", a.shape[1], a.shape[0], 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def wobble(rng, px, lo):
    return ((fbm(rng, N, 2.6, lo=lo) - 0.5) * 2 * px).astype(np.float32)


def main():
    rng = np.random.default_rng(SEED)
    # wood (2 m over 2048 px, ~1 mm a pixel): big flakes ~12 x 2.5 cm, small ones ~4 x 0.9 cm
    hx, hy = wobble(rng, 3.5, 90), wobble(rng, 3.5, 90)              # ragged edges, every cell
    wx, wy = wobble(rng, 14, 6) + hx, wobble(rng, 5, 6) + hy
    big, big_gap = cells(rng, 17, 80, wx, wy)
    fx, fy = wobble(rng, 6, 24), wobble(rng, 3, 24)
    small, _ = cells(rng, 52, 230, wx + fx, wy + fy)
    grain = fbm(rng, N, 2.0, lo=N / 40, angle=0.0, stretch=6.0)
    wood = rank(0.58 * big + 0.32 * small + 0.10 * grain)
    # cracks: the big flakes' borders, about half of them (a slow mask picks which)
    keep = fbm(rng, N, 3.0, lo=3.0) > 0.45
    crack = np.clip(big_gap / 0.07, 0.0, 1.0)
    crack = np.where(keep, crack, 1.0)
    # metal: round flakes ~5 cm, chips ~1.5 cm
    mx, my = wobble(rng, 22, 10) + wobble(rng, 6, 50) + hx, wobble(rng, 22, 10) + wobble(rng, 6, 50) + hy
    mbig, _ = cells(rng, 40, 40, mx, my)
    msmall, _ = cells(rng, 130, 130, mx * 0.6 + hy, my * 0.6 + hx)
    blot = warp(fbm(rng, N, 2.4, lo=N / 60), mx, my)
    pits = fbm(rng, N, 1.6, lo=N / 30)
    metal = rank(0.38 * mbig + 0.22 * msmall + 0.28 * blot + 0.12 * pits)
    write_png_rgb(OUT, np.stack([wood, crack, metal], axis=2))
    print(f"{OUT}: {N}x{N}, {os.path.getsize(OUT) / 1024 / 1024:.1f} MB")


main()
