"""The materials of "the Neighborhood" scene, so generated houses match it.

Each material is recreated from the scene's own node setup and keeps the
scene's name (C_wall_cream, C_roof_red, ...). If the open file already has a
material of that name it is reused as-is, so a house built inside the
neighborhood shares its materials with the hand-made houses.

All of them read the mesh UVs, which the generator writes in metres
(1 UV unit = 1 m), exactly like the scene's houses.

Textures ship in assets/neighborhood/ (Poly Haven CC0 + in-house).
"""

import math
import os
import random

import bpy

TEX_DIR = os.path.join(os.path.dirname(__file__), "assets", "neighborhood")

_PLASTER = "painted_plaster_wall"

# name -> texture set, file extension, mapping scale (repeats per metre; None =
# no Mapping node), Principled base colour / roughness, optional multiply tint
# and optional hue/saturation/value on the colour map.
RECIPES = {
    # Facades (tinted painted plaster)
    "C_wall_cream": dict(tex=_PLASTER, scale=0.4, base=(0.93, 0.85, 0.66), rough=0.9, tint=(1.5, 1.354, 1.015)),
    "C_wall_white": dict(tex=_PLASTER, scale=0.4, base=(0.9, 0.88, 0.84), rough=0.9, tint=(1.5, 1.5, 1.446)),
    "C_wall_grey": dict(tex=_PLASTER, scale=0.4, base=(0.7, 0.7, 0.72), rough=0.9, tint=(1.2, 1.2, 1.231)),
    "C_wall_peach": dict(tex=_PLASTER, scale=0.4, base=(0.92, 0.68, 0.55), rough=0.9, tint=(1.5, 1.077, 0.846)),
    "C_wall_sage": dict(tex=_PLASTER, scale=0.4, base=(0.66, 0.76, 0.62), rough=0.9, tint=(1.108, 1.292, 1.015)),
    "C_wall_blue": dict(tex=_PLASTER, scale=0.4, base=(0.6, 0.72, 0.84), rough=0.9, tint=(1.015, 1.231, 1.462)),
    "C_house_brick": dict(tex="red_brick_03", scale=0.667, base=(0.45, 0.2, 0.13), rough=0.85),
    # Interior
    "C_interior_plaster": dict(tex=_PLASTER, scale=0.4, base=(0.88, 0.86, 0.82), rough=0.9, tint=(1.45, 1.4, 1.32)),
    "C_ceiling": dict(tex=_PLASTER, scale=0.4, base=(0.93, 0.93, 0.92), rough=0.9, tint=(1.5, 1.5, 1.48)),
    "C_floor_wood": dict(tex="wood_floor", scale=0.5, base=(0.45, 0.3, 0.18), rough=0.35),
    "C_stair_wood": dict(tex="wood_floor", scale=0.667, base=(0.35, 0.22, 0.12), rough=0.35, tint=(0.7, 0.6, 0.5)),
    "C_bath_tile_floor": dict(tex="house3_tile_floor_v2", ext="png", base=(1.0, 1.0, 1.0), rough=0.45),
    "C_bath_tile_wall": dict(tex="house3_tile_wall_v2", ext="png", base=(1.0, 1.0, 1.0), rough=0.25),
    "C_door_wood": dict(tex="wood_table_001", scale=0.8, base=(0.8, 0.8, 0.8), rough=0.5, hsv=(0.53, 0.75, 2.0)),
    # Roofs
    "C_roof_red": dict(tex="clay_roof_tiles_02", scale=0.5, base=(0.6, 0.18, 0.12), rough=0.7),
    "C_roof_dark": dict(tex="grey_roof_tiles", scale=0.5, base=(0.18, 0.2, 0.23), rough=0.7, tint=(0.55, 0.58, 0.62)),
    "C_roof_teal": dict(tex="grey_roof_tiles", scale=0.5, base=(0.18, 0.38, 0.4), rough=0.7, tint=(0.45, 0.75, 0.75)),
    "C_roof_flat": dict(tex="concrete_wall_008", scale=0.5, base=(0.55, 0.55, 0.55), rough=0.85),
    "C_plinth": dict(tex="concrete_wall_008", scale=0.5, base=(0.45, 0.43, 0.4), rough=0.85),
    # Outdoors (roads, gardens, walls)
    "C_asphalt": dict(tex="asphalt_02", scale=0.25, base=(0.08, 0.08, 0.09), rough=0.9),
    "C_sidewalk": dict(tex="square_concrete_pavers", scale=0.5, base=(0.62, 0.6, 0.57), rough=0.85),
    "C_curb": dict(tex="concrete_wall_008", scale=0.5, base=(0.6, 0.6, 0.58), rough=0.85),
    "C_stone": dict(tex="concrete_wall_008", scale=0.5, base=(0.55, 0.53, 0.5), rough=0.85),
    "C_wall_cap": dict(tex="concrete_wall_008", scale=0.5, base=(0.5, 0.47, 0.43), rough=0.85),
    "C_path": dict(tex="rectangular_paving", scale=0.667, base=(0.78, 0.72, 0.62), rough=0.8),
    # (also the world's gravel roads; the texture is baked by tools/make_world_textures.py)
    "C_world_gravel": dict(tex="world_gravel", scale=0.25, base=(0.36, 0.29, 0.21), rough=0.9),
    "C_world_dirt": dict(tex="world_dirt", scale=0.25, base=(0.33, 0.25, 0.17), rough=0.9),    # worn verges, yards
    "C_grass": dict(tex="leafy_grass", scale=0.5, base=(0.25, 0.5, 0.16), rough=0.95),
    "C_compound_wall": dict(tex="white_stucco", scale=0.333, base=(0.85, 0.8, 0.7), rough=0.9),
    # Villas: vertical timber boards, and tile sheets baked from assets/tiles. The wall
    # sheet is 8 x 2 upright 60 x 120 cm marble slabs (4.8 x 2.4 m), the floor sheet
    # 4 x 4 beige 60 x 60 cm tiles (2.4 x 2.4 m). The same beige tile, matt, clads the
    # modern villa's bay and paves terraces and balconies.
    "C_villa_timber": dict(tex="wood_floor", scale=1.0, base=(0.5, 0.33, 0.2), rough=0.55, tint=(1.15, 1.0, 0.85)),
    "C_villa_tile_wall": dict(tex="villa_tile_wall", scale=(1 / 4.8, 1 / 2.4), base=(0.93, 0.93, 0.93), rough=0.12),
    "C_villa_tile_floor": dict(tex="villa_tile_floor", scale=1 / 2.4, base=(0.84, 0.81, 0.75), rough=0.15),
    "C_villa_stone": dict(tex="villa_tile_floor", scale=1 / 2.4, base=(0.6, 0.56, 0.5), rough=0.55, matt=True,
                          tint=(0.74, 0.69, 0.61)),
    # Old cottage (maps baked by tools/make_cottage_textures.py). Boards lie along U, so
    # they run horizontally on walls; "rot" turns them to run along V (posts, deck, treads).
    "C_cottage_logs": dict(tex="cottage_logs", scale=1 / 1.44, base=(0.36, 0.32, 0.27), rough=0.85),
    "C_cottage_wood": dict(tex="cottage_wood", scale=1 / 1.44, base=(0.38, 0.33, 0.27), rough=0.85),
    "C_cottage_wood_v": dict(tex="cottage_wood", scale=1 / 1.44, rot=90.0, base=(0.38, 0.33, 0.27), rough=0.85),
    "C_cottage_lining": dict(tex="cottage_lining", scale=1.0, base=(0.7, 0.52, 0.3), rough=0.6,
                             maps={"rough": "wood_floor"}),
    "C_cottage_logs_v": dict(tex="cottage_logs", scale=1 / 1.44, rot=90.0, base=(0.36, 0.32, 0.27), rough=0.85),
    "C_cottage_lining_v": dict(tex="cottage_lining", scale=1.0, rot=90.0, base=(0.7, 0.52, 0.3), rough=0.6,
                               maps={"rough": "wood_floor"}),
}

