"""Bake the Mediterranean villa's textures into cs_environment_elements/core/assets/neighborhood/.

    blender -b --factory-startup --python tools/make_villa_textures.py -- [ashlar] [roof [SOURCE]]

(no arguments: both)

    villa_ashlar_*   drawn from noise, so CC0. 1024 px for a 2 m square (about 2 mm a pixel):
                     rustic random ashlar in pale limestone / travertine: courses 14-30 cm high,
                     blocks 30-80 cm long, some tall blocks split into two thin stones, a few
                     narrow ones standing up; chipped, slightly pillowed, pitted faces and
                     recessed lime mortar. Courses run along U, so they lie level on walls.
    villa_roof_tiles_*   new terracotta barrel tiles, from the user's photo (SOURCE, default
                     ref/villas/roof-tiles.jpeg on the Desktop, 2026-11-26). The photo tiles across
                     but not down the slope (1600 px is 9.94 courses), so it is cut where the
                     courses repeat best and cross-faded over the cut, then sized to 1024 px.
                     Normal and roughness maps come from its shading (dark gaps and lips are
                     low). The tile columns run along V: down the slope on roofs. Real size is
                     printed for the material's mapping (12 columns of about 21 cm across).
"""

import os
import sys

import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_cottage_textures import N, normal_map, save  # noqa: E402
from organic_noise import fbm, warp  # noqa: E402

rng = np.random.default_rng(717)
PX = N / 2.0                    # pixels per metre: the tile is 2 m square
RC = 16.0                       # corner rounding (px)

# Limestone and travertine (sRGB): pale cream, sand, warm ochre and a few greyer stones
STONES = np.array([
    (0.86, 0.81, 0.71), (0.82, 0.76, 0.65), (0.89, 0.85, 0.77), (0.78, 0.72, 0.61),
    (0.84, 0.78, 0.66), (0.75, 0.72, 0.66), (0.87, 0.79, 0.64), (0.80, 0.77, 0.71),
], np.float32)
MORTAR = np.array((0.70, 0.66, 0.58), np.float32)


def _split(total, lo, hi):
    """Lengths between lo and hi (px) that add up to exactly `total`."""
    out = []
    while sum(out) < total:
        out.append(rng.uniform(lo, hi))
    if len(out) > 1 and sum(out) - total > out[-1] / 2:      # closer to drop the last one and stretch
        out.pop()
    out = np.array(out) * total / sum(out)
    return np.concatenate([[0.0], np.cumsum(out)])


def layout():
    """Per course: (y0, y1, offset, block edges, split fraction per block or nan)."""
    rows = []
    ys = _split(N, 0.14 * PX, 0.30 * PX)
    for y0, y1 in zip(ys[:-1], ys[1:]):
        h = y1 - y0
        edges = _split(N, 0.30 * PX, 0.80 * PX)
        nb = len(edges) - 1
        # a few blocks become two thin stones, one on the other (random ashlar)
        frac = np.where((h > 0.22 * PX) & (rng.random(nb) < 0.3), rng.uniform(0.38, 0.62, nb), np.nan)
        rows.append((y0, y1, rng.uniform(0, N), edges, frac))
    return rows


