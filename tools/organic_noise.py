"""Organic, tileable wear fields for the peeling-paint bakers (numpy only).

organic_wear() mixes:
  - clumps: big domain-warped patches, so some areas are badly worn and others nearly intact,
  - flakes: several layers of stretched noise, each turned to its own angle, blended by a
    slow random selector, so chips run every which way (the grain direction still leads),
  - a domain warp on everything, so the chip outlines wobble like real flaking paint,
  - fine ragged detail on the edges.
Everything is periodic (built in the frequency domain, sampled with wrap-around), so the
result tiles. Higher value = worn sooner; the bakers rank-equalise it into "durability".
"""

import numpy as np


def fbm(rng, n, beta, lo=2.0, angle=0.0, stretch=1.0):
    """Tileable 1/f^beta noise in 0..1. stretch > 1 elongates the features along `angle`
    (radians, 0 = along x / U)."""
    f = np.fft.fftfreq(n) * n
    fx, fy = np.meshgrid(f, f)
    c, s = np.cos(angle), np.sin(angle)
    fu, fv = fx * c + fy * s, -fx * s + fy * c          # along / across the feature direction
    r = np.sqrt((fu * stretch) ** 2 + fv ** 2)
    amp = 1.0 / np.maximum(r, lo) ** (beta / 2)
    amp[0, 0] = 0.0
    out = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((n, n))) * amp))
    return (out - out.min()) / (out.max() - out.min())


def warp(field, dx, dy):
    """Sample `field` at (x + dx, y + dy) pixels, bilinear, wrapping round (keeps tiling)."""
    n = field.shape[0]
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    x, y = xx + dx, yy + dy
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    x0, y0 = x0 % n, y0 % n
    x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    top = field[y0, x0] * (1 - fx) + field[y0, x1] * fx
    bot = field[y1, x0] * (1 - fx) + field[y1, x1] * fx
    return top * (1 - fy) + bot * fy


def organic_wear(rng, n, grain=0.0, grain_weight=0.45, chip=36.0, clump_weight=0.5, warp_px=None):
    """The wear field (0..1, tileable). grain: the direction (radians) chips favour;
    chip: rough chip size in pixels; clump_weight: how much big patches dominate."""
    warp_px = chip * 0.9 if warp_px is None else warp_px
    lo_chip = n / (chip * 4.0)
    # flake layers: the grain direction plus three random ones, mixed by a slow selector
    angles = [grain] + list(rng.uniform(0, np.pi, 3))
    weights = [grain_weight] + [(1 - grain_weight) / 3] * 3
    sel = [fbm(rng, n, 3.5, lo=1.5) for _ in angles]
    sel = np.stack([s ** 3 * w for s, w in zip(sel, weights)])
    sel /= sel.sum(axis=0, keepdims=True)
    flakes = sum(sel[i] * fbm(rng, n, 2.2, lo=lo_chip, angle=a, stretch=rng.uniform(2.0, 4.0))
                 for i, a in enumerate(angles))
    clumps = fbm(rng, n, 3.2, lo=1.5)
    ragged = fbm(rng, n, 1.2, lo=n / 6.0)
    f = clump_weight * clumps + (1 - clump_weight) * flakes + 0.12 * ragged
    # domain warp: wobble the outlines
    dx = (fbm(rng, n, 3.0, lo=2.0) - 0.5) * 2 * warp_px
    dy = (fbm(rng, n, 3.0, lo=2.0) - 0.5) * 2 * warp_px
    f = warp(f, dx, dy)
    return (f - f.min()) / (f.max() - f.min())