# Peeling paint (core/paint.py): one material per surface, the colour and the peeling come
# from the mesh's "Paint" colour attribute. Maps baked by tools/make_cottage_textures.py
# (roof) and tools/make_cottage_paint_textures.py (siding: lap boards along U, so
# horizontal on walls; T&G planks turned upright by the 90 degree rotation).
PAINT_SPECS = {
    "C_cottage_roof_paint": dict(under="cottage_roof_diff.jpg", data="cottage_roof_paint.png",
                                 nor="cottage_roof_nor.jpg", rough="cottage_roof_rough.jpg", scale=0.5,
                                 chalk_mul=0.6, chalk_add=0.35, paint_rough=0.55, dirt_gain=1.15,
                                 zone=0.7, rust=True, base=(0.4, 0.11, 0.09)),
    "C_cottage_lap_paint": dict(under="cottage_lap_diff.jpg", data="cottage_lap_paint.png",
                                nor="cottage_lap_nor.jpg", rough="cottage_lap_rough.jpg", scale=1 / 1.44,
                                chalk_mul=0.55, chalk_add=0.4, paint_rough=0.68, zone=0.5, base=(0.4, 0.5, 0.42)),
    "C_cottage_planks_paint_v": dict(under="cottage_planks_diff.jpg", data="cottage_planks_paint.png",
                                     nor="cottage_planks_nor.jpg", rough="cottage_planks_rough.jpg",
                                     scale=1 / 1.44, rot=90.0, chalk_mul=0.55, chalk_add=0.4, paint_rough=0.68,
                                     zone=0.5, base=(0.4, 0.5, 0.42)),
}

