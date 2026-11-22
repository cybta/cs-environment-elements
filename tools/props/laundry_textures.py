"""Textures for the clothesline set (build_clothesline.py), drawn from noise (CC0).

laundry_atlas_2k.png   2048 x 1024, 4 x 2 cells of 512 px, one opaque material for every
                       piece of laundry (flat cloth only: cut-out garments read as 2D cards)
    row 1:  0 white sheet       1 beige towel        2 plaid blanket      3 floral plaid sheet
    row 0:  4 checked tea towel 5 grey wool blanket  6 striped linen      7 yellow towel
laundry_atlas_nor_2k.png   its OpenGL normal (weave, wrinkles in the dirt)
wicker_1k.png / wicker_nor_1k.png   basket weave, one repeat = WICKER_TILE metres

Load with exec() from the build script after setting TEXL (output folder); then call
make_laundry_textures(). CELL_UV(cell) gives a cell's (u0, v0, u1, v1).
"""
import math
import os

import bpy
import numpy as np

C = 512                       # cell size
COLS, ROWS = 4, 2
WICKER_TILE = 0.4


def CELL_UV(cell, inset=3):
    """(u0, v0, u1, v1) of a cell, pulled in by `inset` texels so filtering and mipmaps never
    pick up the neighbouring cell (or wrap round to the far edge of the atlas)."""
    col, row = cell % COLS, (1 if cell < 4 else 0)
    du, dv = inset / (C * COLS), inset / (C * ROWS)
    return col / COLS + du, row / ROWS + dv, (col + 1) / COLS - du, (row + 1) / ROWS - dv


def _fbm(n, seed, beta=2.0, stretch=(1.0, 1.0), lo=2.0):
    g = np.random.default_rng(seed)
    f = np.fft.fftfreq(n) * n
    fx, fy = np.meshgrid(f / stretch[0], f / stretch[1])
    r = np.sqrt(fx ** 2 + fy ** 2); r[0, 0] = 1
    amp = 1 / np.maximum(r, lo) ** (beta / 2); amp[0, 0] = 0
    x = np.real(np.fft.ifft2(np.fft.fft2(g.standard_normal((n, n))) * amp))
    return (x - x.min()) / (x.max() - x.min())


def _sm(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t)


def _lerp(a, b, t): return a + (b - a) * t[..., None]
def _col(c): return np.array(c, np.float32)[None, None, :]


def _grid(n=C):
    ys, xs = (np.mgrid[0:n, 0:n] + 0.5) / n
    return xs, ys


def _fabric(base, seed, weave=180, dirt=0.35):
    """Plain cloth: colour, fine weave, faint mottling, grime gathering low down."""
    xs, ys = _grid()
    w = 0.94 + 0.06 * np.sin(xs * weave * math.pi) * np.sin(ys * weave * math.pi)
    mott = _fbm(C, seed, 2.4)
    c = _col(base) * (w * (0.92 + 0.12 * mott))[..., None]
    smudge = _sm(0.55, 0.85, _fbm(C, seed + 1, 2.2)) * dirt + _sm(0.35, 0.0, ys) * dirt * 0.6
    return _lerp(c, _col((0.55, 0.47, 0.36)), np.clip(smudge, 0, 1) * 0.55)


def _plaid(base, a, b, line, k=6, seed=0):
    xs, ys = _grid()
    def band(t, width, phase=0.0): return _sm(width + 0.04, width, np.abs(((t * k + phase) % 1.0) - 0.5))
    c = _fabric(base, seed, dirt=0.25)
    c = _lerp(c, c * _col(a), band(xs, 0.18) * 0.75)
    c = _lerp(c, c * _col(a), band(ys, 0.18) * 0.75)
    c = _lerp(c, _col(b), band(xs, 0.05, 0.25) * 0.6)
    c = _lerp(c, _col(b), band(ys, 0.05, 0.25) * 0.6)
    c = _lerp(c, _col(line), np.maximum(band(xs, 0.012, 0.5), band(ys, 0.012, 0.5)) * 0.7)
    return c


def _floral(seed=5):
    c = _plaid((0.88, 0.85, 0.76), (1.0, 0.86, 0.86), (0.66, 0.78, 0.62), (0.80, 0.45, 0.48), k=5, seed=seed)
    xs, ys = _grid()
    g = np.random.default_rng(seed)
    for _ in range(140):                                # small roses and leaves
        cx, cy = g.random(2)
        r = g.uniform(0.012, 0.022)
        d = np.hypot(((xs - cx + 0.5) % 1) - 0.5, ((ys - cy + 0.5) % 1) - 0.5)
        pink = _sm(r, r * 0.6, d)
        c = _lerp(c, _col((0.82, 0.45, 0.50)), pink * 0.8)
        lx, ly = cx + r * 1.3, cy - r * 0.6
        leaf = _sm(r * 0.7, r * 0.3, np.hypot(((xs - lx + 0.5) % 1) - 0.5, ((ys - ly + 0.5) % 1) - 0.5))
        c = _lerp(c, _col((0.45, 0.6, 0.4)), leaf * 0.7)
    return c


