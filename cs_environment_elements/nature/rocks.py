"""Rocks: random boulders, jagged shards and layered slabs as game assets.

Every LOD starts from an icosphere and is pushed out by the same shape function of the
direction from the centre, so the levels share one silhouette and only lose detail:

    lumps      two octaves of noise on the radius (Roughness)
    facets     random cutting planes the surface is flattened against (Facets), which
               reads as fractured stone
    strata     the height stepped into layers (Strata), for sedimentary slabs
    base       the underside pressed flat, so the rock sits on the ground; the origin is
               at the middle of that base

LOD 0 / 1 / 2 are icospheres with Detail, Detail-1, Detail-2 subdivisions (Detail 4 =
1280 / 320 / 80 triangles). UVs are a box projection where one UV unit is one repeat of
the rock's Surface texture, and a "Moss" colour attribute (also written to FBX as vertex
colour) blends the mossy-grass texture onto the upward faces.

Textures (Poly Haven, CC0) in textures/rocks/: marble_cliff_05 (Cliff surface),
aerial_rocks_02 (Outcrop surface), aerial_grass_rock (moss).
"""

import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise

from ..core import naming
from . import assets

LOD_COUNT = 3
ROCK_DIR = os.path.join(assets.TEXTURE_DIR, "rocks")
# Surface texture sets: folder, file prefix, metres per repeat
SURFACES = {
    "CLIFF": dict(label="Cliff", description="Clean grey cliff stone with fine fractures",
                  folder="marble_cliff_05_1k", prefix="marble_cliff_05", tile=2.5),
    "OUTCROP": dict(label="Outcrop", description="Weathered stones with moss and grass in the cracks",
                    folder="aerial_rocks_02_1k", prefix="aerial_rocks_02", tile=3.0),
}
MOSS = dict(folder="aerial_grass_rock_1k", prefix="aerial_grass_rock", tile=1.5)

# Starting values per rock type, applied when the type is picked in the panel.
TYPES = {
    "BOULDER": dict(label="Boulder", description="Rounded, weathered lump with a few broken faces",
                    size=1.6, elongation=1.25, flatness=0.75, roughness=0.22, facets=4, strata=0.0, surface="OUTCROP"),
    "JAGGED": dict(label="Jagged", description="Sharp, fractured shard: many flat broken faces, taller than wide",
                   size=1.1, elongation=1.3, flatness=1.7, roughness=0.16, facets=12, strata=0.0, surface="CLIFF"),
    "SLAB": dict(label="Slab", description="Flat, layered sedimentary rock with stepped strata",
                 size=2.2, elongation=1.6, flatness=0.42, roughness=0.1, facets=5, strata=0.6, surface="CLIFF"),
}
STRUCTURE_PROPS = ("rock_type", "size", "elongation", "flatness", "roughness", "facets", "strata",
                   "surface", "moss", "seed", "detail")


# ----------------------------------------------------------------------------
# Shape
# ----------------------------------------------------------------------------
class Shape:
    """The rock's shape function, fixed by its parameters and seed."""

    def __init__(self, p):
        rng = random.Random(p["seed"])
        self.p = p
        self.off = Vector((rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(-500, 500)))
        self.off2 = Vector((rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(-500, 500)))
        self.cuts = []
        for _ in range(p["facets"]):
            # cutting planes: mostly round the sides and the top, rarely from below
            z = rng.uniform(-0.25, 1.0)
            a = rng.uniform(0, 2 * math.pi)
            r = math.sqrt(max(0.0, 1 - z * z))
            deep = (0.42, 0.78) if p["facets"] > 8 else (0.62, 0.9)       # many facets cut deeper: sharp
            self.cuts.append((Vector((r * math.cos(a), r * math.sin(a), z)), rng.uniform(*deep)))
        self.half = Vector((p["size"] * p["elongation"] / 2, p["size"] / 2, p["size"] * p["flatness"] / 2))
        self.tilt = rng.uniform(-0.12, 0.12)

    def point(self, d):
        p = self.p
        r = 1.0 + p["roughness"] * (noise.noise(d * 1.3 + self.off) * 0.8 + noise.noise(d * 3.4 + self.off2) * 0.35)
        q = d * r
        for n, dist in self.cuts:
            h = q.dot(n)
            if h > dist:
                q = q - n * (h - dist)
        q = Vector((q.x * self.half.x, q.y * self.half.y, q.z * self.half.z))
        if p["strata"] > 0.0:
            step = max(0.08, self.half.z * 0.35)
            z = q.z + q.x * self.tilt
            k = math.floor(z / step)
            f = z / step - k
            f = f ** (1.0 + 5.0 * p["strata"])               # sharp riser, flat tread
            q.z = (k + f) * step - q.x * self.tilt
        base = -self.half.z * 0.45
        if q.z < base:
            q.z = base + (q.z - base) * 0.12
        q.z -= base
        return q


def _icosphere(subdivisions):
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=max(1, subdivisions), radius=1.0)
    return bm


def build_mesh(name, params, lod=0):
    """A mesh of the rock at one LOD, with UVs, sharp edges and the Moss attribute."""
    shape = Shape(params)
    bm = _icosphere(params["detail"] - lod)
    for v in bm.verts:
        v.co = shape.point(v.co.normalized())
    bm.normal_update()
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    _uv_box(me, SURFACES[params["surface"]]["tile"])
    _moss(me, shape, params)
    me.shade_smooth()
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(38.0))
    me.materials.append(material(params["surface"]))
    return me


def _uv_box(me, tile):
    """Box projection, one UV unit per `tile` metres: each face takes the plane its
    normal faces most."""
    uv = me.uv_layers.new(name="UVMap")
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    for poly in me.polygons:
        n = poly.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        a, b = [(1, 2), (0, 2), (0, 1)][ax]
        for li in poly.loop_indices:
            c = co[me.loops[li].vertex_index]
            uv.data[li].uv = (c[a] / tile, c[b] / tile)


def _moss(me, shape, params):
    """Moss weight per vertex: upward-facing and sheltered, broken up by noise."""
    attr = me.color_attributes.new("Moss", "FLOAT_COLOR", "POINT")
    amount = params["moss"]
    for v in me.vertices:
        up = max(0.0, v.normal.z)
        n = noise.noise(v.co * 1.7 + shape.off2) * 0.5 + 0.5
        w = min(1.0, max(0.0, (up - (1.0 - amount)) * 2.5 + (n - 0.5) * 0.8)) if amount > 0 else 0.0
        attr.data[v.index].color = (w, w, w, 1.0)


def triangles(mesh):
    return sum(len(p.vertices) - 2 for p in mesh.polygons)


# ----------------------------------------------------------------------------
# Material
# ----------------------------------------------------------------------------
def _set_images(spec):
    """(diffuse, normal, roughness) of one texture set, or None if its files are missing."""
    folder = os.path.join(ROCK_DIR, spec["folder"])
    out = []
    for kind, colour in (("diff", True), ("nor_gl", False), ("rough", False)):
        path = None
        for ext in ("jpg", "exr", "png"):
            candidate = os.path.join(folder, "%s_%s_1k.%s" % (spec["prefix"], kind, ext))
            if os.path.exists(candidate):
                path = candidate
                break
        if path is None:
            return None
        out.append(assets._load(path, colour))
    return out


def rock_images(surface="CLIFF"):
    """Every image the surface's material uses (for export)."""
    return (_set_images(SURFACES[surface]) or []) + (_set_images(MOSS) or [])


def material(surface="CLIFF"):
    """The surface texture on the UVs; the mossy-grass texture blended in by the Moss
    attribute (colour, roughness and normal), so the moss also reads in the game."""
    spec = SURFACES[surface]
    name = "TreeGen_Rock_%s" % spec["label"]
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (0.42, 0.4, 0.37, 1.0)
    nt = mat.node_tree
    N, link = nt.nodes, nt.links.new
    bsdf = N["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    uv = N.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    uv.location = (-1300, 0)
    scale = N.new("ShaderNodeMapping")                     # moss repeats at its own size
    scale.location = (-1100, -500)
    k = spec["tile"] / MOSS["tile"]
    scale.inputs["Scale"].default_value = (k, k, 1.0)
    link(uv.outputs["UV"], scale.inputs["Vector"])

    def textures(images, vec, x, y):
        nodes = []
        for j, img in enumerate(images):
            node = N.new("ShaderNodeTexImage")
            node.image = img
            node.location = (x, y - j * 280)
            link(vec, node.inputs["Vector"])
            nodes.append(node.outputs["Color"])
        return nodes

    rock = _set_images(spec)
    moss = _set_images(MOSS)
    attr = N.new("ShaderNodeVertexColor")
    attr.layer_name = "Moss"
    attr.location = (-800, 600)

    def mix(a, b, y, default_b):
        m = N.new("ShaderNodeMix")
        m.data_type = "RGBA"
        m.location = (-450, y)
        ins = {sk.identifier: sk for sk in m.inputs}
        link(attr.outputs["Color"], ins["Factor_Float"])
        if a is not None:
            link(a, ins["A_Color"])
        if b is not None:
            link(b, ins["B_Color"])
        else:
            ins["B_Color"].default_value = default_b
        return next(sk for sk in m.outputs if sk.identifier == "Result_Color")

    r = textures(rock, uv.outputs["UV"], -900, 300) if rock else [None, None, None]
    g = textures(moss, scale.outputs["Vector"], -900, -600) if moss else [None, None, None]
    link(mix(r[0], g[0], 400, (0.16, 0.24, 0.07, 1.0)), bsdf.inputs["Base Color"])
    if r[2] is not None:
        link(mix(r[2], g[2], 0, (0.9, 0.9, 0.9, 1.0)), bsdf.inputs["Roughness"])
    if r[1] is not None:
        nmap = N.new("ShaderNodeNormalMap")
        nmap.location = (-200, -300)
        link(mix(r[1], g[1], -300, (0.5, 0.5, 1.0, 1.0)), nmap.inputs["Color"])
        link(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


# ----------------------------------------------------------------------------
# Objects
# ----------------------------------------------------------------------------
def is_rock(obj):
    return obj is not None and obj.type == "MESH" and obj.treegen_rock.is_rock


def params_of(settings):
    return {k: getattr(settings, k) for k in STRUCTURE_PROPS}


def regrow(obj):
    """Rebuild the rock's mesh at its preview LOD from its settings."""
    s = obj.treegen_rock
    naming.rename_if_auto(obj, name_prefix(s.rock_type))   # type changed: rock-boulder-1 -> rock-slab-n
    p = params_of(s)
    old = obj.data
    obj.data = build_mesh(obj.name, p, int(s.preview_lod))
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    counts = []
    for lod in range(LOD_COUNT):
        me = build_mesh("_count", p, lod)
        counts.append(triangles(me))
        bpy.data.meshes.remove(me)
    s.tri_lod0, s.tri_lod1, s.tri_lod2 = counts


def name_prefix(rock_type):
    """'BOULDER' -> 'rock-boulder'."""
    return naming.slug("rock", rock_type)


def create_rock(context, values, location):
    name = naming.next_name(name_prefix(values["rock_type"]))
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    context.collection.objects.link(obj)
    obj.location = location
    s = obj.treegen_rock
    s.lock = True
    for k, v in values.items():
        setattr(s, k, v)
    s.is_rock = True
    s.lock = False
    regrow(obj)
    return obj


def lod_meshes(obj, base_name):
    p = params_of(obj.treegen_rock)
    return [build_mesh("%s_LOD%d" % (base_name, lod), p, lod) for lod in range(LOD_COUNT)]


def bake_lods(obj, context):
    coll = bpy.data.collections.new(obj.name + "_LODs")
    context.scene.collection.children.link(coll)
    out = []
    for lod, me in enumerate(lod_meshes(obj, naming.safe(obj.name))):
        new = bpy.data.objects.new(me.name, me)
        coll.objects.link(new)
        new.matrix_world = obj.matrix_world.copy()
        new.location.y += (lod + 1) * obj.treegen_rock.size * obj.treegen_rock.elongation * 1.3
        out.append(new)
    return out


def export_rocks(context, rocks, folder, per_lod_files):
    """Each rock's LOD 0-2 as FBX (centred at the origin) and the rock textures."""
    from .core import _write_fbx
    os.makedirs(folder, exist_ok=True)
    written = []
    images = []
    for obj in rocks:
        images += [i for i in rock_images(obj.treegen_rock.surface) if i not in images]
    for img in images:
        path = os.path.join(folder, os.path.basename(img.filepath))
        img.save(filepath=path)
        written.append(path)
    selected, active = list(context.selected_objects), context.view_layer.objects.active
    coll = bpy.data.collections.new("TreeGen_RockExport")
    context.scene.collection.children.link(coll)
    try:
        for obj in rocks:
            name = naming.safe(obj.name)
            objects = []
            for me in lod_meshes(obj, name):
                new = bpy.data.objects.new(me.name, me)
                coll.objects.link(new)
                objects.append(new)
            if per_lod_files:
                for new in objects:
                    path = os.path.join(folder, new.name + ".fbx")
                    _write_fbx(context, [new], path)
                    written.append(path)
            else:
                path = os.path.join(folder, name + ".fbx")
                _write_fbx(context, objects, path)
                written.append(path)
    finally:
        for new in list(coll.objects):
            me = new.data
            bpy.data.objects.remove(new)
            bpy.data.meshes.remove(me)
        bpy.data.collections.remove(coll)
        for obj in context.view_layer.objects:
            obj.select_set(obj in selected)
        context.view_layer.objects.active = active
    return written