# Paint colours (sRGB), picked from the reference photos. The painted cottage's siding:
COTTAGE_PAINTS = (
    ("CREAM", "Cream", "cream", (0.84, 0.78, 0.64)),
    ("GREEN", "Green", "green", (0.24, 0.44, 0.27)),
    ("TEAL", "Teal", "teal", (0.13, 0.52, 0.47)),
    ("BLUE", "Blue", "blue", (0.40, 0.54, 0.66)),
)

# The tile materials have no Mapping node: in the scene their UVs are scaled so
# one tile texture covers 0.6 m. The generator scales those faces' UVs to match.
UV_SCALE = {"C_bath_tile_floor": 1 / 0.6, "C_bath_tile_wall": 1 / 0.6}

FACADES = (
    ("CREAM", "Cream", "C_wall_cream"),
    ("WHITE", "White", "C_wall_white"),
    ("GREY", "Grey", "C_wall_grey"),
    ("PEACH", "Peach", "C_wall_peach"),
    ("SAGE", "Sage", "C_wall_sage"),
    ("BLUE", "Blue", "C_wall_blue"),
    ("BRICK", "Red Brick", "C_house_brick"),
)
COTTAGE_ROOFS = (               # corrugated sheet paint (sRGB)
    ("RED", "Red Corrugated", (0.34, 0.085, 0.075)),
    ("GREEN", "Green Corrugated", (0.13, 0.33, 0.2)),
    ("GREY", "Grey Corrugated", (0.52, 0.54, 0.55)),
)
ROOFS = (
    ("RED", "Red Clay Tiles", "C_roof_red"),
    ("DARK", "Dark Grey Tiles", "C_roof_dark"),
    ("TEAL", "Teal Tiles", "C_roof_teal"),
)
_RANDOM = ("RANDOM", "Random", "Picked from the house seed")
FACADE_ITEMS = [_RANDOM] + [(k, n, m) for k, n, m in FACADES]
ROOF_ITEMS = [_RANDOM] + [(k, n, m) for k, n, m in ROOFS]
_CUSTOM = ("CUSTOM", "Custom", "Any colour from the colour picker")
COTTAGE_ROOF_ITEMS = [_RANDOM] + [(k, n, f"{n} sheet") for k, n, _ in COTTAGE_ROOFS] + [_CUSTOM]
COTTAGE_PAINT_ITEMS = [_RANDOM] + [(k, n, f"Weathered {n.lower()} paint") for k, n, _, _ in COTTAGE_PAINTS] \
    + [_CUSTOM]
