"""Foliage card meshes, textures and materials. Everything is created on demand."""

import math
import os

import bpy
import numpy as np

TEXTURE_DIR = os.path.join(os.path.dirname(__file__), "textures")

# Where the stem base sits in the cedar texture (UV space).
CEDAR_STEM_U, CEDAR_STEM_V = 0.455, 0.02
CEDAR_ASPECT = 1.5      # texture width / height

# Sprig photos (stem at the bottom centre): file, stem U, width / height, side droop, tip droop,
# and per LOD the card outline rows (v, u_min, u_max) that hug the foliage in the photo.
SPRIGS = {
    "OAK": dict(
        file="oak.png", stem_u=0.455, aspect=1312 / 1199, side=0.12, tip=0.10,
        rows=([(0.0, 0.4, 0.5), (0.3, 0.06, 0.78), (0.6, 0.04, 0.98), (1.0, 0.3, 0.7)],
              [(0.0, 0.3, 0.6), (0.5, 0.04, 0.98), (1.0, 0.25, 0.75)],
              [(0.0, 0.04, 0.98), (1.0, 0.04, 0.98)])),
    "MAPLE": dict(
        file="maple.png", stem_u=0.46, aspect=1312 / 1199, side=0.12, tip=0.10,
        rows=([(0.0, 0.4, 0.52), (0.3, 0.14, 0.84), (0.58, 0.02, 0.98), (1.0, 0.3, 0.8)],
              [(0.0, 0.3, 0.62), (0.5, 0.02, 0.98), (1.0, 0.25, 0.85)],
              [(0.0, 0.02, 0.98), (1.0, 0.02, 0.98)])),
    "PINE": dict(
        file="pine.png", stem_u=0.45, aspect=1313 / 1198, side=0.22, tip=0.16,
        rows=([(0.0, 0.3, 0.6), (0.5, 0.02, 0.98), (1.0, 0.3, 0.75)],
              [(0.0, 0.3, 0.6), (0.5, 0.02, 0.98), (1.0, 0.3, 0.75)],
              [(0.0, 0.02, 0.98), (1.0, 0.02, 0.98)])),
}
# Maple colour variants share one atlas: "cells" sprigs side by side (green, pale, red).
# A tree mixes them by giving each foliage anchor a cell (see Skeleton.leaf_variants).
SPRIGS["MAPLE_AUTUMN"] = SPRIGS["MAPLE_RED"] = dict(SPRIGS["MAPLE"], file="maple-mix.png", cells=3)
# Bush texture: a leaf (cell 0) and a flower (cell 1). The flower gets a fan card, see _bush_card.
SPRIGS["BUSH"] = dict(
    file="bush.png", stem_u=0.5, aspect=1.0, side=0.10, tip=0.2, cells=2,
    rows=([(0.0, 0.36, 0.64), (0.45, 0.12, 0.88), (1.0, 0.3, 0.7)],
          [(0.0, 0.12, 0.88), (1.0, 0.12, 0.88)],
          [(0.0, 0.12, 0.88), (1.0, 0.12, 0.88)]))
FLOWER_SIDES = (8, 6, 4)    # per LOD
CARD_VERSION = 3        # bump when a card's shape changes: cards saved in older .blend files are rebuilt


