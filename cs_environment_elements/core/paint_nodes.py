"""Node helpers for the peeling-paint materials (core/paint.py: cottages, buildings/fence_paint.py: old
fences), and the one piece of maths they share: how long the paint lasts at each spot.

    last = smoothstep(D_LO, D_HI, W_PATCH * patches + W_FLAKE * flakes + W_BOARD * board)  -> 0.04 .. 0.96

  patches  where the weather got at it: wear_zones.png read twice, at PATCH_A metres and turned PATCH_ROT
           at PATCH_B metres (sizes that never line up, so the pattern does not repeat); decides most of
           where the paint is gone, in big soft areas
  flakes   paint_flakes.png over FLAKE_SIZE metres (tools/make_paint_flakes.py): cracked flakes, long along
           the grain on wood (R), round on metal (B); breaks the edge of a peeled area into flakes
  board    the surface's own map (siding / roof _paint R, the fence's peel mask): board edges, board age

D_LO / D_HI make `last` about uniform, so peeling 0.4 takes off about 40 %. G of paint_flakes is the
cracks: paint close to flaking off shows them (crack()).
The Godot shaders (core/assets/godot/peel_paint.gdshader, core/assets/old-fence/godot/) do the same.
"""

import math

PATCH_TEX = "wear_zones.png"
FLAKE_TEX = "paint_flakes.png"
PATCH_A, PATCH_B, PATCH_ROT, PATCH_MIX = 2.7, 6.3, 63.0, 0.6
FLAKE_SIZE = 3.0
W_PATCH, W_FLAKE, W_BOARD = 0.72, 0.21, 0.07
W_BOARD_FENCE = 0.025       # fences: each plank of the mask has its own age; more and whole boards flip
D_LO, D_HI = 0.15, 0.85
CRACK_REACH, CRACK_DARK = 0.2, 0.4


class Graph:
    """Small helpers for building a node tree in code."""

    def __init__(self, nt):
        self.nt = nt
        self.link = nt.links.new

    def node(self, kind, x, y, **props):
        n = self.nt.nodes.new(kind)
        n.location = (x, y)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def _set(self, sock, v):
        if isinstance(v, (int, float, tuple)):
            sock.default_value = v
        else:
            self.link(v, sock)

    def math(self, op, x, y, *inputs):
        n = self.node("ShaderNodeMath", x, y, operation=op)
        for i, v in enumerate(inputs):
            self._set(n.inputs[i], v)
        return n.outputs[0]

    def mix(self, data_type, blend, x, y, fac, a, b):
        m = self.node("ShaderNodeMix", x, y, data_type=data_type, blend_type=blend)
        suffix = "Color" if data_type == "RGBA" else "Float"
        sock = {s.identifier: s for s in m.inputs}
        for key, v in (("Factor_Float", fac), (f"A_{suffix}", a), (f"B_{suffix}", b)):
            self._set(sock[key], v)
        return next(s for s in m.outputs if s.identifier == f"Result_{suffix}")

    def smooth(self, x, y, value, lo, hi, to_lo=0.0, to_hi=1.0, label=""):
        r = self.node("ShaderNodeMapRange", x, y, interpolation_type="SMOOTHSTEP", label=label)
        self._set(r.inputs["Value"], value)
        self._set(r.inputs["From Min"], lo)
        self._set(r.inputs["From Max"], hi)
        r.inputs["To Min"].default_value, r.inputs["To Max"].default_value = to_lo, to_hi
        return r.outputs["Result"]

    def mapping(self, x, y, vector, scale=1.0, rot=0.0, loc=None, label=""):
        m = self.node("ShaderNodeMapping", x, y, label=label)
        self.link(vector, m.inputs["Vector"])
        m.inputs["Scale"].default_value = (scale, scale, 1.0)
        if rot:
            m.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(rot))
        if loc is not None:
            c = self.node("ShaderNodeCombineXYZ", x - 200, y - 100)
            self._set(c.inputs["X"], loc[0])
            self._set(c.inputs["Y"], loc[1])
            self.link(c.outputs["Vector"], m.inputs["Location"])
        return m.outputs["Vector"]

    def image(self, x, y, img, vector, label):
        n = self.node("ShaderNodeTexImage", x, y, label=label, name=label)
        n.image = img
        self.link(vector, n.inputs["Vector"])
        return n


def lasting(g, image, uv_m, flake_uv, board, rnd=None, metal=False, w_board=W_BOARD, x=-1700, y=-1300):
    """How long the paint lasts at each spot (0.04 .. 0.96) and the crack mask (1 none, 0 crack).
    uv_m: the surface in metres (patches); flake_uv: in flake tiles, U along the grain; board: the
    surface's own wear value (weight w_board); rnd: three random values per object (or None); image(name) -> bpy image."""
    off = (lambda a, b: (rnd[a], rnd[b])) if rnd is not None else (lambda a, b: None)
    za = g.image(x + 400, y, image(PATCH_TEX), g.mapping(x + 200, y, uv_m, 1.0 / PATCH_A, loc=off(1, 2),
                                                          label="Weather patches"), "PatchesA")
    zb = g.image(x + 400, y - 300, image(PATCH_TEX),
                 g.mapping(x + 200, y - 300, uv_m, 1.0 / PATCH_B, PATCH_ROT, loc=off(2, 0),
                           label="Weather patches, turned"), "PatchesB")
    patches = g.mix("FLOAT", "MIX", x + 700, y - 100, 1.0 - PATCH_MIX, za.outputs["Color"], zb.outputs["Color"])
    fl = g.image(x + 400, y - 600, image(FLAKE_TEX), flake_uv, "Flakes")
    sep = g.node("ShaderNodeSeparateColor", x + 650, y - 600)
    g.link(fl.outputs["Color"], sep.inputs["Color"])
    flakes = sep.outputs[2 if metal else 0]
    d = g.math("MULTIPLY", x + 900, y - 100, patches, W_PATCH)
    d = g.math("MULTIPLY_ADD", x + 1050, y - 200, flakes, W_FLAKE, d)
    d = g.math("MULTIPLY_ADD", x + 1200, y - 300, board, w_board, d)
    d = g.math("ADD", x + 1300, y - 300, d, (W_BOARD - w_board) * 0.5)     # same middle as W_BOARD
    return g.smooth(x + 1400, y - 300, d, D_LO, D_HI, 0.04, 0.96, "Paint lasts"), sep.outputs[1]


def crack(g, last, peel, cracks, x=-200, y=-650):
    """Darkening of the paint by its cracks, strongest just before it flakes: 1 - CRACK_DARK * (1 - G) * near."""
    near = g.smooth(x, y, g.math("SUBTRACT", x - 150, y, last, peel), 0.0, CRACK_REACH, 1.0, 0.0, "Near the edge")
    amt = g.math("MULTIPLY", x + 200, y, near, g.math("SUBTRACT", x + 50, y - 120, 1.0, cracks))
    return g.math("MULTIPLY_ADD", x + 350, y, amt, -CRACK_DARK, 1.0)
