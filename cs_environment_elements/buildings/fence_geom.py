"""Low-level fence geometry: oriented boxes whose UVs land on one real plank of
assets/old-fence/fence.png (12 weathered planks stacked, transparent gaps between).

Every board, rail and post picks a plank strip and a random stretch along it, so no
two boards look the same and no UV ever crosses a gap or a ragged plank end.
"""

import os

import bpy
from mathutils import Vector

TEX_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "core", "assets", "old-fence", "fence.png")
MAT_WOOD = "C_fence_old_wood"
MAT_METAL = "C_fence_iron"

_IMG_W, _IMG_H = 2584, 1966
# Each plank: (top row, bottom row, first solid column, last solid column) in pixels,
# measured from the image's alpha (rows counted from the top of the picture).
_STRIPS_PX = (
    (2, 151, 167, 2579), (172, 318, 12, 2465), (336, 479, 8, 2567), (497, 636, 4, 2578),
    (655, 800, 22, 2444), (821, 965, 16, 2577), (987, 1136, 244, 2574), (1153, 1298, 10, 2340),
    (1319, 1460, 10, 2578), (1483, 1623, 135, 2576), (1639, 1782, 13, 2397), (1809, 1949, 184, 2507),
)
_INSET_Y, _INSET_X = 9, 20


def _strip_uv(p):
    y0, y1, x0, x1 = p
    v_top = 1.0 - (y0 + _INSET_Y) / _IMG_H
    v_bot = 1.0 - (y1 - _INSET_Y) / _IMG_H
    return (x0 + _INSET_X) / _IMG_W, (x1 - _INSET_X) / _IMG_W, v_bot, v_top


STRIPS = [_strip_uv(p) for p in _STRIPS_PX]          # (u0, u1, v0, v1) in UV space


class Parts:
    """Collects boxes (verts, quads, per-loop UVs, material index) into one mesh."""

    def __init__(self, rng):
        self.rng = rng
        self.verts, self.faces, self.uvs, self.mats = [], [], [], []

    def _quad(self, corners, uvs, mat):
        base = len(self.verts)
        self.verts += [tuple(c) for c in corners]
        self.faces.append(list(range(base, base + len(corners))))
        self.uvs.append(uvs)
        self.mats.append(mat)

    def poly(self, corners, mat=0):
        """One face with metre UVs (like the house walls: U along the face, V up it)."""
        self._quad(corners, [metric_uv(c, _normal(corners)) for c in corners], mat)

    def prism(self, ring, z_lo, z_hi, mat=0):
        """A solid standing on a counter-clockwise ring of xy points; bottom and top heights
        per point (so a plinth can follow the slope underneath and stay level on top)."""
        n = len(ring)
        lo = [Vector((p[0], p[1], z_lo[i])) for i, p in enumerate(ring)]
        hi = [Vector((p[0], p[1], z_hi[i])) for i, p in enumerate(ring)]
        self.poly(hi, mat)
        self.poly(list(reversed(lo)), mat)
        for i in range(n):
            j = (i + 1) % n
            self.poly([lo[i], lo[j], hi[j], hi[i]], mat)

    def raw(self, verts, faces, mat=0):
        """Arbitrary faces (e.g. letters from a font), metre UVs."""
        for f in faces:
            self.poly([Vector(verts[i]) for i in f], mat)

    def box(self, center, a, b, L, W, T, mat=0, uv="plank"):
        """Box at `center`; grain (texture length) along unit `a`, width `W` along unit `b`,
        thickness `T` along a x b. Sizes are full lengths. uv="metric" maps it in metres
        (concrete, paint) instead of onto a plank."""
        a, b = Vector(a).normalized(), Vector(b).normalized()
        c = a.cross(b).normalized()
        b = c.cross(a)                                    # make the frame exactly orthogonal
        center = Vector(center)
        axes, half = (a, b, c), (L / 2, W / 2, T / 2)
        base = len(self.verts)
        signs = [(i, j, k) for i in (-1, 1) for j in (-1, 1) for k in (-1, 1)]
        for s in signs:
            self.verts.append(tuple(center + a * s[0] * half[0] + b * s[1] * half[1] + c * s[2] * half[2]))
        idx = {s: base + n for n, s in enumerate(signs)}

        u0, u1, v0, v1 = self.rng.choice(STRIPS)
        span = (v1 - v0) * _IMG_H / _IMG_W / max(W, 1e-4)  # U units per metre at true aspect
        du = min(L * span, u1 - u0)
        us = self.rng.uniform(u0, u1 - du)
        if self.rng.random() < 0.5:                       # either way up
            v0, v1 = v1, v0

        def uv_of(s, axis):
            ta, tb, tc = (s[0] + 1) / 2, (s[1] + 1) / 2, (s[2] + 1) / 2
            if axis == 2:                                  # broad face: whole plank width
                return us + ta * du, v0 + tb * (v1 - v0)
            if axis == 1:                                  # edge: a thin sliver of the plank
                return us + ta * du, v0 + tc * (v1 - v0) * min(T / max(W, 1e-4), 1.0)
            return us + tb * du * W / max(L, 1e-4), v0 + tc * (v1 - v0) * 0.3   # end grain

        for axis in range(3):
            p, q = (axis + 1) % 3, (axis + 2) % 3
            for sign in (1, -1):
                ring = []
                for sp, sq in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                    s = [0, 0, 0]
                    s[axis], s[p], s[q] = sign, sp, sq
                    ring.append(tuple(s))
                if sign < 0:
                    ring.reverse()
                self.faces.append([idx[s] for s in ring])
                if uv == "metric":
                    nrm = axes[axis] * sign
                    self.uvs.append([metric_uv(Vector(self.verts[idx[s]]), nrm) for s in ring])
                else:
                    self.uvs.append([uv_of(s, axis) for s in ring])
                self.mats.append(mat)

    def upright(self, base, along, width, thick, height, mat=0, uv="plank"):
        """A vertical board/post standing on `base` (bottom centre), face along `along`."""
        up = Vector((0, 0, 1))
        self.box(Vector(base) + up * height / 2, up, along, height, width, thick, mat, uv)

    def beam(self, p0, p1, normal, depth, thick, mat=0, uv="plank"):
        """A rail from p0 to p1 (centre line), `depth` tall, `thick` along `normal`."""
        p0, p1 = Vector(p0), Vector(p1)
        a = (p1 - p0)
        L = a.length
        if L < 1e-4:
            return
        a /= L
        n = Vector(normal).normalized()
        b = n.cross(a)                                    # roughly up, so a x b = n
        self.box((p0 + p1) / 2, a, b, L, depth, thick, mat, uv)

    def mesh(self, name):
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.verts, [], self.faces)
        uv = me.uv_layers.new(name="UVMap")
        li = 0
        for face_uvs in self.uvs:
            for co in face_uvs:
                uv.data[li].uv = co
                li += 1
        for poly, m in zip(me.polygons, self.mats):
            poly.material_index = m
        me.update()
        return me


