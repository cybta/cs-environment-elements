"""World materials: ground textures (baked by tools/make_world_textures.py), the splat
terrain shader, water, road paint and small props. Registered into the neighborhood
material recipes so they follow the same C_* naming and metric-UV convention."""

import bpy

from ..core import neighborhood_materials as nm

nm.RECIPES.setdefault("C_world_dirt", dict(tex="world_dirt", scale=0.25, base=(0.33, 0.25, 0.17), rough=0.9))
nm.RECIPES.setdefault("C_world_rock", dict(tex="world_rock", scale=0.2, base=(0.45, 0.43, 0.4), rough=0.85))
nm.RECIPES.setdefault("C_world_sand", dict(tex="world_sand", scale=0.33, base=(0.72, 0.64, 0.48), rough=0.9))
nm.RECIPES.setdefault("C_world_concrete", dict(tex="concrete_wall_008", scale=0.5, base=(0.55, 0.54, 0.52),
                                               rough=0.85, tint=(0.95, 0.95, 0.95)))
nm.RECIPES.setdefault("C_world_old_concrete", dict(tex="concrete_wall_008", scale=0.5, base=(0.45, 0.43, 0.4),
                                                   rough=0.9, tint=(0.75, 0.72, 0.68)))
nm.RECIPES.setdefault("C_world_timber", dict(tex="cottage_wood", scale=1 / 1.44, rot=90.0,
                                             base=(0.38, 0.33, 0.27), rough=0.85))

# Ground layers of the terrain shader: (texture set, metres per repeat)
LAYERS = (("world_grass", 4.0), ("world_dirt", 4.0), ("world_rock", 11.0), ("world_sand", 3.0))


def _special(name, fn):
    if name not in nm._SPECIAL:
        nm._SPECIAL[name] = fn


_special("C_world_line", lambda n: nm._build_smooth(n, (0.85, 0.85, 0.8), 0.6, 0.05))
_special("C_world_line_yellow", lambda n: nm._build_smooth(n, (0.8, 0.6, 0.1), 0.6, 0.05))
_special("C_world_steel", lambda n: nm._build_metal(n, (0.2, 0.21, 0.22), 0.45, 0.9))
_special("C_world_rust", lambda n: nm._build_metal(n, (0.16, 0.09, 0.06), 0.8, 0.4))
_special("C_world_rubber", lambda n: nm._build_smooth(n, (0.42, 0.14, 0.1), 0.95, 0.1))


def _lamp_glass(name):
    mat, nt, bsdf = nm._new(name, (1.0, 0.92, 0.75), 0.3)
    for key in ("Emission Color", "Emission"):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = (1.0, 0.85, 0.6, 1.0)
            break
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = 3.0
    return mat


_special("C_world_lamp", _lamp_glass)


def ensure(name):
    return nm.ensure(name)


def water():
    """Deep river/lake water: dark green-blue, glossy, with a slow ripple bump."""
    name = "C_world_water"
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat, nt, bsdf = nm._new(name, (0.012, 0.045, 0.05), 0.12)
    bsdf.inputs["IOR"].default_value = 1.33
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-500, -300)
    noise.inputs["Scale"].default_value = 0.6
    noise.inputs["Detail"].default_value = 6.0
    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-700, -300)
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-200, -300)
    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.05
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = (0.05, 0.15, 0.17, 1.0)
    return mat


def terrain(splat_img):
    """Four ground layers blended by the splat map (UVMap = map-wide 0..1); every layer
    tiles in world metres, and a large noise darkens/lightens the grass to hide repeats."""
    name = "C_world_terrain"
    mat = bpy.data.materials.get(name)
    if mat is not None:
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexImage" and node.label == "splat":
                node.image = splat_img
        return mat
    mat, nt, bsdf = nm._new(name, (0.25, 0.4, 0.15), 0.92)
    N = nt.nodes
    uv = N.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    uv.location = (-1600, 600)
    sp = N.new("ShaderNodeTexImage")
    sp.label = "splat"
    sp.image = splat_img
    sp.interpolation = "Linear"
    sp.extension = "EXTEND"
    sp.location = (-1350, 600)
    nt.links.new(uv.outputs["UV"], sp.inputs["Vector"])
    sep = N.new("ShaderNodeSeparateColor")
    sep.location = (-1050, 600)
    nt.links.new(sp.outputs["Color"], sep.inputs["Color"])

    coord = N.new("ShaderNodeTexCoord")
    coord.location = (-1600, 0)
    cols, nors, roughs = [], [], []
    for k, (tex, size) in enumerate(LAYERS):
        mp = N.new("ShaderNodeMapping")
        mp.location = (-1350, -k * 350)
        mp.inputs["Scale"].default_value = (1 / size, 1 / size, 1 / size)
        nt.links.new(coord.outputs["Object"], mp.inputs["Vector"])
        out = []
        for j, (kind, data) in enumerate((("diff", False), ("nor", True), ("rough", True))):
            img = nm._image(f"{tex}_{kind}.jpg", data)
            node = N.new("ShaderNodeTexImage")
            node.image = img
            node.location = (-1100 + j * 0, -k * 350 - j * 100)
            if tex == "world_rock":            # cliffs: no stretching
                node.projection = "BOX"
                node.projection_blend = 0.35
            nt.links.new(mp.outputs["Vector"], node.inputs["Vector"])
            out.append(node.outputs["Color"])
        cols.append(out[0])
        nors.append(out[1])
        roughs.append(out[2])

    # Grass sampled again at 3.43x the size and blended in: hides the repeat at a distance
    mp2 = N.new("ShaderNodeMapping")
    mp2.location = (-1350, 300)
    mp2.inputs["Scale"].default_value = (1 / 13.7, 1 / 13.7, 1 / 13.7)
    mp2.inputs["Rotation"].default_value = (0.0, 0.0, 0.6)
    nt.links.new(coord.outputs["Object"], mp2.inputs["Vector"])
    g2 = N.new("ShaderNodeTexImage")
    g2.image = nm._image(f"{LAYERS[0][0]}_diff.jpg", False)
    g2.location = (-1100, 300)
    nt.links.new(mp2.outputs["Vector"], g2.inputs["Vector"])
    gmix = N.new("ShaderNodeMix")
    gmix.data_type = "RGBA"
    gmix.location = (-800, 450)
    nm._sock(gmix.inputs, "Factor_Float").default_value = 0.5
    nt.links.new(cols[0], nm._sock(gmix.inputs, "A_Color"))
    nt.links.new(g2.outputs["Color"], nm._sock(gmix.inputs, "B_Color"))
    cols[0] = nm._sock(gmix.outputs, "Result_Color")

    # Large light/dark patches over the whole ground
    big = N.new("ShaderNodeTexNoise")
    big.location = (-1100, 900)
    big.inputs["Scale"].default_value = 0.012
    big.inputs["Detail"].default_value = 3.0
    nt.links.new(coord.outputs["Object"], big.inputs["Vector"])
    ramp = N.new("ShaderNodeMapRange")
    ramp.location = (-850, 900)
    ramp.inputs["To Min"].default_value = 0.75
    ramp.inputs["To Max"].default_value = 1.2
    nt.links.new(big.outputs["Fac"], ramp.inputs["Value"])
    tint = N.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.location = (-800, 300)
    nm._sock(tint.inputs, "Factor_Float").default_value = 1.0
    comb = N.new("ShaderNodeCombineColor")
    comb.location = (-1000, 1100)
    for ch in ("Red", "Green", "Blue"):
        nt.links.new(ramp.outputs["Result"], comb.inputs[ch])
    nt.links.new(comb.outputs["Color"], nm._sock(tint.inputs, "B_Color"))

    def stack(values, kind, y):
        cur = values[0]
        for k, ch in ((1, "Red"), (2, "Green"), (3, "Blue")):
            mix = N.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.location = (-500 + k * 120, y)
            nt.links.new(sep.outputs[ch], nm._sock(mix.inputs, "Factor_Float"))
            nt.links.new(cur, nm._sock(mix.inputs, "A_Color"))
            nt.links.new(values[k], nm._sock(mix.inputs, "B_Color"))
            cur = nm._sock(mix.outputs, "Result_Color")
        return cur

    nt.links.new(stack(cols, "col", 300), nm._sock(tint.inputs, "A_Color"))
    nt.links.new(nm._sock(tint.outputs, "Result_Color"), bsdf.inputs["Base Color"])
    nt.links.new(stack(roughs, "rough", -100), bsdf.inputs["Roughness"])
    nmap = N.new("ShaderNodeNormalMap")
    nmap.location = (100, -400)
    nmap.inputs["Strength"].default_value = 0.3
    nt.links.new(stack(nors, "nor", -400), nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    mat.diffuse_color = (0.25, 0.38, 0.16, 1.0)
    return mat
