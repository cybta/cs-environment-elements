"""Bush growth rules. A bush has no wood: it is a rosette of leaf cards that start close
together near the ground and open up towards the top, with flower cards sitting on the crown."""

import math

import numpy as np

from .skeleton import GOLDEN_ANGLE, UP, Skeleton, lerp

LEAF, FLOWER = 0, 1                 # cells of the bush texture, and the card each anchor uses


def grow_bush(p, rng):
    H = p["height"]
    rx = 0.5 * p["canopy"]
    sk = Skeleton()

    def reach(tilt):
        """Distance from the base to the crown outline (half an ellipsoid), `tilt` from vertical."""
        return 1.0 / math.sqrt((math.sin(tilt) / rx) ** 2 + (math.cos(tilt) / H) ** 2)

    def to_outline(base, d):
        """Distance from `base` along unit vector `d` to the crown outline."""
        scale = np.array([1.0 / rx, 1.0 / rx, 1.0 / H])
        o, v = base * scale, d * scale
        a, b, c = float(v @ v), float(o @ v), float(o @ o) - 1.0
        return (-b + math.sqrt(max(b * b - a * c, 0.0))) / a

    # Leaves: rooted over a patch of ground round the centre, upright in the middle and
    # leaning further out towards the rim. Each card also arches away from the centre (the
    # card's tip droop), which opens the bush up at the top.
    count = max(8, round(90 * p["density"]))
    patch = 0.5 * rx
    for i in range(count):
        t = math.sqrt((i + rng.uniform(0.2, 0.8)) / count)
        tilt = math.radians(lerp(6.0, 58.0, t) + rng.uniform(-8.0, 8.0))
        azimuth = i * GOLDEN_ANGLE + rng.uniform(-0.4, 0.4)
        out = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
        base = out * (patch * t) + UP * rng.uniform(0.0, 0.05 * H)
        d = out * math.sin(tilt) + UP * math.cos(tilt)
        length = to_outline(base, d) * rng.uniform(0.75, 1.0)
        flip = -1.0 if rng.random() < 0.5 else 1.0
        sk.leaf(base, d, (length * flip, length, length),
                roll=rng.uniform(-0.45, 0.45), variant=LEAF)

    # Flowers: flat on the crown, facing outward. Low ranks, so a tight budget drops them last.
    flowers = p["flowers"]
    for k in range(flowers):
        tilt = math.radians(lerp(5.0, 56.0, math.sqrt((k + rng.uniform(0.2, 0.8)) / flowers)))
        azimuth = k * GOLDEN_ANGLE + rng.uniform(-0.5, 0.5) + 1.0
        out = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
        side = np.array([-out[1], out[0], 0.0])
        normal = out * math.sin(tilt) + UP * math.cos(tilt)
        spin = rng.uniform(0.0, 2.0 * math.pi)
        tangent = side * math.cos(spin) + np.cross(normal, side) * math.sin(spin)
        size = 0.17 * p["canopy"] * rng.uniform(0.65, 1.2)
        sk.leaf(normal * reach(tilt) * rng.uniform(0.74, 0.88), tangent, (size, size, size),
                roll=rng.uniform(-0.3, 0.3), rank=rng.uniform(0.0, 0.45), up=tuple(normal),
                variant=FLOWER)
    return sk