# ----------------------------------------------------------------------------
# Card meshes
# ----------------------------------------------------------------------------
def _card_mesh(name, rows):
    """rows: list of rows, each a list of (position, uv). Faces are triangles."""
    verts, uvs, faces = [], [], []
    for row in rows:
        for position, uv in row:
            verts.append(position)
            uvs.append(uv)
    width = len(rows[0])
    for r in range(len(rows) - 1):
        for c in range(width - 1):
            a, b = r * width + c, r * width + c + 1
            d, e = (r + 1) * width + c, (r + 1) * width + c + 1
            faces += [(a, b, e), (a, e, d)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    loop_verts = np.zeros(len(mesh.loops), np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    layer = mesh.uv_layers.new(name="UVMap")
    layer.data.foreach_set("uv", np.array(uvs, np.float32)[loop_verts].ravel())
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()
    return mesh


def _cedar_card(name, lod, cell=0):
    """A flat spray lying in XY, stem at the origin, growing along +Y, slightly domed.
    The outline follows the foliage in the texture to limit overdraw."""
    # (v, u_min, u_max) per row, and vertices per row
    if lod == 0:
        spans, columns = [(0.0, 0.38, 0.54), (0.33, 0.05, 0.98), (0.66, 0.0, 1.0), (1.0, 0.2, 0.96)], 4
    elif lod == 1:
        spans, columns = [(0.0, 0.3, 0.62), (0.45, 0.0, 1.0), (1.0, 0.12, 0.97)], 3
    else:
        spans, columns = [(0.0, 0.0, 1.0), (1.0, 0.0, 1.0)], 3
    rows = []
    for v, u0, u1 in spans:
        row = []
        for c in range(columns):
            u = u0 + (u1 - u0) * c / (columns - 1)
            x = (u - CEDAR_STEM_U) * CEDAR_ASPECT
            y = v - CEDAR_STEM_V
            z = -0.10 * ((u - CEDAR_STEM_U) / 0.5) ** 2 - 0.07 * v * v
            row.append(((x, y, z), (u, v)))
        rows.append(row)
    return _card_mesh(name, rows)


def _sprig_card(species):
    spec = SPRIGS[species]

    def build(name, lod, cell=0):
        """Stem at the origin, growing along +Y, drooping towards the sides and the tip.
        `cell` picks the sprig in the texture when it is an atlas of several side by side."""
        cells = spec.get("cells", 1)
        rows = []
        for v, u0, u1 in spec["rows"][lod]:
            row = []
            for c in range(3):
                u = u0 + (u1 - u0) * c / 2
                x = (u - spec["stem_u"]) * spec["aspect"]
                z = -spec["side"] * ((u - spec["stem_u"]) / 0.5) ** 2 - spec["tip"] * v * v
                row.append(((x, v, z), ((u + cell) / cells, v)))
            rows.append(row)
        return _card_mesh(name, rows)
    return build


def _fan_card(name, sides, cell, cells):
    """A flat disc of `sides` triangles round the origin, facing +Z, showing one whole atlas cell."""
    radius = 0.5 / math.cos(math.pi / sides)        # the polygon encloses the cell's inscribed circle
    verts, uvs = [(0.0, 0.0, 0.0)], [((0.5 + cell) / cells, 0.5)]
    for k in range(sides):
        angle = (2 * k + 1) * math.pi / sides
        x, y = math.cos(angle) * radius, math.sin(angle) * radius
        verts.append((x, y, 0.06))                  # slightly cupped, so it catches the light
        uvs.append(((0.5 + x + cell) / cells, 0.5 + y))
    faces = [(0, 1 + k, 1 + (k + 1) % sides) for k in range(sides)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    loop_verts = np.zeros(len(mesh.loops), np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", np.array(uvs, np.float32)[loop_verts].ravel())
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    mesh.update()
    return mesh


def _bush_card(name, lod, cell=0):
    if cell == 1:
        return _fan_card(name, FLOWER_SIDES[lod], cell, SPRIGS["BUSH"]["cells"])
    return _sprig_card("BUSH")(name, lod, cell)


_CARD_BUILDERS = dict({"CEDAR": _cedar_card}, **{key: _sprig_card(key) for key in SPRIGS})
_CARD_BUILDERS["BUSH"] = _bush_card


def card_variants(species):
    """How many different foliage cards the species mixes (cells of its leaf atlas)."""
    return SPRIGS.get(species, {}).get("cells", 1)


def card_collections(species):
    """One collection per LOD holding the species' foliage cards, one object per atlas cell
    (named ..._V0, _V1, in cell order). They are not linked to any scene."""
    material = leaf_material(species)
    collections = []
    for lod in range(3):
        stem = "TreeGen_Card_%s_LOD%d" % (species.title(), lod)
        name = stem.replace("_Card_", "_Cards_")
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = bpy.data.collections.new(name)
            collection.use_fake_user = True
        if collection.get("treegen_card") != CARD_VERSION or not collection.objects:
            for obj in list(collection.objects):
                old = obj.data
                bpy.data.objects.remove(obj)
                if old.users == 0:
                    bpy.data.meshes.remove(old)
            for cell in range(card_variants(species)):
                card = "%s_V%d" % (stem, cell)
                mesh = _CARD_BUILDERS[species](card, lod, cell)
                mesh.materials.append(material)
                collection.objects.link(bpy.data.objects.new(card, mesh))
            collection["treegen_card"] = CARD_VERSION
            legacy = bpy.data.objects.get(stem)        # the single card object of older versions
            if legacy is not None and legacy.get("treegen_card") is not None:
                legacy.use_fake_user = False
        collections.append(collection)
    return collections


# ----------------------------------------------------------------------------
# Textures
# ----------------------------------------------------------------------------
def _photo_image(filename):
    image = bpy.data.images.load(os.path.join(TEXTURE_DIR, filename), check_existing=True)
    if image.packed_file is None:
        image.pack()                             # keep saved .blend files self-contained
    return image


def _load(path, colour):
    image = bpy.data.images.load(path, check_existing=True)
    image.colorspace_settings.name = "sRGB" if colour else "Non-Color"
    if image.packed_file is None:
        image.pack()
    return image


# Photo-scanned bark sets: folder, file prefix and a tint multiplied over the colour photo.
# Oak borrows the cedar photos with its own tint.
BARK_SETS = {
    "CEDAR": ("cedar_trunk", "tree_bark_03", (0.36, 0.30, 0.26, 1.0)),
    "OAK": ("cedar_trunk", "tree_bark_03", (0.30, 0.27, 0.25, 1.0)),
    "MAPLE": ("cedar_trunk", "tree_bark_03", (0.44, 0.42, 0.40, 1.0)),
    "MAPLE_AUTUMN": ("cedar_trunk", "tree_bark_03", (0.44, 0.42, 0.40, 1.0)),
    "MAPLE_RED": ("cedar_trunk", "tree_bark_03", (0.44, 0.42, 0.40, 1.0)),
    "PINE": ("pine_trunk", "pine_bark", (0.85, 0.72, 0.62, 1.0)),
}


def bark_images(species):
    """(diffuse, roughness, normal, displacement) of the species' bark photo set, or None."""
    if species not in BARK_SETS:
        return None
    folder, prefix, _ = BARK_SETS[species]
    folder = os.path.join(TEXTURE_DIR, folder)
    if not os.path.isdir(folder):
        return None
    return (_load(os.path.join(folder, prefix + "_diff_1k.jpg"), True),
            _load(os.path.join(folder, prefix + "_rough_1k.exr"), False),
            _load(os.path.join(folder, prefix + "_nor_gl_1k.exr"), False),
            _load(os.path.join(folder, prefix + "_disp_1k.png"), False))


def texture_images(species):
    """Images an FBX export needs to write: the leaf card and the bark colour."""
    images = [leaf_image(species)]
    bark = bark_images(species)
    if bark is not None:
        images.append(bark[0])
    return images


def leaf_image(species):
    return _photo_image(SPRIGS[species]["file"] if species in SPRIGS else "Lebanese-Cedar.png")


# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
BARK_VERSION = 3


def _new_material(name, existing=None):
    mat = existing if existing is not None else bpy.data.materials.new(name)
    mat.use_nodes = True
    if existing is not None:
        mat.node_tree.nodes.clear()
        mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
        mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        mat.node_tree.links.new(mat.node_tree.nodes["Principled BSDF"].outputs[0],
                                mat.node_tree.nodes["Material Output"].inputs[0])
    nodes = mat.node_tree.nodes
    bsdf = next(n for n in nodes if n.type == "BSDF_PRINCIPLED")
    return mat, nodes, mat.node_tree.links, bsdf


def leaf_material(species):
    name = "TreeGen_Leaf_%s" % species.title()
    mat = bpy.data.materials.get(name)
    if mat is not None:
        # A material saved in an older .blend may still point at a previous leaf texture.
        for node in mat.node_tree.nodes if mat.node_tree else ():
            if node.type == "TEX_IMAGE" and node.image != leaf_image(species):
                node.image = leaf_image(species)
        return mat
    mat, nodes, links, bsdf = _new_material(name)
    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "CLIP"
        mat.alpha_threshold = 0.5
    bsdf.inputs["Roughness"].default_value = 0.7

    uv = nodes.new("ShaderNodeAttribute")
    uv.attribute_name = "UVMap"
    uv.location = (-900, 200)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = leaf_image(species)
    tex.location = (-700, 200)
    links.new(uv.outputs["Vector"], tex.inputs["Vector"])

    # Wired straight into the BSDF so the FBX exporter finds the texture and writes it
    # into the file; game engines then link it up on import. Use alpha clip (0.5) in the engine.
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    return mat


def _bark_photo_material(name, images, tint_colour, existing=None):
    """Bark from a photo-scanned set. The UVMap attribute repeats the texture around and
    along each branch (see Bark U Tiles / Bark V Scale)."""
    diffuse, rough, normal, height = images
    mat, nodes, links, bsdf = _new_material(name, existing)
    mat["treegen_bark"] = BARK_VERSION
    uv = nodes.new("ShaderNodeAttribute")
    uv.attribute_name = "UVMap"
    uv.location = (-900, 200)

    def tex(image, y):
        node = nodes.new("ShaderNodeTexImage")
        node.image = image
        node.location = (-650, y)
        links.new(uv.outputs["Vector"], node.inputs["Vector"])
        return node

    d, r, n, h = tex(diffuse, 400), tex(rough, 100), tex(normal, -200), tex(height, -500)
    tint = nodes.new("ShaderNodeMix")           # the photo is pale and mossy: darken to old cedar bark
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs["Factor"].default_value = 1.0
    tint.inputs["B"].default_value = tint_colour
    tint.label = "Bark Tint"
    tint.location = (-300, 400)
    links.new(d.outputs["Color"], tint.inputs["A"])
    links.new(tint.outputs["Result"], bsdf.inputs["Base Color"])
    links.new(r.outputs["Color"], bsdf.inputs["Roughness"])
    nmap = nodes.new("ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = 1.0
    nmap.location = (-300, -200)
    links.new(n.outputs["Color"], nmap.inputs["Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.4
    bump.inputs["Distance"].default_value = 0.05
    bump.location = (-100, -300)
    links.new(h.outputs["Color"], bump.inputs["Height"])
    links.new(nmap.outputs["Normal"], bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = (0.3, 0.26, 0.22, 1.0)
    return mat


_BARK = {
    # dark colour, light colour, furrows around the branch, noise scale, stretch along the branch
    "CEDAR": ((0.085, 0.065, 0.05, 1.0), (0.40, 0.33, 0.27, 1.0), 9.0, 2.4, 2.0),
    "PINE": ((0.10, 0.06, 0.045, 1.0), (0.42, 0.26, 0.17, 1.0), 6.0, 2.4, 0.8),
}


def bark_material(species):
    """Procedural bark: furrows that run along the branch (seamless around it, using the
    U coordinate), broken up by 3D noise. Swap in an image on the UVMap attribute to texture it."""
    if species not in BARK_SETS and species not in _BARK:
        return None                                  # bushes have no wood
    name = "TreeGen_Bark_%s" % species.title()
    mat = bpy.data.materials.get(name)
    photos = bark_images(species)
    if photos is not None:
        if mat is not None and mat.get("treegen_bark") == BARK_VERSION:
            return mat
        # Missing, or an older bark saved in the .blend: (re)build it in place so every
        # tree using the material picks up the new look.
        return _bark_photo_material(name, photos, BARK_SETS[species][2], mat)
    if mat is not None:
        return mat
    dark, light, furrows, noise_scale, stretch = _BARK[species]
    mat, nodes, links, bsdf = _new_material(name)
    bsdf.inputs["Roughness"].default_value = 0.9
    # The procedural pattern below does not export; this flat colour is what the FBX carries.
    bsdf.inputs["Base Color"].default_value = tuple(
        (d + l) * 0.5 for d, l in zip(dark[:3], light[:3])) + (1.0,)
    mat.diffuse_color = bsdf.inputs["Base Color"].default_value

    uv = nodes.new("ShaderNodeAttribute")
    uv.attribute_name = "UVMap"
    uv.location = (-1500, 200)
    split = nodes.new("ShaderNodeSeparateXYZ")
    split.location = (-1300, 200)
    links.new(uv.outputs["Vector"], split.inputs[0])

    def math_node(operation, a, b, x, y=200):
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        node.location = (x, y)
        for socket, value in zip(node.inputs, (a, b)):
            if isinstance(value, float):
                socket.default_value = value
            elif value is not None:
                links.new(value, socket)
        return node.outputs[0]

    # Noise is sampled on a cylinder built from the UVs: it wraps around the
    # branch without a seam and stretches along it, whatever way the branch points.
    angle = math_node("MULTIPLY", split.outputs["X"], 2.0 * math.pi, -1100)
    cylinder = nodes.new("ShaderNodeCombineXYZ")
    cylinder.location = (-900, -100)
    links.new(math_node("COSINE", angle, None, -1100, 0), cylinder.inputs["X"])
    links.new(math_node("SINE", angle, None, -1100, -150), cylinder.inputs["Y"])
    links.new(math_node("MULTIPLY", split.outputs["Y"], stretch, -1100, -300), cylinder.inputs["Z"])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.6
    noise.location = (-700, -100)
    links.new(cylinder.outputs["Vector"], noise.inputs["Vector"])

    phase = math_node("MULTIPLY", angle, furrows, -900)
    phase = math_node("ADD", phase, math_node("MULTIPLY", noise.outputs["Fac"], 7.0, -500, 0), -350)
    ridges = math_node("SINE", phase, None, -200)
    ridges = math_node("MULTIPLY", ridges, 0.22, -50)
    height = math_node("ADD", ridges, noise.outputs["Fac"], 100)

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = dark
    ramp.color_ramp.elements[1].position = 0.85
    ramp.color_ramp.elements[1].color = light
    ramp.location = (300, 300)
    links.new(height, ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.7
    bump.location = (300, -100)
    links.new(height, bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    for node in (bsdf, next(n for n in nodes if n.type == "OUTPUT_MATERIAL")):
        node.location.x += 700
    return mat
