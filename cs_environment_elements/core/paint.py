"""Peeling paint for game assets: one material per surface type, any colour.

The colour and how much has peeled off travel on the mesh, not in the textures:
the colour attribute "Paint" (face-corner domain), RGB = paint colour (sRGB),
A = peeling (0 fresh .. 1 bare). glTF exports it as COLOR_0, so in the game ONE
material per surface type serves every building or fence, whatever its paint.
Different parts of one mesh can carry different paint (a cottage's walls and roof):
the value is picked per face from its material (see fill).

Textures per surface type (shared by every colour):
  <set>_diff     what is under the paint (bare weathered wood, bare/rusty steel)
  <set>_paint    R: how long the paint lasts at each spot (rank-equalised: peeling 0.4
                    takes off about 40 %), G: sun fade, B: dirt / shading on the paint
  <set>_nor, <set>_rough   the surface (roughness of the bare material)

Shading (the Godot shader in core/assets/godot does the same):
  uv     = mapping(UV) + (random_x * DETILE_SHIFT, 0)            random per object (from its x, y)
  R      = clamp(R(uv) + DETILE * (R(turned, smaller uv) - 0.5), 0.04, 0.96)   no visible tiling
  z      = zones(UV / ZONE_SIZE + random)                         big soft blobs, one or two per building
  peel   = clamp(peel + zone * (z - 0.5) * 4 peel (1 - peel))     worse in a zone, better outside
                                                                  (still fresh at 0, bare at 1)
  paint  = smoothstep(peel - SOFT, peel + SOFT, R)              1 where paint is left
  rim    = 1 - smoothstep(0, RIM, |R - peel|)                    dirty edge round each flake
  chalk  = (sqrt(colour) * chalk_mul + chalk_add)^2              the colour faded to a pale chalk
  coat   = mix(colour, chalk, G) * B * dirt_gain * (1 - 0.18 rim)
  albedo = mix(under, coat, paint);  roughness = mix(rough_tex, paint_rough, paint)
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
VERSION = 3
# Detiling (see peel_material): per-object shift along U, and a second, turned, smaller read
DETILE = 0.35
DETILE_SCALE = 0.41
DETILE_ANGLE = 37.0
DETILE_SHIFT = 7.0
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
    names in the neighborhood textures), scale (repeats per metre), rot (degrees),
    chalk_mul, chalk_add, paint_rough, dirt_gain, base (viewport colour)."""
    import math

    from . import neighborhood_materials as nm

    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)   # rebuilt in place if it exists
    mat["paint_version"] = VERSION
    mat.use_nodes = True
    mat.diffuse_color = (*spec.get("base", (0.4, 0.38, 0.34)), 1.0)
    nt = mat.node_tree
    nt.nodes.clear()
    L = nt.links.new

    def node(kind, x, y, **props):
        n = nt.nodes.new(kind)
        n.location = (x, y)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def math_op(op, x, y, *inputs):
        n = node("ShaderNodeMath", x, y, operation=op)
        for i, v in enumerate(inputs):
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L(v, n.inputs[i])
        return n.outputs[0]

    def mix(data_type, blend, x, y, fac, a, b):
        m = node("ShaderNodeMix", x, y, data_type=data_type, blend_type=blend)
        suffix = "Color" if data_type == "RGBA" else "Float"
        sock = {s.identifier: s for s in m.inputs}
        for key, v in (("Factor_Float", fac), (f"A_{suffix}", a), (f"B_{suffix}", b)):
            if isinstance(v, (int, float, tuple)):
                sock[key].default_value = v
            else:
                L(v, sock[key])
        return next(s for s in m.outputs if s.identifier == f"Result_{suffix}")

    out = node("ShaderNodeOutputMaterial", 1300, 0)
    bsdf = node("ShaderNodeBsdfPrincipled", 1000, 0)
    L(bsdf.outputs["BSDF"], out.inputs["Surface"])

    coord = node("ShaderNodeTexCoord", -1500, 0)
    mapping = node("ShaderNodeMapping", -1300, 0)
    s = spec.get("scale", 1.0)
    mapping.inputs["Scale"].default_value = (s, s, 1.0)
    if spec.get("rot"):
        mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(spec["rot"]))
    L(coord.outputs["UV"], mapping.inputs["Vector"])

    # Detiling: each object gets its own shift along the boards (from where it stands, so
    # its LODs match), and the wear is read a second time, turned and smaller, so the
    # tile never repeats the same chips.
    obj = node("ShaderNodeObjectInfo", -2100, -350)
    flat = node("ShaderNodeVectorMath", -1900, -350, operation="MULTIPLY")
    L(obj.outputs["Location"], flat.inputs[0])
    flat.inputs[1].default_value = (1.0, 1.0, 0.0)              # x, y only: lifting a building keeps it
    noise = node("ShaderNodeTexWhiteNoise", -1700, -350, noise_dimensions="3D")
    L(flat.outputs["Vector"], noise.inputs["Vector"])
    rnd = node("ShaderNodeSeparateColor", -1500, -350)
    L(noise.outputs["Color"], rnd.inputs["Color"])
    shift = node("ShaderNodeCombineXYZ", -1300, -250)
    L(math_op("MULTIPLY", -1400, -150, rnd.outputs[0], DETILE_SHIFT), shift.inputs["X"])
    L(shift.outputs["Vector"], mapping.inputs["Location"])
    mapping2 = node("ShaderNodeMapping", -1100, -250, label="Wear, second read")
    L(mapping.outputs["Vector"], mapping2.inputs["Vector"])
    mapping2.inputs["Scale"].default_value = (DETILE_SCALE, DETILE_SCALE, 1.0)
    mapping2.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(DETILE_ANGLE))
    shift2 = node("ShaderNodeCombineXYZ", -1300, -450)
    L(math_op("MULTIPLY", -1400, -400, rnd.outputs[1], 5.0), shift2.inputs["X"])
    L(math_op("MULTIPLY", -1400, -550, rnd.outputs[2], 5.0), shift2.inputs["Y"])
    L(shift2.outputs["Vector"], mapping2.inputs["Location"])

    def tex(fname, non_color, y, label):
        n = node("ShaderNodeTexImage", -1000, y, label=label, name=label)
        n.image = nm._image(fname, non_color)
        L(mapping.outputs["Vector"], n.inputs["Vector"])
        return n

    under = tex(spec["under"], False, 400, "Under")
    data = tex(spec["data"], True, 50, "PaintData")
    nor = tex(spec["nor"], True, -700, "Normal")
    rough = tex(spec["rough"], True, -400, "Rough")
    attr = node("ShaderNodeVertexColor", -1000, -1000, layer_name=ATTR, label="Paint (RGB colour, A peeling)")
    sep = node("ShaderNodeSeparateColor", -750, 50)
    L(data.outputs["Color"], sep.inputs["Color"])
    R, G, B = sep.outputs[0], sep.outputs[1], sep.outputs[2]
    data2 = node("ShaderNodeTexImage", -850, -150, label="PaintData2", name="PaintData2")
    data2.image = data.image
    L(mapping2.outputs["Vector"], data2.inputs["Vector"])
    sep2 = node("ShaderNodeSeparateColor", -700, -150)
    L(data2.outputs["Color"], sep2.inputs["Color"])
    # R = clamp(R + DETILE * (R2 - 0.5), 0.04, 0.96): still all paint at peeling 0, none at 1
    R = math_op("ADD", -550, -100, R, math_op("MULTIPLY_ADD", -550, -200, sep2.outputs[0], DETILE, -DETILE / 2))
    R = math_op("MINIMUM", -400, -100, math_op("MAXIMUM", -450, -200, R, 0.04), 0.96)
    peel = attr.outputs["Alpha"]

    # Wear zones: big soft blobs over the whole building (not the tile)
    zmap = node("ShaderNodeMapping", -1100, -800, label="Wear zones")
    L(coord.outputs["UV"], zmap.inputs["Vector"])
    zmap.inputs["Scale"].default_value = (1.0 / ZONE_SIZE, 1.0 / ZONE_SIZE, 1.0)
    zshift = node("ShaderNodeCombineXYZ", -1300, -800)
    L(rnd.outputs[1], zshift.inputs["X"])
    L(rnd.outputs[2], zshift.inputs["Y"])
    L(zshift.outputs["Vector"], zmap.inputs["Location"])
    ztex = node("ShaderNodeTexImage", -900, -800, label="WearZones", name="WearZones")
    ztex.image = nm._image(ZONE_TEX, True)
    L(zmap.outputs["Vector"], ztex.inputs["Vector"])
    z = ztex.outputs["Color"]
    k = math_op("MULTIPLY", -700, -900, peel, math_op("SUBTRACT", -850, -950, 1.0, peel))   # peel (1 - peel)
    dz = math_op("MULTIPLY_ADD", -700, -800, z, 4.0 * spec.get("zone", 0.5), -2.0 * spec.get("zone", 0.5))
    peel = math_op("ADD", -500, -850, peel, math_op("MULTIPLY", -600, -850, k, dz))
    peel = math_op("MINIMUM", -350, -850, math_op("MAXIMUM", -420, -900, peel, 0.0), 1.0)

    paint_rng = node("ShaderNodeMapRange", -450, -150, interpolation_type="SMOOTHSTEP", label="Paint left")
    L(R, paint_rng.inputs["Value"])
    L(math_op("SUBTRACT", -650, -250, peel, SOFT), paint_rng.inputs["From Min"])
    L(math_op("ADD", -650, -400, peel, SOFT), paint_rng.inputs["From Max"])
    paint = paint_rng.outputs["Result"]

    dist = math_op("ABSOLUTE", -450, -450, math_op("SUBTRACT", -650, -550, R, peel))
    rim_rng = node("ShaderNodeMapRange", -250, -450, interpolation_type="SMOOTHSTEP", label="Flake rim")
    L(dist, rim_rng.inputs["Value"])
    rim_rng.inputs["From Max"].default_value = RIM
    rim_rng.inputs["To Min"].default_value = 1.0
    rim_rng.inputs["To Max"].default_value = 0.0
    darken = math_op("MULTIPLY_ADD", -50, -450, rim_rng.outputs["Result"], -0.18, 1.0)

    root = node("ShaderNodeGamma", -650, 600)                    # ~ sRGB of the colour
    L(attr.outputs["Color"], root.inputs["Color"])
    root.inputs["Gamma"].default_value = 0.5
    chalk_s = node("ShaderNodeVectorMath", -450, 600, operation="MULTIPLY_ADD")
    L(root.outputs["Color"], chalk_s.inputs[0])
    cm, ca = spec.get("chalk_mul", 0.55), spec.get("chalk_add", 0.4)
    chalk_s.inputs[1].default_value = (cm, cm, cm)
    chalk_s.inputs[2].default_value = (ca, ca, ca)
    chalk = node("ShaderNodeGamma", -250, 600)
    L(chalk_s.outputs["Vector"], chalk.inputs["Color"])
    chalk.inputs["Gamma"].default_value = 2.0
    faded = mix("RGBA", "MIX", -50, 500, G, attr.outputs["Color"], chalk.outputs["Color"])
    dirt = math_op("MULTIPLY", -250, 250, B, spec.get("dirt_gain", 1.0))
    dirt = math_op("MULTIPLY", -50, 250, dirt, darken)
    coat = mix("RGBA", "MULTIPLY", 200, 400, 1.0, faded, dirt)
    albedo = mix("RGBA", "MIX", 500, 300, paint, under.outputs["Color"], coat)
    roughness = mix("FLOAT", "MIX", 500, -300, paint, rough.outputs["Color"], spec.get("paint_rough", 0.65))
    if spec.get("rust"):                    # roofs: rust streaks (data alpha), mostly in the wear zones
        data.image.alpha_mode = "CHANNEL_PACKED"
        zr = node("ShaderNodeMapRange", 300, -950, interpolation_type="SMOOTHSTEP", label="Rust zone")
        L(z, zr.inputs["Value"])
        zr.inputs["From Min"].default_value, zr.inputs["From Max"].default_value = 0.35, 0.9
        amount = math_op("MULTIPLY", 500, -900, data.outputs["Alpha"],
                         math_op("MULTIPLY_ADD", 450, -1000, zr.outputs["Result"], 1.7, 0.3))
        amount = math_op("MINIMUM", 650, -900, amount, 1.0)
        rust = math_op("MULTIPLY", 800, -900, amount, math_op("MULTIPLY_ADD", 650, -1050, paint, -0.7, 1.0))
        rust_lin = tuple(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in RUST_SRGB)
        albedo = mix("RGBA", "MIX", 750, 300, rust, albedo, (*rust_lin, 1.0))
        roughness = mix("FLOAT", "MIX", 750, -300, rust, roughness, 0.85)
    L(albedo, bsdf.inputs["Base Color"])
    L(roughness, bsdf.inputs["Roughness"])
    nmap = node("ShaderNodeNormalMap", 500, -700)
    L(nor.outputs["Color"], nmap.inputs["Color"])
    L(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat
