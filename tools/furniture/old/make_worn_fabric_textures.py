"""Generates the tileable worn upholstery textures for the old sofas into ../textures:

  fabric_plaid_worn_diff_1k.png    sun-faded, yellowed brown/cream gingham with grime
                                   blotches, ring stains, pilling and threadbare spots
  fabric_plaid_worn_rough_1k.png   / fabric_plaid_worn_nor_gl_1k.png   (weave, pills, creases)
  velvet_green_worn_diff_1k.png    faded green velvet, crushed-nap streaks, bald patches
                                   showing the tan backing, grime and stains
  velvet_green_worn_rough_1k.png   / velvet_green_worn_nor_gl_1k.png
  stuffing_foam_diff_1k.png        yellowed old foam / cotton wadding seen through tears
  stuffing_foam_nor_gl_1k.png

Every map tiles. Colours are sRGB. One repeat covers FABRIC_TILE = 0.5 m (sofa_lib.py),
so the plaid keeps 8 checks per repeat like the clean fabric_plaid_512.png.
Headless:  blender -b --factory-startup --python make_worn_fabric_textures.py
"""
import os, numpy as np, bpy
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "textures"))
N = 1024

def fbm(seed, beta=2.0, stretch=1.0, lo=2.0):
    """Tileable 1/f^beta noise in 0..1. stretch < 1 elongates features along U (x)."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(N)*N
    fx, fy = np.meshgrid(f/stretch, f)
    r = np.sqrt(fx**2 + fy**2); r[0, 0] = 1
    amp = 1/np.maximum(r, lo)**(beta/2); amp[0, 0] = 0
    n = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N)))*amp))
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

def lerp(a, b, t): return a + (b - a)*np.asarray(t)[..., None]
def col(c): return np.array(c, dtype=np.float32)[None, None, :]

def ring_stains(seed, count, r_lo, r_hi):
    """Tileable water / drink ring stains: (fill, rim) masks in 0..1."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:N, 0:N].astype(np.float32)
    fill, rim = np.zeros((N, N)), np.zeros((N, N))
    wob = fbm(seed + 100, 2.0)
    for _ in range(count):
        cx, cy, r = rng.random()*N, rng.random()*N, rng.uniform(r_lo, r_hi)
        dx = np.abs(x - cx); dx = np.minimum(dx, N - dx)
        dy = np.abs(y - cy); dy = np.minimum(dy, N - dy)
        d = np.sqrt(dx*dx*rng.uniform(0.7, 1.3) + dy*dy)/r + (wob - 0.5)*0.5
        s = rng.uniform(0.5, 1.0)
        fill = np.maximum(fill, (1 - smooth(0.7, 1.0, d))*s)
        rim = np.maximum(rim, smooth(0.8, 0.97, d)*(1 - smooth(0.97, 1.08, d))*s)
    return fill, rim

# ---------------- shared wear layers ----------------
x = np.arange(N)
grime = fbm(21, 2.6)                                # low-frequency dirt / body oil
blot = smooth(0.55, 0.85, fbm(22, 2.2))             # darker grime blotches
fade = fbm(23, 2.8)                                 # uneven sun fading
pill = smooth(0.78, 0.86, fbm(24, 0.3))             # fuzz balls
bare = smooth(0.70, 0.80, fbm(25, 1.6)*0.7 + fbm(26, 0.8)*0.3)   # threadbare spots
crease = fbm(27, 2.0, stretch=0.25)                 # soft creases mostly along U
fill, rim = ring_stains(29, 3, 60, 140)

# ---------------- worn plaid ----------------
band = ((x*8//N) % 2 == 0).astype(np.float32)
h, v = band[None, :], band[:, None]
t = h + v                                           # 0 light, 1 mid, 2 dark
# soften the check edges a little (worn, bled dye)
k = np.exp(-0.5*(np.arange(-6, 7)/2.5)**2); k /= k.sum()
blur = lambda a: np.real(np.fft.ifft2(np.fft.fft2(a)*np.fft.fft2(np.pad(
    k[:, None]*k[None, :], ((0, N - 13), (0, N - 13))))))
t = np.roll(np.roll(blur(t), -6, 0), -6, 1)
dark, mid, light = col((0.27, 0.23, 0.19)), col((0.43, 0.38, 0.32)), col((0.64, 0.60, 0.50))
plaid = lerp(lerp(light, mid, np.clip(t, 0, 1)), dark, np.clip(t - 1, 0, 1))
weave_u = ((x[None, :] + x[:, None]) % 4 < 2).astype(np.float32)       # twill diagonal
thread = 0.5 + 0.5*np.sin(x*np.pi/2)[None, :]*np.sin(x*np.pi/2)[:, None]
plaid = plaid*(0.92 + 0.08*weave_u)[..., None]
# faded and yellowed: pull toward a dusty beige, unevenly
plaid = lerp(plaid, col((0.60, 0.55, 0.44)), 0.25 + 0.25*smooth(0.3, 0.8, fade))
plaid = plaid*col((1.0, 0.97, 0.88))
plaid = lerp(plaid, plaid*col((0.70, 0.62, 0.50)), 0.35*grime + 0.35*blot)   # dirt
plaid = lerp(plaid, plaid*col((0.78, 0.68, 0.52)), fill*0.35)                # stain fill
plaid = lerp(plaid, plaid*col((0.55, 0.45, 0.33)), rim*0.40)                 # stain tide line
plaid = lerp(plaid, col((0.70, 0.66, 0.57))*(0.9 + 0.1*thread)[..., None], bare*0.55)  # threadbare
plaid = lerp(plaid, plaid*1.12 + 0.03, pill*0.6)                             # light fuzz
save("fabric_plaid_worn_diff_1k.png", plaid)
save("fabric_plaid_worn_rough_1k.png", 0.86 + 0.08*grime - 0.10*blot - 0.08*rim + 0.06*pill)
height = 0.35*weave_u + 0.15*thread + 0.6*pill - 0.25*bare*weave_u + 1.2*crease
save("fabric_plaid_worn_nor_gl_1k.png", normal_from(height, 3.0))

# ---------------- worn green velvet ----------------
nap = fbm(31, 1.8, stretch=0.12)                    # crushed-nap streaks
nap2 = fbm(32, 2.4, stretch=0.4)
bald = smooth(0.60, 0.80, fbm(33, 2.8)*0.85 + fbm(34, 1.2)*0.15)   # pile worn to backing
velvet = lerp(col((0.08, 0.14, 0.05)), col((0.20, 0.29, 0.13)), smooth(0.25, 0.85, nap*0.7 + nap2*0.3))
velvet = lerp(velvet, col((0.20, 0.26, 0.14)), 0.35*smooth(0.3, 0.9, fade))   # faded, greyed
velvet = lerp(velvet, velvet*col((0.62, 0.55, 0.40)), 0.35*grime + 0.3*blot)
velvet = lerp(velvet, velvet*col((0.70, 0.60, 0.45)), fill*0.4)
velvet = lerp(velvet, velvet*col((0.45, 0.38, 0.28)), rim*0.35)
backing = col((0.42, 0.40, 0.30))*(0.85 + 0.15*thread)[..., None]
velvet = lerp(velvet, velvet*0.5 + backing*0.5, bald*0.8)
velvet = lerp(velvet, velvet*1.25, pill*0.4)
save("velvet_green_worn_diff_1k.png", velvet)
save("velvet_green_worn_rough_1k.png", 0.80 + 0.10*nap - 0.18*blot + 0.10*bald)
save("velvet_green_worn_nor_gl_1k.png", normal_from(0.4*nap + 0.25*thread*bald - 0.5*bald + crease, 3.0))

# ---------------- exposed stuffing (old foam + cotton wadding) ----------------
pores = fbm(41, 0.2); clumps = fbm(42, 1.6); age = fbm(43, 2.6)
foam = lerp(col((0.60, 0.53, 0.36)), col((0.42, 0.32, 0.17)), smooth(0.3, 0.9, age))   # yellow->tan
foam = lerp(foam, col((0.70, 0.67, 0.58)), smooth(0.6, 0.8, clumps)*0.5)            # cotton wads
foam = foam*(0.80 + 0.30*pores)[..., None]
foam = lerp(foam, foam*0.55, smooth(0.6, 0.9, grime)*0.6)
save("stuffing_foam_diff_1k.png", foam)
save("stuffing_foam_nor_gl_1k.png", normal_from(pores*0.6 + clumps*1.5, 4.0))
print("WORN FABRIC TEXTURES DONE")
