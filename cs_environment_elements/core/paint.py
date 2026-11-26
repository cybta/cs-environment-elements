"""Peeling paint for game assets: one material per surface type, any colour.

The colour and how much has peeled off travel on the mesh, not in the textures:
the colour attribute "Paint" (face-corner domain), RGB = paint colour (sRGB),
A = peeling (0 fresh .. 1 bare). glTF exports it as COLOR_0, so in the game ONE
material per surface type serves every building or fence, whatever its paint.
Different parts of one mesh can carry different paint (a cottage's walls and roof):
the value is picked per face from its material (see fill).

Textures per surface type (shared by every colour):
  <set>_diff     what is under the paint (bare weathered wood, bare/rusty steel)
  <set>_paint    R: board-level wear (board edges, board age), G: sun fade, B: dirt / shading on the paint
  <set>_nor, <set>_rough   the surface (roughness of the bare material)
and for every set: wear_zones.png (big soft patches) and paint_flakes.png (cracked flakes,
tools/make_paint_flakes.py); see core/paint_nodes.py.

Shading (the Godot shader in core/assets/godot does the same):
  uv     = mapping(UV) + (random_x * DETILE_SHIFT, 0)            random per object (from its x, y)
  R      = paint_nodes.lasting: big weather patches (two reads of wear_zones.png at sizes that never
           line up) + cracked flakes (paint_flakes.png, along the grain; round on metal roofs) + the
           tile's own R (board edges), made about uniform        how long the paint lasts here
  z      = zones(UV / ZONE_SIZE + random)                         big soft blobs, one or two per building
  peel   = clamp(peel + zone * (z - 0.5) * 4 peel (1 - peel))     worse in a zone, better outside
                                                                  (still fresh at 0, bare at 1)
  paint  = smoothstep(peel - SOFT, peel + SOFT, R)              1 where paint is left
  rim    = 1 - smoothstep(0, RIM, |R - peel|)                    dirty edge round each flake
  crack  = 1 - 0.4 (1 - flakes.G) (1 - smoothstep(0, 0.2, R - peel))   wood only: cracks before it flakes
  chalk  = (sqrt(colour) * chalk_mul + chalk_add)^2              the colour faded to a pale chalk
  coat   = mix(colour, chalk, G) * B * dirt_gain * (1 - 0.18 rim) * crack
  bare   = under * under_tint                                  the bare wood: the timber cottages' brown
  albedo = mix(bare, coat, paint);  roughness = mix(rough_tex, paint_rough, paint)
  roofs (spec rust): rust = clamp(A * (0.3 + 1.7 smoothstep(0.35, 0.9, z))) * (1 - 0.7 paint)
                     albedo = mix(albedo, RUST, rust);  roughness = mix(roughness, 0.85, rust)
"""

import json
from contextlib import contextmanager

import numpy as np

import bpy

ATTR = "Paint"
SOFT = 0.03
RIM = 0.06
VERSION = 6
DETILE_SHIFT = 7.0          # per-object shift along U (the tile's boards and the flakes)
# Wear zones: wear_zones.png stretched over ZONE_SIZE metres (shifted per object), so the
# damage gathers in one or two areas of a building instead of repeating with the tile
ZONE_TEX = "wear_zones.png"
ZONE_SIZE = 16.0
RUST_SRGB = (0.46, 0.25, 0.12)

_quiet = {"depth": 0}


@contextmanager
def quiet():
    """Set paint settings from code (the World builder) without the panels' live repaint."""
    _quiet["depth"] += 1
    try:
        yield
    finally:
        _quiet["depth"] -= 1


def is_quiet():
    return _quiet["depth"] > 0


# --------------------------------------------------------------------------
# The per-mesh paint
# --------------------------------------------------------------------------

def fill(me, value, by_material=None):
    """Write the paint: `value` (sRGB r, g, b, peel) everywhere, except faces whose
    material name is in `by_material` ({name: value})."""
    attr = me.color_attributes.get(ATTR)
    if attr is not None and (attr.domain != "CORNER" or attr.data_type != "BYTE_COLOR"):
        me.color_attributes.remove(attr)
        attr = None
    if attr is None:
        attr = me.color_attributes.new(ATTR, "BYTE_COLOR", "CORNER")
    n_loops = len(me.loops)
    if n_loops:
        table = [tuple(value)] * max(1, len(me.materials))
        for i, m in enumerate(me.materials):
            if m is not None and by_material and m.name in by_material:
                table[i] = tuple(by_material[m.name])
        if len(set(table)) == 1:
            vals = np.tile(np.asarray(table[0], np.float32), n_loops)
        else:
            mi = np.empty(len(me.polygons), np.int32)
            me.polygons.foreach_get("material_index", mi)
            tot = np.empty(len(me.polygons), np.int32)
            me.polygons.foreach_get("loop_total", tot)
            per_loop = np.repeat(np.minimum(mi, len(table) - 1), tot)
            vals = np.asarray(table, np.float32)[per_loop].ravel()
        attr.data.foreach_set("color_srgb", vals)
    idx = list(me.color_attributes).index(attr)
    me.color_attributes.active_color_index = idx         # exported as COLOR_0
    me.color_attributes.render_color_index = idx


