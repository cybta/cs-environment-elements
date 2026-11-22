"""Species growth rules. Each one turns the panel settings into a Skeleton."""

import math
import random

import numpy as np

from .bushes import grow_bush
from .skeleton import GOLDEN_ANGLE, UP, Skeleton, Warp, horizontal, lerp, rot_z, smooth_joint

# LOD 0 triangle budgets (min, max). Trees are ordinary by default; ticking Hero Tree in the
# panel gives a tree the hero budget. A species with its own "tri_min"/"tri_max" keeps those.
TREE_BUDGET = (500, 3000)
HERO_BUDGET = (25000, 50000)


def budget(species, hero):
    spec = SPECIES[species]
    if "tri_min" in spec:
        return spec["tri_min"], spec["tri_max"]
    return HERO_BUDGET if hero else TREE_BUDGET


START_KEYS = ("height", "bole", "canopy", "trunk_radius", "twist", "lean")


def start_values(species, hero):
    """The species' starting sizes; a hero tree of a species with "hero_size" gets those."""
    spec = SPECIES[species]
    vals = {k: spec[k] for k in START_KEYS}
    if hero:
        vals.update(spec.get("hero_size", {}))
    return vals


# Per-species starting values, applied when the species is picked in the panel.
# "sides" and "segment" (fraction of tree height) set the natural bark resolution.
# "hero_size" replaces the sizes when Hero Tree is ticked (see start_values).
SPECIES = {
    "CEDAR": dict(
        label="Lebanese Cedar",
        description="Thick trunk, wide flat limbs, layered cloud-shaped foliage pads",
        height=12.0, bole=2.5, canopy=17.0, trunk_radius=1.3,
        hero_size=dict(height=22.0, bole=3.5, canopy=28.0, trunk_radius=2.6),
        twist=math.radians(70.0), lean=math.radians(4.0),
        sides=12, segment=0.03, bark_v=0.8, bark_u=5),
    "PINE": dict(
        label="Pine",
        description="Straight trunk with conical tiers of drooping needle boughs",
        height=9.0, bole=0.9, canopy=6.5, trunk_radius=0.2,
        twist=0.0, lean=0.0,
        sides=8, segment=0.06, bark_v=1.0, bark_u=1),
    "OAK": dict(
        label="Oak",
        description="Short thick trunk and gnarled limbs under a broad crown, widest low down "
                    "and tapering to the top",
        height=14.0, bole=2.2, canopy=15.0, trunk_radius=0.8,
        twist=math.radians(12.0), lean=math.radians(2.0),
        sides=10, segment=0.035, bark_v=0.8, bark_u=4),
    "MAPLE": dict(
        label="Maple",
        description="Gnarled limbs under a dense egg-shaped crown of broad leaves",
        height=15.0, bole=2.6, canopy=12.5, trunk_radius=0.7,
        twist=math.radians(12.0), lean=math.radians(2.0),
        sides=10, segment=0.035, bark_v=0.8, bark_u=4),
}
# Bushes ("bush": no wood, only leaf and flower cards; the panel shows the bush settings).
SPECIES["BUSH"] = dict(
    label="Flowering Bush", bush=True,
    description="Leaves that start close together at the ground and open up at the top, with flowers",
    height=0.7, bole=0.0, canopy=1.1, trunk_radius=0.05, twist=0.0, lean=0.0,
    tri_min=200, tri_max=700, sides=6, segment=0.1, bark_v=1.0, bark_u=1)
# Maple colour variants. "mix" is the share of foliage cards using each cell of the leaf
# atlas (green, pale, red); the cells are spread over the crown in patches, not card by card.
SPECIES["MAPLE_AUTUMN"] = dict(
    SPECIES["MAPLE"], label="Autumn Maple", mix=(0.34, 0.30, 0.36),
    description="Maple turning colour: patches of green, pale and red leaves in one crown")
SPECIES["MAPLE_RED"] = dict(
    SPECIES["MAPLE"], label="Red Maple", mix=(0.0, 0.22, 0.78),
    description="Maple in full autumn red, with a few pale patches")


# ----------------------------------------------------------------------------
# Lebanese Cedar
# ----------------------------------------------------------------------------
def grow_cedar(p, rng):
    H = p["height"]
    D = p["canopy"]
    r0 = p["trunk_radius"]
    density = p["density"]
    gnarl = 2.0 * p["gnarl"]             # 1.0 at the default setting
    fluting = p["fluting"]
    root_length = p["root_length"]
    bole = min(p["bole"], 0.6 * H)
    top = 0.78 * H                       # where the trunk dissolves into the top limbs
    card = D * 0.095                     # foliage card length
    reach_max = max(D * 0.5 - 0.75 * card, 0.1 * D)
    sk = Skeleton(Warp(p, top))

    ph1, ph2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)

    def axis(z):
        t = max(z, 0.0) / top
        a = 0.35 * r0 * t * gnarl
        return np.array([math.sin(ph1 + 2.6 * t) * a, math.cos(ph2 + 2.1 * t) * a, z])

    def trunk_r(z):
        t = min(max(z / top, 0.0), 1.0)
        return r0 * (0.74 * (1.0 - 0.66 * t ** 1.2) + 0.26 * math.exp(-max(z, 0.0) / (0.05 * H)))

    n_limbs = max(4, round(15 * density))

    def limb_height(i):
        return lerp(bole, top * 0.97, (i / (n_limbs - 1)) ** 0.85)

    # Trunk strands: each one is a single chain that starts as a root tip, runs up the
    # outside of the trunk as a flute and then peels away as one of the main limbs.
    # They leave at different heights, spread over the lower 80% of the limbs.
    n_strands = min(p["strands"], n_limbs)
    span = 0.8 * (n_limbs - 1)
    strand_limbs = sorted({round(k * span / max(n_strands - 1, 1)) for k in range(n_strands)})
    slots = [k * 2.0 * math.pi / max(len(strand_limbs), 1) for k in range(len(strand_limbs))]
    rng.shuffle(slots)                   # neighbouring strands should not leave one after another
    turn = rng.uniform(0, 6.28)
    strand_az = {i: turn + slot + rng.uniform(-0.2, 0.2) for i, slot in zip(strand_limbs, slots)}
    last_peel = limb_height(strand_limbs[-1]) if strand_limbs else 0.0
    strand_scale = min(max(0.42 * math.sqrt(6.0 / max(len(strand_limbs), 1)), 0.3), 0.55)

    def strand_r(z):
        return trunk_r(z) * strand_scale

    def core_r(z):
        """The core shrinks behind the strands while they are attached, so they read as flutes."""
        if not strand_limbs:
            return trunk_r(z)
        attached = min(max((last_peel - z) / max(last_peel - bole, 1e-3), 0.0), 1.0)
        return trunk_r(z) * (1.0 - 0.25 * fluting * attached)

    def flute_point(az, z, phase):
        a = az + 0.2 * gnarl * math.sin(7.0 * z / top + phase)
        return axis(z) + np.array([math.cos(a), math.sin(a), 0.0]) * trunk_r(z) * (0.58 + 0.2 * fluting)

    def root(az, end, end_r):
        """A surface root running in to `end` on the trunk. Returns it tip first, without
        `end` itself, and adds its side forks to the skeleton."""
        out = np.array([math.cos(az), math.sin(az), 0.0])
        side = np.array([-out[1], out[0], 0.0])
        length = r0 * rng.uniform(1.5, 2.4) * root_length
        wiggle = rng.uniform(-0.25, 0.25)
        phase = rng.uniform(0, 6.28)
        low = -0.12 * r0

        def at(s):
            pos = end + out * (length * s) + side * (
                wiggle * length * s * s + math.sin(s * 5.0 + phase) * 0.06 * length * gnarl * s)
            pos[2] = low + (end[2] - low) * (1.0 - s) ** 1.6
            return pos, lerp(end_r, 0.07 * r0, s ** 0.7)

        n = 7
        for k, s in enumerate((3 / n, 5 / n)):       # on the root's own points, so the fork starts buried
            origin, radius = at(s)
            sign = 1.0 if (k == 0) == (wiggle > 0) else -1.0
            d = rot_z(out, sign * math.radians(rng.uniform(30.0, 55.0)))
            fork_length = length * ((1.0 - s) * rng.uniform(0.7, 1.0) + 0.15)
            pts, radii = [], []
            for u in (0.0, 0.35, 0.7, 1.0):
                pos = origin + d * (fork_length * u)
                pos[2] = lerp(origin[2], low, u ** 0.6)
                pts.append(pos)
                radii.append(radius * 0.55 * (1.0 - u) + 0.03 * r0 * u)
            sk.branch(pts, radii, 2)

        samples = [at(j / n) for j in range(n, 0, -1)]
        return [pos for pos, _ in samples], [radius for _, radius in samples]

    def strand_base(az, z0, phase):
        """The root and flute part of a strand, tip first, stopping just short of height z0."""
        z_start = min(0.43 * r0, 0.5 * z0) if root_length > 0.0 else -0.25
        count = max(2, math.ceil((z0 - z_start) / (top / 12)) + 1)
        zs = [lerp(z_start, z0, k / (count - 1)) for k in range(count - 1)]
        pts = [flute_point(az, z, phase) for z in zs]
        radii = [strand_r(z) for z in zs]
        if root_length > 0.0:
            root_pts, root_radii = root(az, pts[0], radii[0])
            pts, radii = root_pts + pts, root_radii + radii
        return pts, radii

    # Trunk core, ending in a short tapered stub that the top limbs hide.
    zs = [-0.25] + [top * i / 12 for i in range(13)]
    pts = [axis(z) for z in zs]
    radii = [core_r(z) for z in zs]
    pts.append(axis(top) + np.array([0.0, 0.0, radii[-1] * 0.8]))
    radii.append(0.02)
    sk.branch(pts, radii, 0)

    # Without strands the roots attach to the core instead.
    if not strand_limbs and root_length > 0.0:
        n_roots = rng.randint(5, 7)
        for i in range(n_roots):
            az = i * 2 * math.pi / n_roots + rng.uniform(-0.3, 0.3)
            end = np.array([math.cos(az) * 0.25 * r0, math.sin(az) * 0.25 * r0, 0.43 * r0])
            pts, radii = root(az, end, 0.5 * r0)
            sk.branch(pts + [end], radii + [0.5 * r0], 1)

    def add_card(position, direction, pitch=(5.0, 30.0), yaw=35.0):
        d = rot_z(horizontal(direction), math.radians(rng.uniform(-yaw, yaw)))
        a = math.radians(rng.uniform(*pitch))
        size = card * rng.uniform(0.8, 1.2)
        pos = position - d * size * 0.25 + UP * rng.uniform(0.0, 0.12 * card)
        flip = -1.0 if rng.random() < 0.5 else 1.0
        sk.leaf(pos, d * math.cos(a) + UP * math.sin(a), (size * flip, size, size),
                roll=math.radians(rng.uniform(-18.0, 18.0)))

    for i in range(n_limbs):
        t = i / (n_limbs - 1)
        z0 = limb_height(i)
        strand = i in strand_az
        z_pad = lerp(bole + 0.07 * H, H - 0.75 * card, t)       # height of this limb's pad
        az = strand_az[i] if strand else i * GOLDEN_ANGLE + rng.uniform(-0.35, 0.35)
        reach = reach_max * lerp(1.0, 0.5, t ** 1.6) * (1.0 if i == 0 else rng.uniform(0.86, 1.0))
        rise = max(z_pad - z0, 0.0)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        side = np.array([-out[1], out[0], 0.0])
        phase = rng.uniform(0, 6.28)
        if strand:
            base = flute_point(az, z0, phase)
            reach -= float(np.linalg.norm((base - axis(z0))[:2]))
        else:
            base = axis(z0)             # on the trunk axis: the swollen base stays inside the bark
        sway = reach * rng.uniform(0.03, 0.07) * gnarl
        base_r = trunk_r(z0) * lerp(0.42, 0.6, t)

        # Limb: leaves the trunk angled up, then flattens out; low limbs sag at the tip.
        n = 11
        limb, limb_r = [], []
        for j in range(n + 1):
            s = j / n
            ease = 1.0 - (1.0 - min(s / 0.6, 1.0)) ** 2
            pos = base + out * (reach * s) + side * (math.sin(s * 4.7 + phase) * sway * s)
            pos[2] = z0 + rise * ease - 0.08 * p["limb_droop"] * reach * s * s * (1.0 - t) \
                + math.sin(s * 9.0 + phase) * 0.012 * reach * s * gnarl
            limb.append(pos)
            # The base swells (flare) so the limb widens into the trunk instead of
            # leaving it as a cut cylinder.
            swell = 1.0 + 1.1 * p["flare"] * max(1.0 - s / 0.3, 0.0) ** 2
            limb_r.append(base_r * (0.92 * (1.0 - s) ** 0.9 + 0.08) * swell)
        if strand:
            pts, radii = strand_base(az, z0, phase)
            joint = len(pts)
            chain, chain_r = smooth_joint(pts + limb, radii + limb_r, joint)
            limb, limb_r = chain[joint:], chain_r[joint:]
            sk.branch(chain, chain_r, 0)
        else:
            sk.branch(limb, limb_r, 1)

        def limb_at(s):
            f = min(max(s, 0.0), 1.0) * n
            k = min(int(f), n - 1)
            return (limb[k] + (limb[k + 1] - limb[k]) * (f - k),
                    horizontal(limb[k + 1] - limb[k]),
                    lerp(limb_r[k], limb_r[k + 1], f - k))

        # Foliage sitting on the outer limb itself.
        for s in (0.5, 0.62, 0.74, 0.86, 1.0):
            pos, tangent, _ = limb_at(s)
            add_card(pos, tangent, yaw=45.0)

        # Secondary branches fan out sideways in the limb's plane to shape the pad.
        n_sec = max(3, round(lerp(9, 6, t) * math.sqrt(density)))
        for k in range(n_sec):
            s = lerp(0.22, 0.95, (k + rng.uniform(0.2, 0.8)) / n_sec)
            sign = 1.0 if (k + i) % 2 == 0 else -1.0
            origin, tangent, parent_r = limb_at(s)
            angle = sign * math.radians(rng.uniform(45.0, 75.0))
            length = reach * lerp(0.5, 0.2, (s - 0.22) / 0.73) * rng.uniform(0.8, 1.15)
            steps = 5
            pos = origin.copy()
            lift = 1.0 + 0.35 * p["flare"]
            sec, sec_r, sec_dir = [pos.copy()], [(parent_r * 0.55 + 0.012) * lift], []
            for j in range(steps):
                u = (j + 1) / steps
                d = rot_z(tangent, angle * (1.0 - 0.35 * u))
                pos = pos + d * (length / steps) + UP * (0.03 * length / steps)
                sec.append(pos.copy())
                sec_r.append(parent_r * 0.55 * (1.0 - u) ** 0.8 * (1.0 + 0.35 * p["flare"] * (1.0 - u) ** 2)
                             + 0.012)
                sec_dir.append(d)
            sk.branch(sec, sec_r, 2)

            for j in (2, 3, 5):
                add_card(sec[j], sec_dir[j - 1])
                add_card(sec[j], sec_dir[j - 1], pitch=(15.0, 40.0), yaw=60.0)

            # Twigs with upward-tilted sprays give the pad its thickness.
            for j in (2, 4):
                d = rot_z(sec_dir[j - 1], math.radians(rng.uniform(-70.0, 70.0)))
                a = math.radians(rng.uniform(20.0, 45.0))
                d3 = d * math.cos(a) + UP * math.sin(a)
                twig_len = length * rng.uniform(0.25, 0.38)
                twig = [sec[j], sec[j] + d3 * twig_len * 0.5, sec[j] + d3 * twig_len]
                sk.branch(twig, [0.022, 0.014, 0.008], 3)
                add_card(twig[2], d, pitch=(20.0, 45.0), yaw=50.0)
    return sk


