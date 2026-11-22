"""Bake the old fence's paint peel mask into
cs_environment_elements/core/assets/old-fence/fence_paint_mask.png.

The mask is laid out exactly like fence.png (same UVs: 12 planks stacked, U along the
grain). Each pixel holds how long the paint lasts there, 0..1:
  - big worn patches and small flakes, stretched along the grain,
  - board edges wear first,
  - each plank (board) gets its own age, so neighbouring boards differ.
The values are rank-equalised over the planks, so "peeling = 0.4" in the shader removes
about 40 % of the paint, and squeezed into 0.05..0.95 so 0 is fully painted and 1 is bare.

8-bit single-channel PNG, written directly (no colour management in between).
Headless:  blender -b --factory-startup --python make_fence_paint_mask.py
"""

import os
import struct
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from cs_environment_elements.buildings import fence_geom as fg  # noqa: E402

sys.path.insert(0, HERE)
from organic_noise import organic_wear  # noqa: E402

OUT = os.path.join(ROOT, "cs_environment_elements", "core", "assets", "old-fence", "fence_paint_mask.png")
N = 1024
SEED = 7


def fbm(rng, beta, sx=1.0, sy=1.0, lo=4.0):
    """Tileable 1/f^beta noise in 0..1; sx > 1 damps changes along U, so features
    stretch along U (the grain)."""
    f = np.fft.fftfreq(N) * N
    fx, fy = np.meshgrid(f * sx, f * sy)
    r = np.sqrt(fx ** 2 + fy ** 2)
    amp = 1.0 / np.maximum(r, lo) ** (beta / 2)
    amp[0, 0] = 0.0
    n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * amp))
    return (n - n.min()) / (n.max() - n.min())


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def write_png_gray(path, a):
    """a: (rows, cols) uint8, row 0 = top of the picture."""
    raw = b"".join(b"\x00" + a[i].tobytes() for i in range(a.shape[0]))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", a.shape[1], a.shape[0], 8, 0, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fh:
        fh.write(png)


def main():
    rng = np.random.default_rng(SEED)
    # organic chips at every angle (the grain leading), in clumps, with wobbly outlines
    chips = organic_wear(rng, N, grain=0.0, grain_weight=0.4, chip=14.0, clump_weight=0.45)
    # Which plank each picture row belongs to, and where across it (0 = one edge, 1 = the other)
    rows_from_top = (np.arange(N) + 0.5) / N * fg._IMG_H
    plank = np.full(N, -1)
    across = np.zeros(N)
    for i, (y0, y1, _x0, _x1) in enumerate(fg._STRIPS_PX):
        inside = (rows_from_top >= y0) & (rows_from_top <= y1)
        plank[inside] = i
        across[inside] = (rows_from_top[inside] - y0) / (y1 - y0)
    age = rng.uniform(-0.22, 0.22, len(fg._STRIPS_PX))  # some boards newer, some older
    edge = smooth(0.0, 0.16, np.minimum(across, 1.0 - across))[:, None]   # board edges first
    d = chips + 0.25 * edge + np.where(plank >= 0, age[np.maximum(plank, 0)], 0.0)[:, None]

    on = np.broadcast_to((plank >= 0)[:, None], d.shape)
    ranks = np.empty(on.sum())
    ranks[np.argsort(d[on], kind="stable")] = np.linspace(0.0, 1.0, on.sum())
    m = np.full(d.shape, 0.5)
    m[on] = 0.05 + 0.9 * ranks
    write_png_gray(OUT, np.clip(m * 255.0 + 0.5, 0, 255).astype(np.uint8))
    print(f"{OUT}: {N}x{N}, {os.path.getsize(OUT) / 1024:.0f} KB")


main()
