"""The east side's ground made level (user, 2026-11-25: "the land should be flattened and the fences should be
straight on the Z axis").

One height, LEVEL (the median ground under the lots and the parking), over every lot, parking pad and street (with
its sidewalks), EDGE m past them, blended back into the valley's terrain over BLEND m round them. A street where the
ground falls away more than DROP below the level (the bridge road down to the bridge) keeps the terrain there.

FlatGround stands in for old_neighborhood.terrain.Terrain (height / z / water), so the terrain preview, the
buildings, the sidewalks and the fences all stand on the level ground and every fence runs level. The game's
heightmap is NOT changed here: the terrain step has to flatten it the same way (east_built.json "ground").
"""
import numpy as np

from old_neighborhood.drawn import inside

from .surfaces import _nearest, _segments

STEP = 0.5          # m, the raster the blend is worked out on
BLEND = 12.0        # m from the level ground back to the terrain
DROP = 1.5          # m: street ground lower than level - DROP keeps the terrain (the bridge road's bank)
EDGE = 1.0          # m: the level reaches this far past the lots, pads and streets


def _box_blur(a, r):
    """Mean over a (2r+1)-cell window along each axis, two passes (zeros outside): a soft falloff."""
    for _ in range(2):
        for axis in (0, 1):
            pad = [(r + 1, r) if ax == axis else (0, 0) for ax in (0, 1)]
            c = np.cumsum(np.pad(a, pad), axis=axis)
            k = 2 * r + 1
            a = (c[k:] - c[:-k]) / k if axis == 0 else (c[:, k:] - c[:, :-k]) / k
    return a


def _grow(m, n):
    for _ in range(n):
        g = m.copy()
        g[1:] |= m[:-1]
        g[:-1] |= m[1:]
        g[:, 1:] |= m[:, :-1]
        g[:, :-1] |= m[:, 1:]
        m = g
    return m


class FlatGround:
    def __init__(self, terrain, plan):
        self.t = terrain
        polys = [np.array(L["outline"], float) for L in plan["lots"]] + \
                [np.array(p["outline"], float) for p in plan["parking"]]
        h = plan["road_width_m"] / 2 + plan["sidewalk_width_m"]
        for c in plan.get("cul_de_sacs", []):            # a cul-de-sac's plaza and the strip on past it, level too
            a, b = np.array(c["lane"], float)
            n = np.array([-c["dir"][1], c["dir"][0]]) * h
            polys += [np.array(c["plaza"], float), np.array([a + n, b + n, b - n, a - n])]
        every = np.vstack(polys + [np.array(r, float) for r in plan["roads"]])
        lo, hi = every.min(0) - 2 * BLEND - 10, every.max(0) + 2 * BLEND + 10
        xs, ys = np.arange(lo[0], hi[0], STEP), np.arange(lo[1], hi[1], STEP)
        gx, gy = np.meshgrid(xs, ys)
        P = np.stack([gx.ravel(), gy.ravel()], -1)
        h0 = terrain.height(P)
        area = np.zeros(len(P), bool)
        for poly in polys:
            area |= inside(P, poly)
        self.level = float(np.median(h0[area]))
        half = plan["road_width_m"] / 2
        da = _nearest(P, _segments(plan["roads"]))[0]
        dw = _nearest(P, _segments([r for r, w in zip(plan["roads"], plan["road_sidewalks"]) if w]))[0]
        street = ((da <= half) | (dw <= half + plan["sidewalk_width_m"])) & (h0 >= self.level - DROP)
        zone = _grow((area | street).reshape(gy.shape), int(round(EDGE / STEP)))
        s = np.clip(2 * _box_blur(zone.astype(float), max(1, int(BLEND / 2 / STEP))), 0, 1)
        w = s * s * (3 - 2 * s)
        w[zone] = 1.0
        h0 = h0.reshape(gy.shape)
        self.h = h0 * (1 - w) + self.level * w
        self.x0, self.y0, self.nx, self.ny = xs[0], ys[0], len(xs), len(ys)
        cut = h0 - self.level
        self.report = "ground levelled at %.2f m: cut up to %.1f m, filled up to %.1f m" % (
            self.level, max(cut[zone].max(), 0), max(-cut[zone].min(), 0))

    def height(self, pts):
        """Like Terrain.height: bilinear, the levelled raster where it covers, the terrain elsewhere."""
        pts = np.atleast_2d(np.asarray(pts, float))
        out = self.t.height(pts)
        c, r = (pts[:, 0] - self.x0) / STEP, (pts[:, 1] - self.y0) / STEP
        on = (c >= 0) & (c < self.nx - 1) & (r >= 0) & (r < self.ny - 1)
        if on.any():
            c0, r0 = np.floor(c[on]).astype(int), np.floor(r[on]).astype(int)
            fc, fr = c[on] - c0, r[on] - r0
            h = self.h
            out[on] = (h[r0, c0] * (1 - fc) + h[r0, c0 + 1] * fc) * (1 - fr) + \
                      (h[r0 + 1, c0] * (1 - fc) + h[r0 + 1, c0 + 1] * fc) * fr
        return out

    def z(self, x, y):
        return float(self.height([(x, y)])[0])

    def water(self, pts):
        return self.t.water(pts)

    def record(self):
        """For east_built.json: how the terrain step must level the game's heightmap."""
        return dict(level_m=round(self.level, 3), blend_m=BLEND, edge_m=EDGE, street_drop_m=DROP,
                    note="lots, parking pads and streets (+ sidewalks) EDGE m wider set to level_m; streets whose "
                         "ground is lower than level_m - street_drop_m keep the terrain; blended back over blend_m "
                         "(east/ground.py)")