def _terry(base=(0.74, 0.68, 0.58), seed=3, band=0.8):
    """Towel: coarse terry loops, two woven bands near the hem."""
    xs, ys = _grid()
    loops = _fbm(C, seed, 0.3)
    c = _col(base) * (0.82 + 0.3 * loops)[..., None]
    for y0 in (0.1, 0.16):
        c = _lerp(c, c * band, _sm(0.02, 0.01, np.abs(ys - y0)))
    return _lerp(c, _col((0.55, 0.47, 0.36)), _sm(0.55, 0.85, _fbm(C, seed + 4, 2.2)) * 0.4)


def _tea_towel(seed=15):
    """Off-white tea towel: small blue check, a red stripe near each end."""
    c = _plaid((0.9, 0.88, 0.84), (0.72, 0.8, 0.95), (0.45, 0.55, 0.75), (0.8, 0.82, 0.9), k=14, seed=seed)
    xs, ys = _grid()
    for y0 in (0.08, 0.92):
        c = _lerp(c, _col((0.68, 0.22, 0.2)), _sm(0.03, 0.022, np.abs(ys - y0)) * 0.85)
    return c


def _wool_blanket(seed=16):
    """Grey wool blanket: heavy felted mottling, two dark stripes near each end."""
    xs, ys = _grid()
    c = _col((0.52, 0.51, 0.5)) * (0.8 + 0.3 * _fbm(C, seed, 1.2) + 0.1 * _fbm(C, seed + 1, 0.5))[..., None]
    for y0 in (0.07, 0.13, 0.87, 0.93):
        c = _lerp(c, _col((0.2, 0.2, 0.22)), _sm(0.022, 0.016, np.abs(ys - y0)) * 0.8)
    return _lerp(c, _col((0.45, 0.4, 0.34)), _sm(0.6, 0.9, _fbm(C, seed + 2, 2.2)) * 0.3)


def _striped_linen(seed=17):
    """Cream linen with thin blue stripes running down it."""
    c = _fabric((0.88, 0.85, 0.77), seed, weave=220, dirt=0.3)
    xs, ys = _grid()
    stripe = _sm(0.012, 0.006, np.abs(((xs * 9) % 1.0) - 0.5) / 9)
    return _lerp(c, _col((0.36, 0.45, 0.62)), stripe * 0.75)


def _opaque(c):
    return np.dstack((c, np.ones((C, C), np.float32)))


def _save(path, arr):
    h, w = arr.shape[:2]
    if arr.shape[2] == 3:
        arr = np.dstack((arr, np.ones((h, w), np.float32)))
    img = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    img.pixels.foreach_set(np.clip(arr, 0, 1).astype(np.float32).ravel())
    img.filepath_raw = path; img.file_format = "PNG"; img.save()
    bpy.data.images.remove(img); print("saved", os.path.basename(path))


def _normal(h, s):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * s
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * s
    n = np.dstack((-dx, -dy, np.ones_like(h))); n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def make_laundry_textures():
    os.makedirs(TEXL, exist_ok=True)
    plaid_red = _plaid((0.62, 0.52, 0.5), (0.7, 0.42, 0.4), (0.3, 0.26, 0.3), (0.85, 0.8, 0.7), k=4, seed=8)
    cells = [_fabric((0.90, 0.89, 0.85), 1), _terry(), plaid_red, _floral(),
             _tea_towel(), _wool_blanket(), _striped_linen(), _terry((0.84, 0.74, 0.44), seed=18, band=0.85)]
    cells = [_opaque(c) for c in cells]
    atlas = np.zeros((C * ROWS, C * COLS, 4), np.float32)
    for i, cell in enumerate(cells):
        u0, v0, _, _ = CELL_UV(i)
        x, y = int(u0 * COLS) * C, int(v0 * ROWS) * C
        atlas[y:y + C, x:x + C] = cell
    _save(os.path.join(TEXL, "laundry_atlas_2k.png"), atlas)
    lum = atlas[..., :3].mean(-1)
    _save(os.path.join(TEXL, "laundry_atlas_nor_2k.png"), _normal(lum * 0.5, 2.0))
    # wicker: horizontal strands woven over and under upright stakes
    n = 1024
    xs, ys = (np.mgrid[0:n, 0:n] + 0.5)[::-1] / n
    rows_, stakes = 24, 12
    row = np.floor(ys * rows_); stake = np.floor(xs * stakes)
    over = ((row + stake) % 2 == 0)
    strand = np.sin(((ys * rows_) % 1.0) * math.pi) ** 0.6
    stake_bump = np.sin(((xs * stakes) % 1.0) * math.pi) ** 0.8
    h = np.where(over, strand * (0.6 + 0.4 * stake_bump), strand * 0.55)
    shade = (0.55 + 0.45 * h) * (0.9 + 0.15 * _fbm(n, 21, 1.5))
    c = _col((0.66, 0.48, 0.28)) * shade[..., None]
    c = _lerp(c, _col((0.4, 0.3, 0.2)), _sm(0.6, 0.9, _fbm(n, 22, 2.4)) * 0.4)
    _save(os.path.join(TEXL, "wicker_1k.png"), c)
    _save(os.path.join(TEXL, "wicker_nor_1k.png"), _normal(h, 3.0))