def store(root, value, by_material=None):
    """Remember a generated object's paint on its root (the LOD builder reads it back)."""
    root["paint"] = list(value)
    root["paint_by_mat"] = json.dumps({k: list(v) for k, v in (by_material or {}).items()})


def stored(root):
    """(value, by_material) saved on `root`, or None."""
    if "paint" not in root:
        return None
    try:
        by = json.loads(root.get("paint_by_mat", "{}"))
    except ValueError:
        by = {}
    return list(root["paint"]), by


def apply(root, value, by_material=None):
    """Store and paint every mesh under `root` (LOD0 parts, leaves, LOD meshes)."""
    store(root, value, by_material)
    for ob in root.children_recursive:
        if ob.type == "MESH" and ob.data is not None:
            fill(ob.data, value, by_material)


def fill_from_root(me, root):
    got = stored(root)
    if got is not None:
        fill(me, *got)


# --------------------------------------------------------------------------
# Material
# --------------------------------------------------------------------------

def peel_material(name, spec):
    """A peeling-paint material from a texture set. spec: under, data, nor, rough (file
    names in the neighborhood textures), scale (repeats per metre), rot (degrees), metal
    (round flakes instead of flakes along the grain), under_tint (rgb multiplier on the bare surface:
    the timber cottages' old brown wood), chalk_mul, chalk_add, paint_rough,
    dirt_gain, zone, rust, base (viewport colour). Where the paint lasts: core/paint_nodes."""
    from . import neighborhood_materials as nm
    from . import paint_nodes as pn

    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)   # rebuilt in place if it exists
    mat["paint_version"] = VERSION
    mat.use_nodes = True
    mat.diffuse_color = (*spec.get("base", (0.4, 0.38, 0.34)), 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    g = pn.Graph(nt)
    L, math_op, mix = g.link, g.math, g.mix

    out = g.node("ShaderNodeOutputMaterial", 1300, 0)
    bsdf = g.node("ShaderNodeBsdfPrincipled", 1000, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])

    # each object gets its own random values (from where it stands, so its LODs match)
    coord = g.node("ShaderNodeTexCoord", -2300, 0)
    obj = g.node("ShaderNodeObjectInfo", -2500, -350)
    flat = g.node("ShaderNodeVectorMath", -2300, -350, operation="MULTIPLY")
    L(obj.outputs["Location"], flat.inputs[0])
    flat.inputs[1].default_value = (1.0, 1.0, 0.0)              # x, y only: lifting a building keeps it
    noise = g.node("ShaderNodeTexWhiteNoise", -2100, -350, noise_dimensions="3D")
    L(flat.outputs["Vector"], noise.inputs["Vector"])
    rnd = g.node("ShaderNodeSeparateColor", -1900, -350)
    L(noise.outputs["Color"], rnd.inputs["Color"])
    rnd = (rnd.outputs[0], rnd.outputs[1], rnd.outputs[2])
    s = spec.get("scale", 1.0)
    tile = g.mapping(-1300, 0, coord.outputs["UV"], s, spec.get("rot", 0.0),
                     loc=(math_op("MULTIPLY", -1700, -150, rnd[0], DETILE_SHIFT), 0.0), label="Tile")

    def tex(fname, non_color, y, label):
        return g.image(-1000, y, nm._image(fname, non_color), tile, label)

    under = tex(spec["under"], False, 400, "Under")
    data = tex(spec["data"], True, 50, "PaintData")
    nor = tex(spec["nor"], True, -700, "Normal")
    rough = tex(spec["rough"], True, -400, "Rough")
    attr = g.node("ShaderNodeVertexColor", -1000, -1000, layer_name=ATTR, label="Paint (RGB colour, A peeling)")
    sep = g.node("ShaderNodeSeparateColor", -750, 50)
    L(data.outputs["Color"], sep.inputs["Color"])
    G, B = sep.outputs[1], sep.outputs[2]
    flake_uv = g.node("ShaderNodeVectorMath", -1100, -1500, operation="SCALE")   # tiles -> flake tiles
    L(tile, flake_uv.inputs[0])
    flake_uv.inputs["Scale"].default_value = 1.0 / (s * pn.FLAKE_SIZE)
    R, cracks = pn.lasting(g, lambda f: nm._image(f, True), coord.outputs["UV"], flake_uv.outputs["Vector"],
                           sep.outputs[0], rnd, metal=spec.get("metal", False), x=-2300, y=-1300)
    peel = attr.outputs["Alpha"]

    # Wear zones: big soft blobs over the whole building
    z = g.image(-900, -2300, nm._image(ZONE_TEX, True),
                g.mapping(-1100, -2300, coord.outputs["UV"], 1.0 / ZONE_SIZE, loc=(rnd[1], rnd[2]),
                          label="Wear zones"), "WearZones").outputs["Color"]
    k = math_op("MULTIPLY", -700, -2400, peel, math_op("SUBTRACT", -850, -2450, 1.0, peel))   # peel (1 - peel)
    dz = math_op("MULTIPLY_ADD", -700, -2300, z, 4.0 * spec.get("zone", 0.5), -2.0 * spec.get("zone", 0.5))
    peel = math_op("ADD", -500, -2350, peel, math_op("MULTIPLY", -600, -2350, k, dz))
    peel = math_op("MINIMUM", -350, -2350, math_op("MAXIMUM", -420, -2400, peel, 0.0), 1.0)

    paint = g.smooth(-250, -150, R, math_op("SUBTRACT", -450, -250, peel, SOFT),
                     math_op("ADD", -450, -400, peel, SOFT), label="Paint left")
    dist = math_op("ABSOLUTE", -450, -450, math_op("SUBTRACT", -650, -550, R, peel))
    rim = g.smooth(-250, -450, dist, 0.0, RIM, 1.0, 0.0, "Flake rim")
    darken = math_op("MULTIPLY_ADD", -50, -450, rim, -0.18, 1.0)
    if not spec.get("metal"):
        darken = math_op("MULTIPLY", 100, -550, darken, pn.crack(g, R, peel, cracks, x=-250, y=-750))

    root = g.node("ShaderNodeGamma", -650, 600)                    # ~ sRGB of the colour
    L(attr.outputs["Color"], root.inputs["Color"])
    root.inputs["Gamma"].default_value = 0.5
    chalk_s = g.node("ShaderNodeVectorMath", -450, 600, operation="MULTIPLY_ADD")
    L(root.outputs["Color"], chalk_s.inputs[0])
    cm, ca = spec.get("chalk_mul", 0.55), spec.get("chalk_add", 0.4)
    chalk_s.inputs[1].default_value = (cm, cm, cm)
    chalk_s.inputs[2].default_value = (ca, ca, ca)
    chalk = g.node("ShaderNodeGamma", -250, 600)
    L(chalk_s.outputs["Vector"], chalk.inputs["Color"])
    chalk.inputs["Gamma"].default_value = 2.0
    faded = mix("RGBA", "MIX", -50, 500, G, attr.outputs["Color"], chalk.outputs["Color"])
    dirt = math_op("MULTIPLY", -250, 250, B, spec.get("dirt_gain", 1.0))
    dirt = math_op("MULTIPLY", -50, 250, dirt, darken)
    coat = mix("RGBA", "MULTIPLY", 200, 400, 1.0, faded, dirt)
    bare = under.outputs["Color"]
    if spec.get("under_tint"):            # where it peeled: the old brown wood of the timber cottages
        tint = g.node("ShaderNodeVectorMath", -300, 800, operation="MULTIPLY", label="Bare wood tint")
        L(bare, tint.inputs[0])
        tint.inputs[1].default_value = spec["under_tint"]
        bare = tint.outputs["Vector"]
    albedo = mix("RGBA", "MIX", 500, 300, paint, bare, coat)
    roughness = mix("FLOAT", "MIX", 500, -300, paint, rough.outputs["Color"], spec.get("paint_rough", 0.65))
    if spec.get("rust"):                    # roofs: rust streaks (data alpha), mostly in the wear zones
        data.image.alpha_mode = "CHANNEL_PACKED"
        zr = g.smooth(300, -950, z, 0.35, 0.9, label="Rust zone")
        amount = math_op("MULTIPLY", 500, -900, data.outputs["Alpha"],
                         math_op("MULTIPLY_ADD", 450, -1000, zr, 1.7, 0.3))
        amount = math_op("MINIMUM", 650, -900, amount, 1.0)
        rust = math_op("MULTIPLY", 800, -900, amount, math_op("MULTIPLY_ADD", 650, -1050, paint, -0.7, 1.0))
        rust_lin = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in RUST_SRGB)
        albedo = mix("RGBA", "MIX", 750, 300, rust, albedo, (*rust_lin, 1.0))
        roughness = mix("FLOAT", "MIX", 750, -300, rust, roughness, 0.85)
    L(albedo, bsdf.inputs["Base Color"])
    L(roughness, bsdf.inputs["Roughness"])
    nmap = g.node("ShaderNodeNormalMap", 500, -700)
    L(nor.outputs["Color"], nmap.inputs["Color"])
    L(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
