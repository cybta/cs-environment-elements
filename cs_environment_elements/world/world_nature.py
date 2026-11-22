"""World nature: trees and rocks from the TreeGen add-on, and the hero Lebanese cedar.

Ordinary trees are never cedars (the cedar is the one hero tree). Each species gets a
few variations grown inside TreeGen's ordinary budget (LOD0 500-3000 triangles), baked
into LOD0-2 meshes plus TreeGen's LOD3 impostor (two crossed planes). Each variation
lives in its own library collection ("TreeLib_<name>") holding its four levels, and
every tree in the world is an instance of one of those collections, so the forest
costs one copy of each mesh. The LODs panel's Show switch picks the level drawn.

The hero cedar stays a live TreeGen tree (hero budget, 25-50k triangles) on the summit.
"""

import math

import bpy
import bmesh
import numpy as np
from mathutils import Vector, noise

from . import world_layout as wl
from . import world_materials as wm
from . import world_terrain as wt

VARIANTS = (("OAK", 3), ("MAPLE", 2), ("MAPLE_AUTUMN", 1), ("PINE", 4), ("BUSH", 2))
# Grown heights (m). The whole tree scales with it (crown, bare trunk, trunk radius and,
# through the crown, the foliage cards), so a small tree keeps its proportions.
HEIGHTS = {"OAK": (2.0, 3.0), "MAPLE": (2.0, 3.0), "MAPLE_AUTUMN": (2.0, 3.0), "PINE": (2.6, 4.0)}
SIZE_KEYS = ("height", "canopy", "bole", "trunk_radius")
LIB_PREFIX = "TreeLib_"


def treegen():
    """The Nature section (trees and rocks, formerly the TreeGen add-on), or None."""
    if not hasattr(bpy.types.Scene, "treegen"):     # nature section not registered
        return None
    from .. import nature
    return nature


# --------------------------------------------------------------------------
# Tree library
# --------------------------------------------------------------------------

def build_library(context, lib, rng, report=print):
    tg = treegen()
    if tg is None:
        report("TreeGen add-on not found: no trees")
        return {}
    from ..nature import core, species
    st = context.scene.treegen
    keep_species = st.species
    out = {}
    for sp, count in VARIANTS:
        st.species = sp                       # loads the species' default sizes
        base = {n: getattr(st, n) for n in core.COPIED_PROPS}
        for k in range(count):
            vals = dict(base, species=sp, hero=False, seed=rng.randint(1, 999999))
            vals["tri_min"], vals["tri_max"] = species.TREE_BUDGET
            if sp in HEIGHTS:
                f = rng.uniform(*HEIGHTS[sp]) / base["height"]
                for key in SIZE_KEYS:
                    vals[key] = base[key] * f
                vals["canopy"] *= rng.uniform(0.9, 1.1)
            name = f"{species.SPECIES[sp]['label'].replace(' ', '')}_{k + 1}"
            tree = core.create_tree(context, vals, (0.0, 0.0, 0.0))
            meshes = core.lod_meshes(tree, context, name)
            if core.has_impostor(tree):
                mesh, image = core._impostor(tree, context, meshes[0], name)
                image.pack()
                meshes.append(mesh)
            coll = bpy.data.collections.new(LIB_PREFIX + name)
            lib.children.link(coll)
            coll["tree_species"] = sp
            for lod, me in enumerate(meshes):
                ob = bpy.data.objects.new(me.name, me)
                coll.objects.link(ob)
                ob["tree_lod"] = lod
            data = tree.data
            for c in list(tree.users_collection):
                c.objects.unlink(tree)
            bpy.data.objects.remove(tree)
            if data.users == 0:
                bpy.data.meshes.remove(data)
            out.setdefault(sp, []).append(coll)
            show_lod(coll, 0)
    st.species = keep_species
    return out


def show_lod(coll, level):
    obs = sorted(coll.objects, key=lambda o: o.get("tree_lod", 0))
    level = min(level, len(obs) - 1)
    for ob in obs:
        hide = ob.get("tree_lod", 0) != level
        ob.hide_viewport = ob.hide_render = hide


def show_all(level):
    for coll in bpy.data.collections:
        if coll.name.startswith((LIB_PREFIX, "RockLib_")):
            show_lod(coll, level)


# --------------------------------------------------------------------------
# Scattering
# --------------------------------------------------------------------------

def _pick(rng, lib, h):
    if "PINE" in lib and rng.random() < np.clip((h - 8.0) / 55.0, 0.12, 0.85):
        return rng.choice(lib["PINE"])
    broad = [("OAK", 5), ("MAPLE", 4), ("MAPLE_AUTUMN", 1)]
    pool = [c for sp, w in broad for c in lib.get(sp, []) for _ in range(w)]
    return rng.choice(pool) if pool else None


def forest_points(L, T, rng, per_ha):
    """Jittered grid over the map, kept off the town, water, roads and cliffs."""
    cell = math.sqrt(10000.0 / max(per_ha, 0.1))
    n = int(2 * wl.HALF / cell)
    g = (np.arange(n) + 0.5) * cell - wl.HALF
    X, Y = np.meshgrid(g, g)
    X = X + np.array([[rng.uniform(-0.45, 0.45) * cell for _ in range(n)] for _ in range(n)])
    Y = Y + np.array([[rng.uniform(-0.45, 0.45) * cell for _ in range(n)] for _ in range(n)])
    pts = np.stack([X.ravel(), Y.ravel()], 1)
    pts = pts[wl.edge_r(pts[:, 0], pts[:, 1]) < wl.HALF - 10]
    h = T.sample_fine(pts)
    flat = T._bilinear(T.flat, pts, T.step, T.N)
    slope = T._bilinear(T.slope_grid, pts, T.step, T.N)
    lake_e = T._bilinear(T.lake_e, pts, T.step, T.N)
    river = T._bilinear(T.d_river, pts, T.step, T.N)
    clear = wt.fbm(pts[:, 0], pts[:, 1], 160.0, L.seed + 77, 3)          # clearings and groves
    rnd = np.array([rng.random() for _ in range(len(pts))])
    keep = ((h > wl.WATER_Z + 0.8) & (flat < 0.25) & (slope < 1.15) & (lake_e > 8.0) &
            (river > L.river_hw + 6.0) & (h < 135.0))
    dens = np.clip(0.55 + 1.2 * (clear - 0.3), 0.08, 1.0) * np.where(h > 100, 0.5, 1.0)
    keep &= rnd < dens
    sx, sy = L.summit
    keep &= np.hypot(pts[:, 0] - sx, pts[:, 1] - sy) > 26.0
    for r in L.roads:
        if r.kind in ("TRAIL", "PATH"):
            sel = np.nonzero(keep)[0]
            keep[sel] &= wl.seg_dist(pts[sel], r.loop_pts()) > r.hw + 2.5
    return pts[keep], h[keep]


def _instance(coll_src, name, coll, loc, rot, scale):
    ob = bpy.data.objects.new(name, None)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = coll_src
    ob.empty_display_size = 1.0
    coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (0.0, 0.0, rot)
    ob.scale = (scale, scale, scale)
    ob["tree_variant"] = coll_src.name[len(LIB_PREFIX):]
    return ob


def scatter(L, T, lib, forest_coll, town_coll, rng, per_ha, town_spots):
    if not lib:
        return 0
    n = 0
    pts, hs = forest_points(L, T, rng, per_ha)
    zs = T.sample(pts)
    for (x, y), h, z in zip(pts, hs, zs):
        src = _pick(rng, lib, h)
        if src is None:
            continue
        n += 1
        _instance(src, f"Tree_{n:05d}", forest_coll, (x, y, z - 0.05), rng.uniform(0, math.tau),
                  rng.uniform(0.9, 1.1))
    # Underbrush at the forest edges
    if "BUSH" in lib:
        bp, _ = forest_points(L, T, rng, per_ha * 0.35)
        bz = T.sample(bp)
        for (x, y), z in zip(bp, bz):
            n += 1
            _instance(rng.choice(lib["BUSH"]), f"Bush_{n:05d}", forest_coll, (x, y, z - 0.05),
                      rng.uniform(0, math.tau), rng.uniform(0.8, 1.4))
    # Gardens and parks: broadleaf trees, a bush or two at their feet
    for x, y, kind in town_spots:
        z = T.z(x, y)
        src = _pick(rng, {k: v for k, v in lib.items() if k != "PINE"} or lib, 0.0)
        if kind == "VILLA" and "PINE" in lib and rng.random() < 0.25:
            src = rng.choice(lib["PINE"])
        n += 1
        _instance(src, f"Tree_{n:05d}", town_coll, (x, y, z - 0.05), rng.uniform(0, math.tau), rng.uniform(0.9, 1.1))
        if "BUSH" in lib and rng.random() < 0.5:
            a = rng.uniform(0, math.tau)
            bx, by = x + 1.4 * math.cos(a), y + 1.4 * math.sin(a)
            n += 1
            _instance(rng.choice(lib["BUSH"]), f"Bush_{n:05d}", town_coll, (bx, by, T.z(bx, by) - 0.05),
                      rng.uniform(0, math.tau), rng.uniform(0.9, 1.3))
    return n


# --------------------------------------------------------------------------
# Rocks
# --------------------------------------------------------------------------

def _rock_mesh(name, seed, mat):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    off = Vector((seed * 7.31, seed * 3.17, seed * 1.93))
    for v in bm.verts:
        d = noise.noise(v.co * 1.3 + off) * 0.35 + noise.noise(v.co * 3.1 + off) * 0.12
        v.co *= 1.0 + d
        if v.co.z < -0.2:                   # flat-ish bottom, it sits in the ground
            v.co.z = -0.2 + (v.co.z + 0.2) * 0.3
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    from ..core.materials import _uv_metric
    from ..core import neighborhood_materials as nm
    _uv_metric(me, nm.uv_scale)
    return me


ROCK_PREFIX = "RockLib_"
ROCK_MIX = ("BOULDER", "BOULDER", "BOULDER", "BOULDER", "JAGGED", "JAGGED", "SLAB", "SLAB")


def rock_library(lib_coll, rng):
    """TreeGen's rocks (boulders, jagged shards, slabs) with LOD 0-2, one collection
    each like the trees; [] without TreeGen (or an older TreeGen without rocks)."""
    if treegen() is None:
        return []
    try:
        from ..nature import rocks as tr
    except ImportError:
        return []
    out = []
    for k, typ in enumerate(ROCK_MIX):
        p = {key: tr.TYPES[typ].get(key) for key in ("size", "elongation", "flatness", "roughness", "facets", "strata", "surface")}
        p.update(rock_type=typ, moss=rng.uniform(0.25, 0.5), seed=rng.randint(1, 999999), detail=4)
        name = f"{tr.TYPES[typ]['label']}_{k + 1}"
        coll = bpy.data.collections.new(ROCK_PREFIX + name)
        lib_coll.children.link(coll)
        for lod in range(tr.LOD_COUNT):
            ob = bpy.data.objects.new(f"{name}_LOD{lod}", tr.build_mesh(f"{name}_LOD{lod}", p, lod))
            coll.objects.link(ob)
            ob["tree_lod"] = lod
        show_lod(coll, 0)
        out.append(coll)
    return out


def rocks(L, T, coll, lib_coll, rng, count=320):
    """Rocks on the mountain sides and rim, and a few on the gentler ground."""
    lib = rock_library(lib_coll, rng)
    shapes = []
    if not lib:                               # no TreeGen: simple stand-in rocks
        mat = wm.ensure("C_world_rock")
        for k in range(6):
            src = bpy.data.objects.new(f"RockSrc_{k + 1}", _rock_mesh(f"RockSrc_{k + 1}", k + rng.random(), mat))
            lib_coll.objects.link(src)
            shapes.append(src)
    placed, tries = 0, 0
    slope = T.slope_grid
    while placed < count and tries < count * 40:
        tries += 1
        x, y = rng.uniform(-wl.HALF + 20, wl.HALF - 20), rng.uniform(-wl.HALF + 20, wl.HALF - 20)
        p = np.array([[x, y]])
        if T._bilinear(T.flat, p, T.step, T.N)[0] > 0.05:
            continue
        h = float(T.sample_fine(p)[0])
        s = float(T._bilinear(slope, p, T.step, T.N)[0])
        mh = float(L.mountain_h(np.array([x]), np.array([y]))[0])
        if h < wl.WATER_Z + 0.5 or (s < 0.45 and mh < 25 and rng.random() < 0.9):
            continue
        if math.hypot(x - L.summit[0], y - L.summit[1]) < 16:
            continue
        placed += 1
        rot = (rng.uniform(-0.15, 0.15), rng.uniform(-0.15, 0.15), rng.uniform(0, math.tau))
        if lib:
            src = rng.choice(lib)
            size = rng.uniform(0.6, 1.8) * (1.5 if s > 0.7 else 1.0)
            ob = bpy.data.objects.new(f"Rock_{placed:04d}", None)
            ob.instance_type = "COLLECTION"
            ob.instance_collection = src
            ob["rock_variant"] = src.name[len(ROCK_PREFIX):]
            coll.objects.link(ob)
            ob.location = (x, y, T.z(x, y) - 0.12 * size)
            ob.rotation_euler = rot
            ob.scale = (size, size, size * rng.uniform(0.85, 1.15))
        else:
            src = rng.choice(shapes)
            size = rng.uniform(0.6, 2.2) * (1.6 if s > 0.7 else 1.0)
            ob = src.copy()
            ob.name = f"Rock_{placed:04d}"
            coll.objects.link(ob)
            ob.location = (x, y, T.z(x, y) - 0.25 * size)
            ob.rotation_euler = rot
            ob.scale = (size * rng.uniform(1.0, 1.8), size * rng.uniform(0.8, 1.4), size * rng.uniform(0.6, 1.1))
    for src in shapes:
        src.hide_viewport = src.hide_render = True
    return placed


# --------------------------------------------------------------------------
# The hero cedar
# --------------------------------------------------------------------------

def hero_cedar(context, L, T, coll, seed):
    tg = treegen()
    if tg is None:
        return None
    from ..nature import core, species
    st = context.scene.treegen
    keep = st.species
    st.species = "CEDAR"
    vals = {n: getattr(st, n) for n in core.COPIED_PROPS}
    vals.update(species.start_values("CEDAR", hero=True), species="CEDAR", hero=True, seed=seed)
    vals["tri_min"], vals["tri_max"] = species.HERO_BUDGET
    x, y = L.summit
    tree = core.create_tree(context, vals, (x, y, T.z(x, y) - 0.3))
    st.species = keep
    tree.name = "Hero_Lebanese_Cedar"
    for c in list(tree.users_collection):
        c.objects.unlink(tree)
    coll.objects.link(tree)
    tree["world_part"] = "hero_tree"
    return tree
