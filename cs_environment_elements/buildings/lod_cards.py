"""Fence cards for LOD2 and LOD3: each run of boards, slats or a closed leaf becomes one
quad (two, back to back), so a fence costs a few triangles per run instead of hundreds.

The fence builders record a card per run (fence_build.FenceBuilder.cards) and the fence
root keeps them as JSON in root["lod_cards"]:
    [x0, y0, z0, x1, y1, z1, height, material name, kind, pitch]
p0 / p1 are the bottom corners in the root's space, the card rises `height` straight up.

kind:
  "upright"  old board fence: fence.png turned on its side, so its 12 planks (alpha gaps
             between them) stand up side by side, one per `pitch` metres along the run
  "level"    timber slats lying level: the planks as they are, one per `pitch` up the card
  "metric"   anything else (black steel slats): the material in metres, no cut-out
"""

import json

import bpy
from mathutils import Vector

UP = Vector((0.0, 0.0, 1.0))
GAP = 0.003             # the two faces of a card sit this far apart (no flicker in the viewport)
# fence.png: 12 planks between rows 2 and 1949 of 1966 (fence_geom._STRIPS_PX) -> UV per plank
PLANK_V = (1949 - 2) / 12 / 1966
PLANK_U0, PLANK_U1 = 0.08, 0.94     # the solid stretch of the planks' length


def record(cards, p0, p1, height, mat_index, kind, pitch=1.0):
    cards.append([p0.x, p0.y, p0.z, p1.x, p1.y, p1.z, height, mat_index, kind, pitch])


def store(root, cards, mats):
    """Save the builder's cards on the fence root, material indices turned into names."""
    out = [c[:7] + [mats[c[7]].name] + c[8:] for c in cards]
    root["lod_cards"] = json.dumps(out)


def load(root):
    try:
        return json.loads(root.get("lod_cards", "[]"))
    except ValueError:
        return []


def card_material(name, kind):
    """The plank materials with their alpha as a cut-out (and tiling), for card kinds that need it."""
    base = bpy.data.materials.get(name)
    if base is None or kind == "metric":
        return base
    cname = f"{name}_card"
    mat = bpy.data.materials.get(cname)
    if mat:
        return mat
    mat = base.copy()
    mat.name = cname
    nt = mat.node_tree
    tex = nt.nodes.get("Wood") or next((n for n in nt.nodes if n.type == "TEX_IMAGE"), None)
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if tex is None or bsdf is None:
        return mat
    for n in nt.nodes:                          # the planks (and the paint mask) repeat along a card
        if n.type == "TEX_IMAGE":
            n.extension = "REPEAT"
    nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    if hasattr(mat, "surface_render_method"):       # 4.2+
        mat.surface_render_method = "DITHERED"
    else:
        mat.blend_method = "CLIP"
    return mat


def _uv(kind, s, h, pitch):
    """UV at distance s along the run, height h up the card."""
    if kind == "upright":
        return PLANK_U0 + (PLANK_U1 - PLANK_U0) * h, s / pitch * PLANK_V
    if kind == "level":
        return s / 3.0, h / pitch * PLANK_V
    return s, h


def add(soup, cards):
    """Append the cards' faces to an lod.Soup."""
    for x0, y0, z0, x1, y1, z1, height, name, kind, pitch in cards:
        mat = card_material(name, kind)
        a, b = Vector((x0, y0, z0)), Vector((x1, y1, z1))
        run = (b - a).xy.to_3d()
        L = run.length
        if L < 1e-3 or height <= 0.0:
            continue
        n = run.normalized().cross(UP)
        hu = 1.0 if kind == "upright" else height          # "upright" maps h as a 0..1 fraction
        quad = [(a, 0.0, 0.0), (b, L, 0.0), (b + UP * height, L, hu), (a + UP * height, 0.0, hu)]
        for side in (1.0, -1.0):
            ring = quad if side > 0 else list(reversed(quad))
            pts = [p + n * (GAP / 2 * side) for p, _, _ in ring]
            uvs = [_uv(kind, s, h, pitch) for _, s, h in ring]
            soup.add_face(pts, uvs, mat)