# ----------------------------------------------------------------------------
# Pine
# ----------------------------------------------------------------------------
def grow_pine(p, rng):
    """Straight trunk with a cone of drooping boughs. Each bough is real wood that sags under
    its own weight and lifts again at the tip, with needle sprigs fanned out along both sides."""
    H = p["height"]
    D = p["canopy"]
    r0 = p["trunk_radius"]
    density = p["density"]
    gnarl = 2.0 * p["gnarl"]
    droop = 2.0 * p["limb_droop"]
    bole = min(p["bole"], 0.6 * H)
    card = D * 0.21                         # sprig card length on the longest boughs
    sk = Skeleton(Warp(p, H))

    lean = rng.uniform(0, 6.28)

    def axis(z):
        t = max(z, 0.0) / H
        a = 0.6 * r0 * math.sin(t * 3.0) * t * gnarl
        return np.array([math.cos(lean) * a, math.sin(lean) * a, z])

    def trunk_r(z):
        t = min(max(z / H, 0.0), 1.0)
        return r0 * (0.67 * (1.0 - t) ** 0.8 + 0.33 * math.exp(-max(z, 0.0) / (0.04 * H))) + 0.008

    zs = [-0.15] + [H * (i / 11) ** 1.2 for i in range(1, 12)]
    sk.branch([axis(z) for z in zs], [trunk_r(z) for z in zs], 0)

    def add_sprig(position, heading, pitch, size, rank=None):
        d = heading * math.cos(pitch) + UP * math.sin(pitch)
        flip = -1.0 if rng.random() < 0.5 else 1.0
        sk.leaf(position, d, (size * flip, size, size),
                roll=math.radians(rng.uniform(-35.0, 35.0)), rank=rank)

    count = max(10, round(90 * density * (H / 9.0) ** 0.6))
    for i in range(count):
        t = i / (count - 1)
        z0 = lerp(bole, 0.93 * H, t ** 0.9)
        azimuth = i * GOLDEN_ANGLE + rng.uniform(-0.3, 0.3)
        out = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
        side = np.array([-out[1], out[0], 0.0])
        # Cone profile; the very lowest boughs are a little shorter, like shaded old growth.
        reach = 0.5 * D * (0.93 * (1.0 - t) ** 0.85 + 0.07) * (0.8 + 0.2 * min(t / 0.12, 1.0))
        reach *= rng.uniform(0.82, 1.0)
        rise = reach * math.tan(math.radians(lerp(8.0, 42.0, t) + rng.uniform(-6.0, 6.0)))
        sag = reach * lerp(0.55, 0.12, t) * droop
        curl = reach * 0.1
        phase = rng.uniform(0, 6.28)
        base = axis(z0)
        base_r = max(trunk_r(z0) * 0.26, 0.014)

        n = 7
        bough, bough_r = [], []
        for j in range(n + 1):
            s = j / n
            pos = base + out * (reach * s) + side * (math.sin(s * 5.0 + phase) * 0.05 * reach * gnarl * s)
            pos[2] = z0 + rise * s - sag * s * s + curl * s ** 4 \
                + math.sin(s * 8.0 + phase) * 0.015 * reach * gnarl * s
            pos[2] = max(pos[2], 0.2 + 0.1 * s)          # never into the ground
            bough.append(pos)
            bough_r.append(base_r * (1.0 - s) ** 0.9 + 0.006)
        sk.branch(bough, bough_r, 1)

        def bough_at(s):
            f = min(max(s, 0.0), 1.0) * n
            k = min(int(f), n - 1)
            tan = bough[k + 1] - bough[k]
            tan = tan / max(np.linalg.norm(tan), 1e-6)
            return bough[k] + (bough[k + 1] - bough[k]) * (f - k), tan

        size = card * min(max(reach / (0.5 * D) * 1.3 + 0.3, 0.42), 1.0)
        # Tip sprig continues the bough; it is the last to be culled so the cone outline holds.
        tip, tan = bough_at(1.0)
        add_sprig(tip - tan * size * 0.25, horizontal(tan), math.asin(max(min(tan[2], 1.0), -1.0)),
                  size, rank=(i * 0.7548776662) % 0.3)
        # Side sprigs alternate left and right, angled forward and hanging slightly.
        n_side = max(3, round(reach / (0.15 * size)))
        for k in range(n_side):
            s = lerp(0.15, 0.95, (k + rng.uniform(0.3, 0.7)) / n_side)
            pos, tan = bough_at(s)
            sign = 1.0 if (k + i) % 2 == 0 else -1.0
            slope = math.asin(max(min(tan[2], 1.0), -1.0))
            if k % 3 == 2:
                # Every third sprig hangs under the bough: this is what fills the tree from the side.
                heading = rot_z(horizontal(tan), sign * math.radians(rng.uniform(5.0, 30.0)))
                pitch = slope - math.radians(rng.uniform(35.0, 60.0))
            else:
                heading = rot_z(horizontal(tan), sign * math.radians(rng.uniform(38.0, 68.0)))
                pitch = slope - math.radians(rng.uniform(8.0, 28.0))
            add_sprig(pos, heading, pitch, size * lerp(1.0, 0.8, s) * rng.uniform(0.85, 1.1))

    # Leader: a ring of upright sprigs round the tip and one straight up.
    # Sized from the canopy width, so the tip narrows and widens with the rest of the cone.
    spire = min(0.19 * D, 0.3 * H)
    top = axis(H - 0.72 * spire)
    for k in range(4):
        a = k * math.pi / 2 + rng.uniform(-0.3, 0.3)
        add_sprig(top + UP * rng.uniform(-0.03, 0.03) * H, np.array([math.cos(a), math.sin(a), 0.0]),
                  math.radians(rng.uniform(50.0, 68.0)), spire * 0.9, rank=0.0)
    for k in range(2):
        a = k * math.pi / 2 + 0.4
        sk.leaf(axis(H) - UP * spire * 0.85, (0.0, 0.0, 1.0), (spire, spire, spire), rank=0.0,
                up=(math.sin(a), -math.cos(a), 0.0))
    return sk


