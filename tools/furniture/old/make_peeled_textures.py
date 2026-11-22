"""Generates the tileable worn textures for the playground set into ../textures:

  peeled_<colour>_rust_diff_1k.png   paint flaking off steel down to rust
  peeled_<colour>_wood_diff_1k.png   paint flaking off planks down to grey weathered wood
  peeled_rust_rough_1k.png / peeled_rust_nor_gl_1k.png   shared by all *_rust colours
  peeled_wood_rough_1k.png / peeled_wood_nor_gl_1k.png   shared by all *_wood colours
  galv_worn_diff / _rough / _metal / _nor_gl _1k.png     worn galvanised sheet (slide chute)

Every map tiles (noise is built in the frequency domain, so it is periodic).
Colours are sRGB. One repeat covers TILE = 0.6 m like the rest of the set.
Headless:  blender -b --factory-startup --python make_peeled_textures.py
"""
import os, numpy as np, bpy
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "textures"))
N = 1024

PAINTS = {   # sRGB, faded outdoor enamel
    "red":    (0.60, 0.15, 0.12),
    "blue":   (0.15, 0.38, 0.60),
    "green":  (0.17, 0.44, 0.24),
    "yellow": (0.86, 0.62, 0.13),
    "dark":   (0.19, 0.19, 0.19),
}

def fbm(seed, beta=2.0, stretch=1.0, lo=2.0):
    """Tileable 1/f^beta noise in 0..1. stretch < 1 elongates features along U (x)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(N)*N
    fx, fy = np.meshgrid(f/stretch, f)
    r = np.sqrt(fx**2 + fy**2); r[0, 0] = 1
    amp = 1/np.maximum(r, lo)**(beta/2); amp[0, 0] = 0
    spec = np.fft.fft2(rng.standard_normal((N, N)))*amp
    n = np.real(np.fft.ifft2(spec))
    return (n - n.min())/(n.max() - n.min())

def smooth(e0, e1, x):
    t = np.clip((x - e0)/(e1 - e0), 0, 1); return t*t*(3 - 2*t)

def normal_from(h, strength):
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1))*strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0))*strength
    n = np.dstack((-dx, -dy, np.ones_like(h)))
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n*0.5 + 0.5

def save(name, arr):
    arr = np.clip(arr, 0, 1)
    if arr.ndim == 2: arr = np.dstack([arr]*3)
    rgba = np.dstack((arr, np.ones((N, N)))).astype(np.float32)
    img = bpy.data.images.new(name, N, N, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = os.path.join(OUT, name); img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img); print("saved", name)

def lerp(a, b, t): return a + (b - a)*t[..., None]
def col(c): return np.array(c, dtype=np.float32)[None, None, :]

# ---------------- shared peel pattern ----------------
big, mid, fine = fbm(1, 2.2), fbm(2, 1.6), fbm(3, 1.0)
p = big*0.65 + mid*0.25 + fine*0.10
thr = np.quantile(p, 0.70)                       # ~30 % of the paint is gone
peel = smooth(thr - 0.004, thr + 0.004, p)       # 1 = paint missing
lip = smooth(thr - 0.035, thr - 0.004, p)*(1 - peel)        # lifting paint edge
chips = smooth(0.80, 0.83, fbm(4, 0.6))*(1 - peel)          # tiny chips elsewhere
peel = np.maximum(peel, chips)
grime = fbm(5, 2.6)                              # low-frequency dirt / fading
speck = fbm(6, 0.4)

# paint layer (colour applied later): fade + dirt + fine speckle; lighter near lifting edges
paint_shade = (0.80 + 0.30*grime)[..., None] * (0.93 + 0.12*speck)[..., None]
chalk = (0.25*smooth(0.4, 0.9, grime) + 0.15*lip)

# rust underlay
r1, r2 = fbm(7, 1.4), fbm(8, 2.4)
rust = lerp(col((0.20, 0.09, 0.05)), col((0.48, 0.22, 0.08)), smooth(0.35, 0.75, r1))
rust = lerp(rust, col((0.10, 0.06, 0.04)), smooth(0.55, 0.85, r2)*0.7)
# grey weathered wood underlay, grain along U
g1, g2 = fbm(9, 1.8, stretch=0.06), fbm(10, 1.2, stretch=0.15)
wood = lerp(col((0.27, 0.24, 0.20)), col((0.47, 0.44, 0.39)), smooth(0.2, 0.8, g1*0.7 + g2*0.3))

for kind, under in (("rust", rust), ("wood", wood)):
    for name, c in PAINTS.items():
        paint = col(c)*paint_shade
        paint = lerp(paint, np.ones_like(paint)*0.80, chalk*0.5)          # chalky fade
        diff = lerp(paint, under, peel)
        diff = lerp(diff, diff*0.55, lip*0.5)                         # shadow under lifted edge
        save(f"peeled_{name}_{kind}_diff_1k.png", diff)
    rough_under = 0.85 + 0.10*(r1 if kind == "rust" else g1)
    rough = (0.50 + 0.18*grime + 0.06*speck)*(1 - peel) + rough_under*peel
    save(f"peeled_{kind}_rough_1k.png", rough)
    tex = (r2*0.4 + fine*0.6) if kind == "rust" else g1
    height = (1 - peel)*0.6 + lip*0.25 + tex*0.25
    save(f"peeled_{kind}_nor_gl_1k.png", normal_from(height, 6.0))

# ---------------- worn galvanised sheet ----------------
s1, s2, s3, s4 = fbm(11, 0.8), fbm(12, 2.0, stretch=0.08), fbm(13, 2.2), fbm(14, 2.6)
base = 0.56 + 0.14*s1 - 0.18*smooth(0.45, 0.85, s2)            # spangle + streaks along the slide
base = base - 0.22*smooth(0.45, 0.8, s4)                         # dull dark oxidation patches
sp = s3*0.75 + fine*0.25; q = np.quantile(sp, 0.90)
spot = smooth(q - 0.01, q + 0.015, sp)                           # ~10 % rust spots
halo = smooth(q - 0.06, q, sp)*(1 - spot)                        # brown stain round each spot
galv = np.dstack([base]*3)*col((1.0, 1.0, 1.02))
galv = lerp(galv, galv*col((0.85, 0.68, 0.52)), halo*0.8)
galv = lerp(galv, rust, spot)
save("galv_worn_diff_1k.png", galv)
save("galv_worn_rough_1k.png", np.minimum(0.30 + 0.2*smooth(0.4, 0.9, s2) + 0.25*smooth(0.45, 0.8, s4) + 0.3*halo + 0.6*spot, 0.95))
save("galv_worn_metal_1k.png", 1 - spot*0.95 - halo*0.3)
save("galv_worn_nor_gl_1k.png", normal_from(spot*0.5 + s1*0.15, 4.0))
print("TEXTURES DONE")
