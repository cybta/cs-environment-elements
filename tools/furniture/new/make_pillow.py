"""Realistic bed pillow for the home bed (HomeFitting._dress_bed):

    blender --background --python "ref/3D Models/furniture/pillow/make_pillow.py"

About 0.60 x 0.38 m in plan, ~0.12 m high, lowest point on z = 0. Two sewn cotton panels: a plump,
slightly dented top, a flatter bottom (it rests on the mattress), a flat stitched flange all round
(the typical pillow seam), pointed corners with soft creases running in from them. Woven-percale
textures with a normal map. Saved as pillow.blend beside this script (textures/ next to it) and
exported to data/models/bedding/pillow.glb.
"""
import math
import pathlib
import sys

import bmesh
import bpy
from mathutils import Vector, noise

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "mattress"))
import fabric  # noqa: E402

OUT = HERE.parents[3] / "data" / "models" / "bedding"
A, B = 0.30, 0.19         # half sizes of the plump body
FL = 0.016                # flange width
TILE = 0.10
NX, NY = 110, 70


def graded(n, half):
    """n+1 positions across -half..half, denser toward the ends where the surface turns."""
    return [half * math.sin(math.pi / 2 * (2 * i / n - 1)) for i in range(n + 1)]


def height(x, y, top):
    """Surface height above the seam plane at (x, y); 0 at/after the seam."""
    u, v = abs(x) / A, abs(y) / B
    if u >= 1 or v >= 1:
        return 0.0
    fx, fy = (1 - u ** 2.2) ** 0.5, (1 - v ** 2.2) ** 0.5
    body = fx * fy
    corner = (u * v) ** 1.2
    z = 0.082 * body ** 0.9 * (1 - 0.4 * corner)
    if top:
        # a shallow dent where a head rested, off-centre like a real used pillow
        z -= 0.014 * math.exp(-(((x + 0.03) / 0.16) ** 2 + ((y - 0.01) / 0.10) ** 2))
    else:
        z *= 0.5   # the underside is flatter
    # soft creases running in from each corner, and fine fabric wrinkles
    cr = Vector((math.copysign(A, x), math.copysign(B, y), 0)) - Vector((x, y, 0))
    ang = math.atan2(cr.y, cr.x)
    z += 0.0035 * math.sin(ang * 9 + (3 if x * y > 0 else 0)) * corner * (1 if top else 0.6)
    z += 0.0018 * noise.noise(Vector((x * 14, y * 14, 5.0 if top else 9.0))) * (1 - body ** 2)
    return max(z, 0.0)


def thickness(x, y):
    """The flange is two thin layers; thickness fades to nothing at its outer edge."""
    ox = max(0.0, abs(x) - A) / FL
    oy = max(0.0, abs(y) - B) / FL
    o = max(ox, oy)
    return 0.0022 * (1 - min(1.0, o) ** 1.5)


def build():
    xs = [(-(A + FL) if i == 0 else (A + FL) if i == NX else 0) for i in range(NX + 1)]
    gx = graded(NX, A)
    gy = graded(NY, B)
    xs = [-(A + FL)] + gx[1:-1] + [A + FL]
    ys = [-(B + FL)] + gy[1:-1] + [B + FL]
    # add a couple of columns/rows inside the flange so it keeps its flat shape
    xs = sorted(set(xs + [-A - FL * 0.5, -A - 0.001, A + 0.001, A + FL * 0.5]))
    ys = sorted(set(ys + [-B - FL * 0.5, -B - 0.001, B + 0.001, B + FL * 0.5]))
    bm = bmesh.new()
    grids = {}
    for top in (True, False):
        g = []
        for x in xs:
            row = []
            for y in ys:
                z = height(x, y, top) + thickness(x, y)
                row.append(bm.verts.new((x, y, z if top else -z)))
            g.append(row)
        grids[top] = g
    # the two panels share the outer edge
    for i in range(len(xs)):
        for j in range(len(ys)):
            if i in (0, len(xs) - 1) or j in (0, len(ys) - 1):
                bm.verts.remove(grids[False][i][j])
                grids[False][i][j] = grids[True][i][j]
    for top in (True, False):
        g = grids[top]
        for i in range(len(xs) - 1):
            for j in range(len(ys) - 1):
                vs = [g[i][j], g[i + 1][j], g[i + 1][j + 1], g[i][j + 1]]
                if not top:
                    vs.reverse()
                try:
                    bm.faces.new(vs)
                except ValueError:
                    pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    uv = bm.loops.layers.uv.verify()
    col = bm.loops.layers.color.new("Col")
    for f in bm.faces:
        f.smooth = True
        for lp in f.loops:
            p = lp.vert.co
            lp[uv].uv = (p.x / TILE, p.y / TILE)
            # darker toward the seam where the fabric is pulled tight, and in the creases
            e = min(abs(p.x) / A, 1.0) ** 6 + min(abs(p.y) / B, 1.0) ** 6
            a = 1.0 - 0.18 * min(e, 1.0)
            lp[col] = (a, a, a, 1.0)
    low = min(v.co.z for v in bm.verts)
    for v in bm.verts:
        v.co.z -= low
    return bm


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    albedo, normal = fabric.make_textures("T_pillow_case", HERE / "textures", (0.96, 0.95, 0.92), 0.02, threads=64, nstrength=1.6, seed=9)
    mat = fabric.fabric_material("PillowCase", albedo, normal, 0.85, normal_strength=0.6)
    bm = build()
    mesh = bpy.data.meshes.new("pillow")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    obj = bpy.data.objects.new("Pillow", mesh)
    bpy.context.collection.objects.link(obj)
    bpy.ops.wm.save_as_mainfile(filepath=str(HERE / "pillow.blend"))
    fabric.export_glb([obj], OUT / "pillow.glb")
    d = obj.dimensions
    print("pillow done", len(mesh.polygons), "faces", tuple(round(c, 3) for c in d))


main()
