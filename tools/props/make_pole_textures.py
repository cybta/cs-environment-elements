"""Generates the tileable old utility-pole wood maps (ref: Desktop/ref/old-poll.png) into
cs_environment_elements/props/assets/poles/textures:

  pole_wood_diff_1k.png    orange-brown creosoted wood, grain along V (up the pole),
                           drying checks, grey weathering and small whitish flecks
  pole_wood_rough_1k.png
  pole_wood_nor_gl_1k.png  OpenGL normal

One repeat wraps once round the pole (U) and covers 2 m of its height (V); see
build_electric_pole.py. Noise is built in the frequency domain, so every map tiles.
Headless:  blender -b --factory-startup --python make_pole_textures.py
"""
import os
import numpy as np
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "..", "cs_environment_elements", "props", "assets",
                                    "poles", "textures"))
N = 1024


def fbm(seed, beta=2.0, stretch=1.0, lo=2.0):
    """Tileable 1/f^beta noise in 0..1. stretch < 1 elongates features along U (x)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(N) * N
    fx, fy = np.meshgrid(f / stretch, f)
    r = np.sqrt(fx ** 2 + fy ** 2)
    r[0, 0] = 1
    amp = 1 / np.maximum(r, lo) ** (beta / 2)
    amp[0, 0] = 0
    n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * amp))
    return (n - n.min()) / (n.max() - n.min())


def along_v(seed, beta, stretch):
    """Noise whose features run along V (rows), i.e. up the pole."""
    return fbm(seed, beta, stretch).T.copy()


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def col(c):
    return np.array(c, dtype=np.float32)[None, None, :]


def normal_from(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.dstack((-dx, -dy, np.ones_like(h)))
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n * 0.5 + 0.5


def save(name, arr):
    arr = np.clip(arr, 0, 1)
    if arr.ndim == 2:
        arr = np.dstack([arr] * 3)
    rgba = np.dstack((arr, np.ones((N, N)))).astype(np.float32)
    img = bpy.data.images.new(name, N, N, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(OUT, name)
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    print("saved", name)


os.makedirs(OUT, exist_ok=True)

# grain: long streaks up the pole, plus finer fibres
g1, g2, g3 = along_v(1, 1.8, 0.05), along_v(2, 1.2, 0.12), along_v(3, 0.8, 0.3)
grain = g1 * 0.55 + g2 * 0.3 + g3 * 0.15

# drying checks: thin dark lines along the grain, broken up so they start and stop
c1 = along_v(4, 2.0, 0.015)
check = 1 - smooth(0.0, 0.006, np.abs(c1 - 0.5))
check *= smooth(0.45, 0.65, along_v(5, 2.4, 0.2))

weather = fbm(6, 2.6)                                  # big soft grey/dark patches
dirt = fbm(7, 2.2)

fl = fbm(8, 1.2) * 0.8 + fbm(9, 0.6) * 0.2             # small whitish flecks (ref: white specks)
q = np.quantile(fl, 0.975)
fleck = smooth(q - 0.004, q + 0.01, fl)

diff = lerp(col((0.36, 0.19, 0.11)), col((0.64, 0.40, 0.26)), smooth(0.15, 0.85, grain))
diff = lerp(diff, col((0.44, 0.38, 0.33)), smooth(0.55, 0.9, weather) * 0.45)   # sun-greyed
diff = lerp(diff, diff * 0.65, smooth(0.6, 0.95, dirt) * 0.6)                     # damp / dirt
diff = lerp(diff, col((0.10, 0.06, 0.04)), check * 0.85)
diff = lerp(diff, col((0.82, 0.80, 0.75)), fleck * 0.85)
save("pole_wood_diff_1k.png", diff)

rough = 0.72 + 0.14 * grain + 0.1 * smooth(0.55, 0.9, weather)
rough = rough * (1 - check) + 0.95 * check
rough = rough * (1 - fleck) + 0.6 * fleck
save("pole_wood_rough_1k.png", rough)

height = grain * 0.35 + g3 * 0.15 - check * 0.9 + fleck * 0.15
save("pole_wood_nor_gl_1k.png", normal_from(height, 5.0))
print("POLE TEXTURES DONE")