def _normal(corners):
    n = Vector((0.0, 0.0, 0.0))
    for i, c in enumerate(corners):                        # Newell's method
        d = corners[(i + 1) % len(corners)]
        n += Vector(((c.y - d.y) * (c.z + d.z), (c.z - d.z) * (c.x + d.x), (c.x - d.x) * (c.y + d.y)))
    return n.normalized() if n.length > 1e-9 else Vector((0, 0, 1))


def metric_uv(p, n):
    """1 UV unit = 1 m on the face's own plane (same rule as the house walls)."""
    if abs(n.z) > 0.999:
        return p.x, p.y
    t = Vector((0, 0, 1)).cross(n).normalized()
    return p.dot(t), p.dot(n.cross(t))


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

MAT_CEDAR = "C_fence_cedar"


def wood_material(name=MAT_WOOD):
    """The plank sheet as a material; C_fence_cedar is the same planks oiled to a warm
    red-brown (fresh modern slats), C_fence_old_wood the weathered silver-grey."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (500, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (200, 0)
    bsdf.inputs["Roughness"].default_value = 0.88
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.diffuse_color = (0.42, 0.37, 0.31, 1.0)
    img = bpy.data.images.load(TEX_PATH, check_existing=True) if os.path.exists(TEX_PATH) else None
    if img is None:
        bsdf.inputs["Base Color"].default_value = (0.42, 0.37, 0.31, 1.0)
        return mat
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.extension = "EXTEND"
    tex.location = (-400, 0)
    col = tex.outputs["Color"]
    if name == MAT_CEDAR:
        hsv = nt.nodes.new("ShaderNodeHueSaturation")
        hsv.location = (-150, 150)
        hsv.inputs["Saturation"].default_value = 0.35       # drop the grey, keep the grain
        nt.links.new(col, hsv.inputs["Color"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
        mix.location = (0, 150)
        sock = lambda socks, ident: next(x for x in socks if x.identifier == ident)   # noqa: E731
        sock(mix.inputs, "Factor_Float").default_value = 1.0
        sock(mix.inputs, "B_Color").default_value = (0.95, 0.55, 0.32, 1.0)      # oiled cedar
        nt.links.new(hsv.outputs["Color"], sock(mix.inputs, "A_Color"))
        col = sock(mix.outputs, "Result_Color")
        bsdf.inputs["Roughness"].default_value = 0.6
        mat.diffuse_color = (0.45, 0.25, 0.14, 1.0)
    nt.links.new(col, bsdf.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")             # cracks and grain read as relief
    bump.location = (-50, -300)
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.003
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def metal_material():
    mat = bpy.data.materials.get(MAT_METAL)
    if mat:
        return mat
    mat = bpy.data.materials.new(MAT_METAL)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.07, 0.055, 0.045, 1.0)   # old black iron, a bit rusty
    bsdf.inputs["Roughness"].default_value = 0.7
    bsdf.inputs["Metallic"].default_value = 0.6
    mat.diffuse_color = (0.07, 0.055, 0.045, 1.0)
    return mat
