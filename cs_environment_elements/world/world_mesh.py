"""Mesh building blocks for the world: one Parts collector per object (boxes turned
about Z, cylinders, ribbons that follow a curve), emitted as a single multi-material
mesh with the addon's metric UVs."""

import math

import bpy
import numpy as np

from ..core import neighborhood_materials as nm


class Parts:
    def __init__(self):
        self.verts, self.faces, self.fmat = [], [], []
        self.mats = []

    def _mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def face(self, pts, mat):
        base = len(self.verts)
        self.verts += [tuple(map(float, p)) for p in pts]
        self.faces.append(tuple(range(base, base + len(pts))))
        self.fmat.append(self._mi(mat))

    def box(self, center, size, angle, mat, top_mat=None):
        """Box of size (lx, ly, lz) centred on center (x, y, z), turned `angle` about Z."""
        cx, cy, cz = center
        lx, ly, lz = (s / 2 for s in size)
        c, s = math.cos(angle), math.sin(angle)
        p = [(cx + c * x - s * y, cy + s * x + c * y, cz + z)
             for z in (-lz, lz) for y in (-ly, ly) for x in (-lx, lx)]
        # 0..3 bottom (x-,y-),(x+,y-),(x-,y+),(x+,y+) ; 4..7 top
        quads = ((0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (1, 3, 7, 5), (3, 2, 6, 7), (2, 0, 4, 6))
        for k, q in enumerate(quads):
            self.face([p[i] for i in q], top_mat if (k == 1 and top_mat) else mat)

    def seg_box(self, a, b, width, z0, z1, mat, top_mat=None):
        """Box from point a to point b (x, y) with its bottom at z0 and top at z1."""
        a, b = np.asarray(a[:2], float), np.asarray(b[:2], float)
        d = b - a
        L = float(np.linalg.norm(d))
        if L < 1e-6:
            return
        m = (a + b) / 2
        self.box((m[0], m[1], (z0 + z1) / 2), (L, width, z1 - z0), math.atan2(d[1], d[0]), mat, top_mat)

    def cylinder(self, center, r, z0, z1, mat, seg=8, cap=True, r_top=None):
        cx, cy = center[:2]
        rt = r if r_top is None else r_top
        ring0 = [(cx + r * math.cos(2 * math.pi * k / seg), cy + r * math.sin(2 * math.pi * k / seg), z0)
                 for k in range(seg)]
        ring1 = [(cx + rt * math.cos(2 * math.pi * k / seg), cy + rt * math.sin(2 * math.pi * k / seg), z1)
                 for k in range(seg)]
        for k in range(seg):
            n = (k + 1) % seg
            self.face([ring0[k], ring0[n], ring1[n], ring1[k]], mat)
        if cap:
            self.face(ring1, mat)
            self.face(ring0[::-1], mat)

    def ribbon(self, pts, z, o0, o1, mat, keep=None, closed=False):
        """A flat strip between offsets o0 < o1 (metres to the left of the curve) at
        heights z (per point, or (z_at_o0, z_at_o1) arrays). keep[i] False drops quad i."""
        pts = np.asarray(pts, float)
        nrm = _normals(pts, closed)
        za, zb = (z, z) if not isinstance(z, tuple) else z
        o0 = np.broadcast_to(np.asarray(o0, float), (len(pts),))
        o1 = np.broadcast_to(np.asarray(o1, float), (len(pts),))
        A = pts + nrm * o0[:, None]
        B = pts + nrm * o1[:, None]
        n = len(pts) if closed else len(pts) - 1
        for i in range(n):
            j = (i + 1) % len(pts)
            if keep is not None and not keep[i]:
                continue
            self.face([(*A[i], za[i]), (*A[j], za[j]), (*B[j], zb[j]), (*B[i], zb[i])], mat)

    def wall(self, pts, z0, z1, off, mat, keep=None, closed=False, flip=False):
        """A vertical strip at a fixed offset from the curve, from z0 up to z1 (arrays)."""
        pts = np.asarray(pts, float)
        P = pts + _normals(pts, closed) * off
        n = len(pts) if closed else len(pts) - 1
        for i in range(n):
            j = (i + 1) % len(pts)
            if keep is not None and not keep[i]:
                continue
            q = [(*P[i], z0[i]), (*P[j], z0[j]), (*P[j], z1[j]), (*P[i], z1[i])]
            self.face(q[::-1] if flip else q, mat)

    def build(self, name, coll, parent=None, smooth=False):
        if not self.faces:
            return None
        me = bpy.data.meshes.new(name)
        me.from_pydata(self.verts, [], self.faces)
        for m in self.mats:
            me.materials.append(m)
        me.polygons.foreach_set("material_index", self.fmat)
        if smooth:
            me.polygons.foreach_set("use_smooth", [True] * len(self.faces))
        from ..core.materials import _uv_metric
        _uv_metric(me, nm.uv_scale)
        me.validate()
        me.update()
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        if parent is not None:
            ob.parent = parent
        return ob


def _normals(pts, closed):
    if closed:
        d = np.roll(pts, -1, 0) - np.roll(pts, 1, 0)
    else:
        d = np.gradient(pts, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    return np.stack([-d[:, 1], d[:, 0]], 1)


def normals(pts, closed=False):
    return _normals(np.asarray(pts, float), closed)


def linked_copy(src, name, coll, loc, rot_z=0.0, scale=1.0):
    """A copy of `src` sharing its mesh, at loc turned rot_z."""
    ob = src.copy()
    ob.name = name
    coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (0.0, 0.0, rot_z)
    ob.scale = (scale, scale, scale)
    return ob