COTTAGE_SIDING_ITEMS = [_RANDOM, ("LAP", "Lap Boards", "Horizontal clapboard siding"),
                        ("PLANKS", "Upright Boards", "Vertical tongue-and-groove boards")]


def uv_scale(mat):
    return UV_SCALE.get(mat.name, 1.0) if mat else 1.0


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def _find_file(filename):
    """The open .blend's own textures/ folder first, then the addon's copy."""
    dirs = []
    if bpy.data.filepath:
        dirs.append(os.path.join(os.path.dirname(bpy.data.filepath), "textures"))
    dirs.append(TEX_DIR)
    for d in dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


def _relink(img):
    """Repoint an image whose file has gone missing to a copy we can find."""
    if img.packed_file or img.source != "FILE":
        return
    if os.path.exists(bpy.path.abspath(img.filepath)):
        return
    path = _find_file(os.path.basename(bpy.path.abspath(img.filepath)))
    if not path:
        return
    try:
        img.filepath = bpy.path.relpath(path) if bpy.data.filepath else path
    except ValueError:  # different drive: keep it absolute
        img.filepath = path
    img.reload()


def _image(filename, non_color):
    want = filename.lower()
    img = next((im for im in bpy.data.images if im.source == "FILE" and
                os.path.basename(bpy.path.abspath(im.filepath)).lower() == want), None)
    if img:
        _relink(img)
    else:
        path = _find_file(filename)
        if not path:
            return None
        img = bpy.data.images.load(path, check_existing=True)
    if non_color:
        img.colorspace_settings.name = "Non-Color"
    return img


# --------------------------------------------------------------------------
# Material builders
# --------------------------------------------------------------------------

def _sock(sockets, identifier):
    return next(s for s in sockets if s.identifier == identifier)


def _new(name, base, rough, diffuse=None):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = diffuse or (*base, 1.0)
    return mat, nt, bsdf


def _build_textured(name, r):
    mat, nt, bsdf = _new(name, r["base"], r["rough"])
    ext = r.get("ext", "jpg")

    vec = None
    if r.get("scale"):
        coord = nt.nodes.new("ShaderNodeTexCoord")
        coord.location = (-1000, 0)
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.location = (-800, 0)
        sx, sy = r["scale"] if isinstance(r["scale"], tuple) else (r["scale"], r["scale"])
        mapping.inputs["Scale"].default_value = (sx, sy, 1.0)
        if r.get("rot"):
            mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(r["rot"]))
        nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
        vec = mapping.outputs["Vector"]

    def tex(kind, non_color, y):
        img = _image(f"{r.get('maps', {}).get(kind, r['tex'])}_{kind}.{ext}", non_color)
        if img is None:
            return None
        node = nt.nodes.new("ShaderNodeTexImage")
        node.image = img
        node.location = (-500, y)
        if vec:
            nt.links.new(vec, node.inputs["Vector"])
        return node

    diff, nor = tex("diff", False, 300), tex("nor", True, -300)
    rough = None if r.get("matt") else tex("rough", True, 0)

    if diff:
        col = diff.outputs["Color"]
        if r.get("tint"):
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.location = (-150, 300)
            _sock(mix.inputs, "Factor_Float").default_value = 1.0
            _sock(mix.inputs, "B_Color").default_value = (*r["tint"], 1.0)
            nt.links.new(col, _sock(mix.inputs, "A_Color"))
            col = _sock(mix.outputs, "Result_Color")
        if r.get("hsv"):
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.location = (-150, 300)
            h, s, v = r["hsv"]
            hsv.inputs["Hue"].default_value = h
            hsv.inputs["Saturation"].default_value = s
            hsv.inputs["Value"].default_value = v
            nt.links.new(col, hsv.inputs["Color"])
            col = hsv.outputs["Color"]
        nt.links.new(col, bsdf.inputs["Base Color"])
    if rough:
        nt.links.new(rough.outputs["Color"], bsdf.inputs["Roughness"])
    if nor:
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.location = (-150, -300)
        nt.links.new(nor.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _build_glass(name):
    mat, nt, bsdf = _new(name, (0.85, 0.92, 0.95), 0.02, diffuse=(0.6, 0.75, 0.85, 0.25))
    for key in ("Transmission Weight", "Transmission"):  # 4.x / 3.x
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = 1.0
            break
    return mat


def _build_painted_trim(name):
    """White satin paint with a faint brush-noise bump (window frames, soffits)."""
    mat, nt, bsdf = _new(name, (0.92, 0.92, 0.9), 0.35)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-600, 0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-400, 0)
    noise.inputs["Scale"].default_value = 60.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-150, -200)
    bump.inputs["Strength"].default_value = 0.03
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _build_smooth(name, base, rough=0.9, grain=0.04):
    """Fresh, even paint or render: one clean colour with a very fine grain, no stains."""
    mat, nt, bsdf = _new(name, base, rough)
    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-600, 0)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.location = (-400, 0)
    noise.inputs["Scale"].default_value = 350.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.location = (-150, -200)
    bump.inputs["Strength"].default_value = grain
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _build_smoked_glass(name):
    """The user's stair glass: near-black, 30 % opaque, matt."""
    mat, nt, bsdf = _new(name, (0.028, 0.028, 0.028), 1.0, diffuse=(0.03, 0.03, 0.03, 0.3))
    bsdf.inputs["Alpha"].default_value = 0.3
    if hasattr(mat, "surface_render_method"):      # 4.2+
        mat.surface_render_method = "DITHERED"
    else:
        mat.blend_method = "HASHED"
    return mat


def _build_metal(name, base, rough, metal):
    mat, nt, bsdf = _new(name, base, rough)
    bsdf.inputs["Metallic"].default_value = metal
    return mat


_SPECIAL = {
    "C_window_glass": _build_glass,
    "C_window_frame": _build_painted_trim,
    "C_gutter": lambda n: _build_metal(n, (0.85, 0.85, 0.83), 0.35, 0.3),
    "C_line_white": lambda n: _new(n, (0.9, 0.9, 0.88), 0.6)[0],
    "C_water": lambda n: _new(n, (0.1, 0.35, 0.55), 0.05)[0],
    "C_hedge_leaves": lambda n: _new(n, (0.04, 0.15, 0.03), 0.8)[0],
    "C_villa_trim": lambda n: _build_metal(n, (0.045, 0.05, 0.055), 0.45, 0.2),   # anthracite frames, posts, fascias
    "C_villa_plaster": lambda n: _build_smooth(n, (0.94, 0.94, 0.93), 0.9, 0.02),  # clean white walls and ceilings
    "C_villa_render": lambda n: _build_smooth(n, (0.93, 0.93, 0.91), 0.92, 0.08),  # fresh white facade
    "C_villa_render_grey": lambda n: _build_smooth(n, (0.36, 0.37, 0.39), 0.92, 0.08),
    "C_villa_stair_glass": _build_smoked_glass,
    "C_villa_stair_post": lambda n: _new(n, (0.017, 0.017, 0.017), 0.5)[0],
    "C_cottage_trim": lambda n: _build_smooth(n, (0.78, 0.76, 0.7), 0.7, 0.06),     # old white paint
    "C_cottage_pile": lambda n: _build_metal(n, (0.09, 0.07, 0.06), 0.75, 0.5),      # rusty steel piles
}


def ensure(name):
    """The scene material `name`: reuse the file's own copy, else build it."""
    mat = bpy.data.materials.get(name)
    if mat and name in PAINT_SPECS:
        from .paint import VERSION, peel_material
        if mat.get("paint_version") != VERSION:      # an older peeling-paint setup: rebuild in place
            return peel_material(name, PAINT_SPECS[name])
    if mat:
        if mat.node_tree:  # repair texture links that point at a moved folder
            for node in mat.node_tree.nodes:
                if node.bl_idname == "ShaderNodeTexImage" and node.image:
                    _relink(node.image)
        return mat
    if name in RECIPES:
        return _build_textured(name, RECIPES[name])
    if name in PAINT_SPECS:
        from .paint import peel_material
        return peel_material(name, PAINT_SPECS[name])
    return _SPECIAL[name](name)


def ensure_any(name):
    """Like ensure(), with a plain grey stand-in for names we have no recipe for."""
    if bpy.data.materials.get(name) or name in RECIPES or name in _SPECIAL or name in PAINT_SPECS:
        return ensure(name)
    return _new(name, (0.5, 0.5, 0.5), 0.8)[0]


# --------------------------------------------------------------------------
# Palette for one house
# --------------------------------------------------------------------------

def house_palette(facade="RANDOM", roof="RANDOM", seed=0, bath_tiles=True):
    """{role: material} for one house. 'RANDOM' choices follow the seed."""
    rng = random.Random(seed * 7919 + 101)
    rand_facade = rng.choice(FACADES)[2]   # always draw both, so fixing one
    rand_roof = rng.choice(ROOFS)[2]       # choice doesn't reshuffle the other
    facade_mat = rand_facade if facade == "RANDOM" else dict((k, m) for k, _, m in FACADES)[facade]
    roof_mat = rand_roof if roof == "RANDOM" else dict((k, m) for k, _, m in ROOFS)[roof]

    plaster = ensure("C_interior_plaster")
    floor = ensure("C_floor_wood")
    return {
        "wall_in": plaster,
        "wall_out": ensure(facade_mat),
        "wall_wet": ensure("C_bath_tile_wall") if bath_tiles else plaster,
        "floor": floor,
        "floor_wet": ensure("C_bath_tile_floor") if bath_tiles else floor,
        "ceiling": ensure("C_ceiling"),
        "roof": ensure(roof_mat),
        "roof_flat": ensure("C_roof_flat"),
        "soffit": ensure("C_window_frame"),
        "door": ensure("C_door_wood"),
        "glass": ensure("C_window_glass"),
        "stair": ensure("C_stair_wood"),
        "rail": ensure("C_gutter"),
    }


def villa_palette(style, facade="RANDOM", roof="RANDOM", seed=0, bath_tiles=True):
    """A villa in new condition: clean white plaster inside, marble-tiled bathrooms
    (60 x 120 slabs on the walls, 60 x 60 on the floor), fresh render outside.
    'RANDOM' means the style's own look: white render with dark roof tiles, stone
    tiles (modern) or timber (gable) on the front bay."""
    m = house_palette("WHITE" if facade == "RANDOM" else facade, "DARK" if roof == "RANDOM" else roof, seed, bath_tiles)
    plaster = ensure("C_villa_plaster")
    m.update({
        "wall_in": plaster,
        "ceiling": plaster,
        "wall_wet": ensure("C_villa_tile_wall") if bath_tiles else plaster,
        "floor_wet": ensure("C_villa_tile_floor") if bath_tiles else m["floor"],
        "accent": ensure("C_villa_stone" if style == "MODERN" else "C_villa_timber"),
        "recess": ensure("C_villa_render_grey"),
        "deck": ensure("C_villa_stone"),
        "trim": ensure("C_villa_trim"),
        "soffit_wood": ensure("C_villa_timber"),
        "paving": ensure("C_sidewalk"),
        "drive": ensure("C_path"),
        "water": ensure("C_water"),
        "stair_glass": ensure("C_villa_stair_glass"),
        "stair_post": ensure("C_villa_stair_post"),
    })
    if facade == "RANDOM":
        m["wall_out"] = ensure("C_villa_render")
    return m