def bake():
    rows = layout()
    yy, xx = np.mgrid[0:N, 0:N].astype(np.float32)
    # Joints wobble, so the stones read as dressed by hand, not sawn
    wx = (fbm(rng, N, 3.0, lo=6.0) - 0.5) * 18.0
    wy = (fbm(rng, N, 3.0, lo=6.0) - 0.5) * 12.0
    xw, yw = (xx + wx) % N, (yy + wy) % N

    ys = np.array([r[0] for r in rows] + [N])
    course = np.clip(np.searchsorted(ys, yw, side="right") - 1, 0, len(rows) - 1)
    ids = np.zeros((N, N), np.int32)
    dist = np.zeros((N, N), np.float32)
    base = 0
    for j, (y0, y1, off, edges, frac) in enumerate(rows):
        m = course == j
        xr = (xw[m] - off) % N
        nb = len(edges) - 1
        k = np.clip(np.searchsorted(edges, xr, side="right") - 1, 0, nb - 1)
        dx = np.minimum(xr - edges[k], edges[k + 1] - xr)
        ym = yw[m]
        dy = np.minimum(ym - y0, y1 - ym)
        f = frac[k]
        has = ~np.isnan(f)
        ysplit = y0 + np.nan_to_num(f) * (y1 - y0)
        ds = np.where(has, np.abs(ym - ysplit), np.inf)
        dy = np.minimum(dy, ds)
        # rounded corners: inside RC of two edges, the distance is to a quarter circle
        corner = np.maximum(RC - np.hypot(np.maximum(RC - dx, 0), np.maximum(RC - dy, 0)), 0)
        dist[m] = np.where((dx < RC) & (dy < RC), corner, np.minimum(dx, dy))
        ids[m] = base + 2 * k + (has & (ym > ysplit))
        base += 2 * nb

    n_ids = base
    colour = STONES[rng.integers(0, len(STONES), n_ids)] * rng.uniform(0.95, 1.05, (n_ids, 1)).astype(np.float32)
    bulge = rng.uniform(0.6, 1.4, n_ids).astype(np.float32)          # some stones stand proud
    rough_k = rng.uniform(-0.05, 0.05, n_ids).astype(np.float32)

    # Chipped arrises: the joint line bites into the stone in chunks
    chip = fbm(rng, N, 2.6, lo=22.0)
    chip = warp(chip, (fbm(rng, N, 3.0, lo=10.0) - 0.5) * 14, (fbm(rng, N, 3.0, lo=10.0) - 0.5) * 14)
    d = dist - np.clip(chip - 0.5, 0, 1) * 22.0
    jw = 3.0                                                          # half a joint, px (about 1.2 cm joints)
    stone = d > jw
    body = np.clip((d - jw) / 16.0, 0.0, 1.0)
    body = body * (2.0 - body)                                        # rounded, eased edge

    face = 0.65 * fbm(rng, N, 2.6, lo=18.0) + 0.35 * fbm(rng, N, 1.8, lo=70.0)   # pitched, tooled face
    pits = np.clip((fbm(rng, N, 1.2, lo=90.0) - 0.74) * 5.0, 0, 1)    # travertine holes
    mott = fbm(rng, N, 3.4, lo=2.5)                                   # weathering patches
    grain = fbm(rng, N, 1.3, lo=150.0)
    mortar_n = fbm(rng, N, 1.4, lo=60.0)

    h = np.where(stone, 6.0 * body * bulge[ids] + 5.0 * (face - 0.5) - 2.5 * pits, -2.5 + 0.8 * mortar_n)
    save("villa_ashlar_nor.jpg", normal_map(h, 0.9), data=True)

    col = colour[ids]
    col = col * (0.84 + 0.3 * mott)[..., None] * (0.9 + 0.2 * grain)[..., None]
    col = col * (0.8 + 0.3 * face)[..., None]                         # the tooling catches light and dirt
    col = col * (0.7 + 0.3 * body)[..., None]                         # grime toward the joints
    col = col * (1.0 - 0.35 * pits)[..., None]
    mortar = MORTAR * (0.62 + 0.12 * mortar_n)[..., None]             # recessed: in shadow
    col = np.where(stone[..., None], col, mortar)
    save("villa_ashlar_diff.jpg", col)

    rough = np.where(stone, 0.74 + 0.16 * (face - 0.5) + rough_k[ids] + 0.1 * pits, 0.93)
    save("villa_ashlar_rough.jpg", rough, data=True)


ROOF_SRC = os.path.join(os.path.expanduser("~"), "Desktop", "ref", "villas", "roof-tiles.jpeg")
COLUMN_M = 0.21                 # one column of tiles (cap and pan), metres


def _pixels(img):
    w, h = img.size
    a = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)[..., :3].copy()


def _blur(x, s):
    """Gaussian blur, sigma s px, wrapping round (the map tiles)."""
    fy, fx = np.fft.fftfreq(x.shape[0])[:, None], np.fft.fftfreq(x.shape[1])[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(x) * np.exp(-2 * (np.pi * s) ** 2 * (fx ** 2 + fy ** 2))))


def _period(signal, lo=40, hi=400):
    s = signal - signal.mean()
    ac = np.correlate(s, s, "full")[len(s) - 1:]
    return int(np.argmax(ac[lo:hi]) + lo)


def bake_roof(src=ROOF_SRC, blend=24):
    a = _pixels(bpy.data.images.load(src))                  # rows from the bottom, sRGB values
    h, w = a.shape[:2]
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    col, course = _period(lum.mean(0)), _period(lum.mean(1))
    # Down the slope: cut at the row where the courses line up best with the first rows, and
    # fade the first rows into what follows the cut, so the bottom runs on into the top
    lo = max(h - 2 * course - 20, h // 2)
    r = min(range(lo, h - blend), key=lambda i: float(np.abs(a[i:i + blend] - a[:blend]).mean()))
    out = a[:r].copy()
    t = (np.arange(blend, dtype=np.float32) / blend)[:, None, None]
    out[:blend] = (1 - t) * a[r:r + blend] + t * a[:blend]
    print(f"roof source {w} x {h}: columns every {col} px, courses every {course} px, cut at {r}")

    img = bpy.data.images.new("roof_cut", w, r, alpha=False)
    px = np.ones((r, w, 4), np.float32)
    px[..., :3] = out
    img.pixels.foreach_set(px.ravel())
    img.scale(N, N)
    a = _pixels(img)
    save("villa_roof_tiles_diff.jpg", a)

    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    hp = _blur(lum, 1.2) - _blur(lum, 18.0)                 # tile bodies up, gaps and lip shadows down
    hp /= hp.std() + 1e-6
    save("villa_roof_tiles_nor.jpg", normal_map(hp * 2.2, 1.0), data=True)
    dark = np.clip(0.5 - hp * 0.25, 0, 1)
    save("villa_roof_tiles_rough.jpg", 0.68 + 0.24 * dark, data=True)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4).reshape(-1, 3).mean(0)
    print(f"villa_roof_tiles: {w / col * COLUMN_M:.3f} x {r / col * COLUMN_M:.3f} m, mean linear colour",
          tuple(round(float(v), 3) for v in lin))


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args or "ashlar" in args:
        bake()
    if not args or "roof" in args:
        i = args.index("roof") + 1 if "roof" in args else len(args)
        bake_roof(args[i] if i < len(args) else ROOF_SRC)