# ----------------------------------------------------------------------------
# Broadleaves: oak and maple
# ----------------------------------------------------------------------------
# Crown outline. "widest": how far up the crown (0 bottom, 1 top) the widest ring sits.
# "taper": 2 gives a rounded dome above that ring, towards 1 a straight-sided cone.
# "low": sine of the lowest limb's elevation seen from the crown centre.
# "limbs": main limbs at density 1. "bias": above 1 puts more of them low, to fill a wide base.
CROWNS = {
    "OAK": dict(widest=0.16, taper=1.35, low=-0.12, limbs=17, bias=1.5),     # broad base, near-triangular
    "MAPLE": dict(widest=0.36, taper=2.0, low=-0.5, limbs=13, bias=1.0),     # egg, fat end down
}


def grow_broadleaf(p, rng, crown):
    """Short, thick bole that forks into big limbs; limbs snake, fork again and end in twigs
    that carry leaf sprigs. Branch ends are steered onto the crown envelope, which gives the
    species its silhouette, with the inner branching visible through gaps."""
    H = p["height"]
    D = p["canopy"]
    r0 = p["trunk_radius"]
    density = p["density"]
    gnarl = 2.0 * p["gnarl"]
    bole = min(p["bole"], 0.5 * H)
    card = D * 0.11                        # sprig card length
    sk = Skeleton(Warp(p, 0.7 * H))

    ph1, ph2 = rng.uniform(0, 6.28), rng.uniform(0, 6.28)
    fork_top = bole + 0.28 * (H - bole)    # trunk leader fades out here

    def axis(z):
        t = max(z, 0.0) / fork_top
        a = 0.28 * r0 * t * gnarl
        return np.array([math.sin(ph1 + 2.2 * t) * a, math.cos(ph2 + 1.9 * t) * a, z])

    def trunk_r(z):
        t = min(max(z / fork_top, 0.0), 1.0)
        return r0 * (0.72 * (1.0 - 0.5 * t) + 0.28 * math.exp(-max(z, 0.0) / (0.06 * H)))

    # Crown envelope: an egg, fat end down. Two half-ellipsoids share the widest ring at cz:
    # a shallow one below and a tall one above.
    cz = bole + crown["widest"] * (H - bole)
    rz_top = H - cz
    rz_bottom = cz - 0.8 * bole
    rx = D * 0.5

    def crown_norm(v):
        """1 on the crown surface, less inside. The lower half is always a shallow ellipsoid."""
        n, rz = (crown["taper"], rz_top) if v[2] >= 0.0 else (2.0, rz_bottom)
        return ((math.hypot(v[0], v[1]) / rx) ** n + (abs(v[2]) / rz) ** n) ** (1.0 / n)

    def envelope(direction, fill=1.0):
        """Point of the crown surface (scaled by fill) in the direction of `direction`."""
        d = np.asarray(direction, float)
        d = d / max(np.linalg.norm(d), 1e-6)
        k = 1.0 / crown_norm(d)
        return np.array([0.0, 0.0, cz]) + d * k * fill

    zs = [-0.2] + [fork_top * i / 8 for i in range(9)]
    sk.branch([axis(z) for z in zs], [trunk_r(z) for z in zs], 0)

    # Buttress roots: short, fat, mostly buried.
    for i in range(5):
        az = i * 2 * math.pi / 5 + rng.uniform(-0.3, 0.3)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        ln = r0 * rng.uniform(1.0, 1.6)
        pts = [out * (ln * s) + np.array([0.0, 0.0, 0.35 * r0 * (1 - s) ** 1.7 - 0.1 * r0 * s]) for s in (1.0, 0.7, 0.4, 0.1)]
        sk.branch(pts + [axis(0.25 * r0)], [0.07 * r0, 0.17 * r0, 0.3 * r0, 0.5 * r0, 0.62 * r0], 1)

    def add_sprig(position, outward, spread=1.0):
        """A foliage card: tilted any way, but biased to face outward/up like sunlit leaf clusters."""
        d = np.asarray(outward, float)
        d = d / max(np.linalg.norm(d), 1e-6)
        d = d + np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.6, 1.0)]) * spread
        d = d / max(np.linalg.norm(d), 1e-6)
        size = card * rng.uniform(0.75, 1.25)
        flip = -1.0 if rng.random() < 0.5 else 1.0
        sk.leaf(position - d * size * 0.2, d, (size * flip, size, size),
                roll=rng.uniform(-1.4, 1.4))

    centre = np.array([0.0, 0.0, cz])

    def crown_fraction(pos):
        return crown_norm(pos - centre)

    def side_branch(origin, direction, length, radius, level, limit):
        """A wandering branch clipped to the crown. Returns its points and final direction."""
        d = np.asarray(direction, float)
        d = d / max(np.linalg.norm(d), 1e-6)
        e = crown_fraction(origin + d * length)
        if e > limit:
            length *= max(limit / e, 0.35)
        steps = 7 if level == 2 else 4
        pos = np.array(origin, float)
        pts, radii = [pos.copy()], [radius]
        # A steady curl to one side plus a kink at every step: elbows, not straight sticks.
        curl = math.radians(rng.uniform(-22.0, 22.0)) * gnarl
        for j in range(steps):
            u = (j + 1) / steps
            jitter = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.35, 0.6)])
            d = rot_z(d, curl) + jitter * 0.42 * gnarl
            if j % 2 == 1:
                curl = -curl * rng.uniform(0.5, 1.2)       # zigzag back
            d = d / np.linalg.norm(d)
            pos = pos + d * (length / steps)
            pts.append(pos.copy())
            radii.append(radius * (1.0 - u) ** 0.8 + 0.006)
        sk.branch(pts, radii, level)
        return pts, d, length

    def leafy_twigs(origin, direction, length, radius):
        """Level-3 twig carrying sprigs along its outer half and a tuft at the tip."""
        pts, d, length = side_branch(origin, direction, length, radius, 3, 1.0)
        outward = pts[-1] - centre
        for _ in range(3):
            add_sprig(pts[-1], outward, 0.8)
        for q in pts[1:-1]:
            add_sprig(q + d * rng.uniform(0.0, 0.3 * card), outward, 1.1)

    n_limbs = max(5, round(crown["limbs"] * density))
    base_az = rng.uniform(0, 6.28)
    # Elevations of the limb ends, spread from near-horizontal to the near-vertical leader.
    # Evenly spread over the egg's surface (equal steps in sin(elevation)), so no side is bare.
    elevations = [math.degrees(math.asin(lerp(crown["low"], 0.995, (k / (n_limbs - 1)) ** crown["bias"]))) for k in range(n_limbs)]
    for i in range(n_limbs):
        t = i / (n_limbs - 1)
        az = base_az + i * GOLDEN_ANGLE + rng.uniform(-0.3, 0.3)
        z0 = lerp(bole, fork_top, t ** 0.9)
        out = np.array([math.cos(az), math.sin(az), 0.0])
        side = np.array([-out[1], out[0], 0.0])
        base = axis(z0)
        elev = math.radians(elevations[i] + rng.uniform(-6.0, 6.0))
        target = envelope(out * math.cos(elev) + UP * math.sin(elev), rng.uniform(0.84, 0.92))
        span = float(np.linalg.norm(target - base))
        # Leave the trunk steeply, then arch over towards the target.
        start = math.radians(lerp(35.0, 80.0, t))
        ctrl = base + (out * math.cos(start) + UP * math.sin(start)) * span * 0.5
        wander = rng.uniform(-1, 1) * 0.1 * span * gnarl
        n = 14
        # Elbows: a random sideways and vertical offset per knot, smoothed so the limb
        # snakes between them, growing from nothing at the trunk.
        knots = 6
        kink_side = [0.0] + [rng.uniform(-1, 1) for _ in range(knots)]
        kink_up = [0.0] + [rng.uniform(-1, 1) for _ in range(knots)]

        def kink(values, s):
            f = s * knots
            k = min(int(f), knots - 1)
            u = f - k
            u = u * u * (3.0 - 2.0 * u)
            return lerp(values[k], values[k + 1], u)
        limb, limb_r = [], []
        base_r = trunk_r(z0) * lerp(0.6, 0.72, t)
        for j in range(n + 1):
            s = j / n
            pos = (1 - s) ** 2 * base + 2 * (1 - s) * s * ctrl + s ** 2 * target
            pos = pos + side * math.sin(s * 3.5 + ph1 + i) * wander * s
            pos[2] += math.sin(s * 7.0 + ph2 + i) * 0.012 * D * s * gnarl
            bend = 0.07 * span * gnarl * min(s * 3.0, 1.0)
            pos = pos + side * kink(kink_side, s) * bend + UP * kink(kink_up, s) * bend * 0.7
            pos[2] -= 0.03 * p["limb_droop"] * D * s * s * (1.0 - t)
            limb.append(pos)
            swell = 1.0 + 0.9 * p["flare"] * max(1.0 - s / 0.25, 0.0) ** 2
            limb_r.append(base_r * (0.9 * (1.0 - s) ** 0.8 + 0.1) * swell)
        sk.branch(limb, limb_r, 1)

        def limb_at(s):
            f = min(max(s, 0.0), 1.0) * n
            k = min(int(f), n - 1)
            tan = limb[k + 1] - limb[k]
            return (limb[k] + tan * (f - k), tan / max(np.linalg.norm(tan), 1e-6),
                    lerp(limb_r[k], limb_r[k + 1], f - k))

        tip, tip_dir, _ = limb_at(1.0)
        for k in range(3):
            leafy_twigs(tip, rot_z(tip_dir, (k - 1) * 0.9) + UP * 0.2, 0.16 * span, 0.016)

        # Secondary branches fork off round the limb along its outer two thirds.
        n_sec = max(4, round(8 * math.sqrt(density)))
        for k in range(n_sec):
            s = lerp(0.28, 0.93, (k + rng.uniform(0.2, 0.8)) / n_sec)
            origin, tangent, parent_r = limb_at(s)
            # Fan round the limb: sideways, upward, and a little downward.
            roll = k * GOLDEN_ANGLE + rng.uniform(-0.4, 0.4)
            ref = np.cross(tangent, UP)
            ref = ref / max(np.linalg.norm(ref), 1e-6)
            normal = math.cos(roll) * ref + (0.35 + 0.65 * abs(math.sin(roll))) * np.cross(ref, tangent)
            fork = math.radians(rng.uniform(40.0, 65.0))
            d = tangent * math.cos(fork) + normal * math.sin(fork)
            length = span * lerp(0.55, 0.3, s) * rng.uniform(0.85, 1.15)
            sec, sec_d, length = side_branch(origin, d, length, parent_r * 0.5 + 0.012, 2, 0.96)
            leafy_twigs(sec[-1], sec_d, length * 0.3, 0.014)
            for j in (2, 4, 5, 6):
                turn = (1.0 if (j + k) % 2 == 0 else -1.0) * math.radians(rng.uniform(40.0, 80.0))
                td = rot_z(sec_d, turn) + UP * rng.uniform(-0.15, 0.5)
                leafy_twigs(sec[j], td, length * rng.uniform(0.28, 0.45), 0.013)
    return sk


GROWERS = {
    "CEDAR": grow_cedar,
    "PINE": grow_pine,
    "OAK": lambda p, rng: grow_broadleaf(p, rng, CROWNS["OAK"]),
    "MAPLE": lambda p, rng: grow_broadleaf(p, rng, CROWNS["MAPLE"]),
}
GROWERS["MAPLE_AUTUMN"] = GROWERS["MAPLE_RED"] = GROWERS["MAPLE"]
GROWERS["BUSH"] = grow_bush


def build_mesh(name, species, params):
    """Grow a skeleton and return it as a mesh datablock with the attributes nodes.py expects."""
    sk = GROWERS[species](params, random.Random(params["seed"]))
    return sk.to_mesh(name, SPECIES[species].get("mix"), params["seed"], params["canopy"])
