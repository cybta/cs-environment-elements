"""The valley terrain under the old neighbourhood: heights from the bake, a preview ground mesh, and the
game's own road / water / hero-cottage models imported as read-only context.

valley_height.exr: 32-bit metres, 2560 x 1536 at 1 m, row 0 = north; pixel (r, c) is x = c - NX/2,
Blender y = NY/2 - r (the bake's convention). Godot: x = X, y = Z, z = -Y.
"""
import os

import bmesh
import bpy
import numpy as np

NX, NY = 2560, 1536


def _load(path):
    img = bpy.data.images.load(path, check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1, :, 0].copy()          # row 0 = north, like the file


class Terrain:
    def __init__(self, project):
        self.project = project
        self.out = os.path.join(project, "blender_src", "terrain", "out")
        self.h = _load(os.path.join(self.out, "valley_height.exr"))
        self.water_mask = _load(os.path.join(self.out, "valley_water_mask.png")) > 0.4

    def _rc(self, pts):
        pts = np.atleast_2d(np.asarray(pts, float))
        return NY / 2 - pts[:, 1], pts[:, 0] + NX / 2

    def height(self, pts):
        """Bilinear terrain height (m) at world (x, y) points (n, 2) -> (n,)."""
        r, c = self._rc(pts)
        r0 = np.clip(np.floor(r).astype(int), 0, NY - 2)
        c0 = np.clip(np.floor(c).astype(int), 0, NX - 2)
        fr, fc = np.clip(r - r0, 0, 1), np.clip(c - c0, 0, 1)
        h = self.h
        top = h[r0, c0] * (1 - fc) + h[r0, c0 + 1] * fc
        bot = h[r0 + 1, c0] * (1 - fc) + h[r0 + 1, c0 + 1] * fc
        return top * (1 - fr) + bot * fr

    def z(self, x, y):
        return float(self.height([(x, y)])[0])

    def water(self, pts):
        r, c = self._rc(pts)
        r = np.clip(np.round(r).astype(int), 0, NY - 1)
        c = np.clip(np.round(c).astype(int), 0, NX - 1)
        return self.water_mask[r, c]


def ground_mesh(terrain, name, x0, y0, x1, y1, step, mat, coll, uv_scale):
    """A terrain-following grid (preview of the game's terrain) with metric UVs."""
    xs = np.arange(x0, x1 + 1e-6, step)
    ys = np.arange(y0, y1 + 1e-6, step)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel()], -1)
    z = terrain.height(pts) - 0.02
    nx, ny = len(xs), len(ys)
    verts = np.column_stack([pts, z])
    i = np.arange(nx - 1)[None, :] + (np.arange(ny - 1) * nx)[:, None]
    i = i.ravel()
    faces = np.stack([i, i + 1, i + 1 + nx, i + nx], -1)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(faces.size)
    me.loops.foreach_set("vertex_index", faces.astype(np.int32).ravel())
    me.polygons.add(len(faces))
    me.polygons.foreach_set("loop_start", (np.arange(len(faces)) * 4).astype(np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(len(faces), bool))
    uv_scale = uv_scale(mat) if callable(uv_scale) else uv_scale
    uv = me.uv_layers.new(name="UVMap")
    lv = verts[faces.ravel()]
    uv.data.foreach_set("uv", (lv[:, :2] * uv_scale).astype(np.float32).ravel())
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def import_glb(path, coll):
    """Import a glb into `coll` (game models in world coordinates; glTF Y-up -> Blender Z-up)."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    return new


def ribbon(name, line, z_of, half0, half1, z_lift, mat, coll, uv_scale, keep=None):
    """A strip beside a polyline from `half0` to `half1` metres to its left (negative = right side),
    draped on the terrain. `keep(pts) -> bool array` drops quads whose corners fail it."""
    from .layout import offset_line
    uv_scale = uv_scale(mat) if callable(uv_scale) else uv_scale
    a, b = offset_line(line, half0), offset_line(line, half1)
    za, zb = z_of(a) + z_lift, z_of(b) + z_lift
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new("UVMap")
    va = [bm.verts.new((p[0], p[1], z)) for p, z in zip(a, za)]
    vb = [bm.verts.new((p[0], p[1], z)) for p, z in zip(b, zb)]
    ok_a = keep(a) if keep else np.ones(len(a), bool)
    ok_b = keep(b) if keep else np.ones(len(b), bool)
    for i in range(len(line) - 1):
        if not (ok_a[i] and ok_a[i + 1] and ok_b[i] and ok_b[i + 1]):
            continue
        quad = [va[i], va[i + 1], vb[i + 1], vb[i]] if half1 > half0 else [va[i], vb[i], vb[i + 1], va[i + 1]]
        try:
            f = bm.faces.new(quad)
        except ValueError:
            continue
        for lp in f.loops:
            lp[uvl].uv = (lp.vert.co.x * uv_scale, lp.vert.co.y * uv_scale)
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if not bm.faces:
        bm.free()
        return None
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob
