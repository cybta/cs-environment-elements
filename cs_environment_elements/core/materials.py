"""Shared materials: bundled PBR texture sets, flat colours, metric UVs.

Textures live in core/assets so they travel with the add-on when it is installed
from a .zip. Each sub-folder of assets/ is one selectable material set; files are
matched to Principled roles by their "-<role>" suffix. (assets/neighborhood is the
scene look, see neighborhood_materials.)
"""

import os

import bpy

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

# Suffix on a file's name (before the extension) -> the role it feeds.
_ROLE_SUFFIXES = (
    ("color", "-color"),
    ("normal", "-normal"),
    ("bump", "-bump"),
    ("specular", "-specular"),
    ("roughness", "-roughness"),
    ("ao", "-ambient-occlusion"),
)
_NOT_SETS = {"neighborhood", "old-fence"}


def _discover_material_sets():
    """Scan assets/ once: {folder_name: {role: absolute_path}} for every set."""
    sets = {}
    if not os.path.isdir(ASSET_DIR):
        return sets
    for entry in sorted(os.listdir(ASSET_DIR)):
        folder = os.path.join(ASSET_DIR, entry)
        if entry in _NOT_SETS or not os.path.isdir(folder):
            continue
        maps = {}
        for fn in os.listdir(folder):
            stem = os.path.splitext(fn)[0].lower()
            for role, suffix in _ROLE_SUFFIXES:
                if stem.endswith(suffix):
                    maps[role] = os.path.join(folder, fn)
                    break
        if "color" in maps:  # a set is only usable if it has a colour map
            sets[entry] = maps
    return sets


# Built at import time so the enums that use them can have static items (and defaults).
MATERIAL_SETS = _discover_material_sets()


def _pretty(name):
    return name.replace("-", " ").replace("_", " ").title()


MATERIAL_ENUM_ITEMS = [(k, _pretty(k), f"{len(v)} maps") for k, v in MATERIAL_SETS.items()]
if not MATERIAL_ENUM_ITEMS:  # no assets shipped — keep the enum valid
    MATERIAL_ENUM_ITEMS = [("NONE", "(no textures found)", "")]


def _default_set(preferred):
    """Pick `preferred` if it exists, else fall back to whatever is available."""
    if preferred in MATERIAL_SETS:
        return preferred
    return MATERIAL_ENUM_ITEMS[0][0]


def _load_image(path, non_color=False):
    """Load an image by absolute path, or return None if it isn't on disk."""
    if not path or not os.path.exists(path):
        return None
    img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


def _uv_metric(me, scale_for=None, z0=0.0, z0_for=None):
    """UVs in metres (1 UV unit = 1 m), projected onto each face's own plane.

    Matches the neighborhood scene, whose materials scale UVs to life size.
    U runs horizontally along the face and V up it (up the slope on roofs), so
    textures line up across neighbouring wall pieces. `scale_for(material)`
    can give a per-material multiplier (e.g. tiles that are 0.6 m per repeat).
    `z0` is the height V is measured from, so wall tiles start at each storey's floor;
    `z0_for(material)` (if given) says which materials that applies to: the others keep V = height,
    so facade cladding runs on unbroken from one storey to the next.
    """
    from mathutils import Vector

    uv = me.uv_layers.new(name="UVMap")
    up = Vector((0.0, 0.0, 1.0))
    for poly in me.polygons:
        n = poly.normal
        if abs(n.z) > 0.999:
            t, b = Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0))
        else:
            t = up.cross(n).normalized()
            b = n.cross(t)
        k, zz = 1.0, z0
        mat = me.materials[poly.material_index] if poly.material_index < len(me.materials) else None
        if scale_for and mat is not None:
            k = scale_for(mat)
        if z0_for is not None and not z0_for(mat):
            zz = 0.0
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (v.dot(t) * k, (v.dot(b) - zz * b.z) * k)


def _material(name, color, glass=False):
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 0.3 if glass else 1.0)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if glass:
            for key in ("Transmission Weight", "Transmission"):  # 4.x / 3.x
                if key in bsdf.inputs:
                    bsdf.inputs[key].default_value = 1.0
                    break
            bsdf.inputs["Roughness"].default_value = 0.0
    return mat


def _build_pbr_material(mat_name, maps, tile_size_m):
    """Build a PBR material from a discovered map set ({role: path}).

    `tile_size_m` is the real-world size (metres) of one texture repeat, so the
    pattern stays life-sized on any surface. Box projection from object
    coordinates needs no UVs and tiles cleanly across the boolean-cut walls.
    Whatever maps a set is missing (normal, roughness, AO...) are simply skipped.
    """
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-900, 0)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-700, 0)
    # Scale maps object-space metres -> texture repeats. 1/tile_size repeats/m.
    f = 1.0 / max(tile_size_m, 1e-4)
    mapping.inputs["Scale"].default_value = (f, f, f)
    nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])

    def _tex(role, non_color, y):
        img = _load_image(maps.get(role), non_color)
        if img is None:
            return None
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        node.projection = "BOX"       # triplanar-ish; no UVs needed
        node.projection_blend = 0.2
        node.location = (-400, y)
        nt.links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        return node

    color = _tex("color", False, 400)
    ao = _tex("ao", True, 100)
    spec = _tex("specular", True, -200)
    rough = _tex("roughness", True, -500)
    normal = _tex("normal", True, -800)
    bump = _tex("bump", True, -1100)

    # Base colour = colour (x ambient occlusion, if the set has one)
    if color and ao:
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 1.0
        mix.location = (0, 300)
        nt.links.new(color.outputs["Color"], mix.inputs["Color1"])
        nt.links.new(ao.outputs["Color"], mix.inputs["Color2"])
        nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    elif color:
        nt.links.new(color.outputs["Color"], bsdf.inputs["Base Color"])

    if spec:
        spec_in = "Specular IOR Level" if "Specular IOR Level" in bsdf.inputs else "Specular"
        if spec_in in bsdf.inputs:
            nt.links.new(spec.outputs["Color"], bsdf.inputs[spec_in])

    if rough:
        nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])

    # Surface detail: normal map and/or bump, chained into the BSDF Normal.
    normal_out = None
    if normal:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (0, -800)
        nt.links.new(normal.outputs["Color"], nmap.inputs["Color"])
        normal_out = nmap.outputs["Normal"]
    if bump:
        bnode = nt.nodes.new("ShaderNodeBump")
        bnode.location = (0, -1100)
        bnode.inputs["Strength"].default_value = 0.3
        nt.links.new(bump.outputs["Color"], bnode.inputs["Height"])
        if normal_out:  # feed the normal map through the bump node
            nt.links.new(normal_out, bnode.inputs["Normal"])
        normal_out = bnode.outputs["Normal"]
    if normal_out:
        nt.links.new(normal_out, bsdf.inputs["Normal"])

    return mat


def _material_for(set_key, tile_size_m, fallback_color, slot=""):
    """Resolve a chosen set to a material, falling back to flat colour.

    `slot` (e.g. "Wall") keeps each element's material distinct, so the same
    texture set can tile at a different size on walls, floor and ceiling.
    """
    suffix = f"_{slot}" if slot else ""
    maps = MATERIAL_SETS.get(set_key)
    if not maps:
        return _material(f"RoomGen_{set_key}{suffix}", fallback_color)
    return _build_pbr_material(f"RoomGen_{set_key}{suffix}", maps, tile_size_m)