def roof_paint_colour(roof="RANDOM", seed=0, custom=(0.34, 0.085, 0.075)):
    """The corrugated roof's paint colour (sRGB): a named one, the custom one, or picked by the seed."""
    rand = random.Random(seed * 7919 + 211).choice(COTTAGE_ROOFS)[2]
    if roof == "RANDOM":
        return rand
    if roof == "CUSTOM":
        return tuple(custom)
    return dict((k, c) for k, _, c in COTTAGE_ROOFS)[roof]


def siding_paint_colour(paint="RANDOM", seed=0, custom=(0.24, 0.44, 0.27)):
    """The painted cottage's siding colour (sRGB), like roof_paint_colour."""
    rand = random.Random(seed * 4513 + 97).choice(COTTAGE_PAINTS)[3]
    if paint == "RANDOM":
        return rand
    if paint == "CUSTOM":
        return tuple(custom)
    return next(c for k, _, _, c in COTTAGE_PAINTS if k == paint)


def cottage_palette(roof="RANDOM", seed=0, bath_tiles=True):
    """An old timber cottage: weathered siding outside, aged pine lining on the walls, ceilings
    and floors inside, plank doors of the same wood (boards upright), a corrugated roof whose
    paint colour and peeling come from the mesh (see roof_paint_colour, core/paint.py)."""
    lining = floor = ensure("C_cottage_lining")
    return {
        "wall_in": lining,
        "wall_out": ensure("C_cottage_logs"),
        "wall_wet": ensure("C_bath_tile_wall") if bath_tiles else lining,
        "floor": floor,
        "floor_wet": floor,
        "ceiling": lining,
        "roof": ensure("C_cottage_roof_paint"),
        "roof_flat": ensure("C_roof_flat"),
        "soffit": lining,
        "soffit_out": ensure("C_cottage_wood"),
        "door": ensure("C_cottage_logs_v"),            # the front door: the siding, boards upright
        "door_in": ensure("C_cottage_lining_v"),       # inside doors: the lining, boards upright
        "glass": ensure("C_window_glass"),
        "stair": lining,
        "stair_v": ensure("C_cottage_lining_v"),
        "rail": ensure("C_cottage_wood"),
        "trim": ensure("C_cottage_trim"),
        "timber": ensure("C_cottage_wood"),
        "post": ensure("C_cottage_wood_v"),
        "pile": ensure("C_cottage_pile"),
        "chimney": ensure("C_house_brick"),
        "chimney_cap": ensure("C_plinth"),
    }


def painted_cottage_palette(roof="RANDOM", paint="RANDOM", siding="RANDOM", seed=0, bath_tiles=True):
    """The painted cottage: the old cottage's inside, weathered painted boards outside
    (lap siding or upright boards; upright boards always clad the gables), white trim,
    a brick plinth. 'RANDOM' picks from the seed. The paint colour and peeling come from
    the mesh (siding_paint_colour, core/paint.py), so `paint` only matters there."""
    m = cottage_palette(roof, seed, bath_tiles)
    rng = random.Random(seed * 4513 + 97)
    rng.choice(COTTAGE_PAINTS)                  # (the colour pick: keeps the siding pick below as it was)
    lap = rng.random() < 0.5 if siding == "RANDOM" else siding == "LAP"
    planks = ensure("C_cottage_planks_paint_v")
    trim = ensure("C_cottage_trim")
    m.update({
        "wall_out": ensure("C_cottage_lap_paint") if lap else planks,
        "wall_gable": planks,
        "door": planks,
        "corner": trim,
        "veranda_post": trim,
        "baluster": trim,
        "veranda_rail": trim,
        "bargeboard": trim,
        "plinth": ensure("C_house_brick"),
        "plinth_cap": ensure("C_plinth"),
    })
    return m
