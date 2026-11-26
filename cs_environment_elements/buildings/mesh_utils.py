"""Small mesh helpers shared by the house, villa and neighborhood builders."""

import bpy
import bmesh
from mathutils import Matrix, Vector

from ..core import neighborhood_materials as nm


def _boxes_mesh(name, boxes, offset):
    """One mesh from many axis-aligned boxes (x0, y0, z0, x1, y1, z1)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for x0, y0, z0, x1, y1, z1 in boxes:
        c = Vector(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)) + offset
        m = Matrix.Translation(c) @ Matrix.Diagonal((x1 - x0, y1 - y0, z1 - z0, 1.0))
        bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    bm.to_mesh(me)
    bm.free()
    return me


def _obj(name, data, coll, parent, mats=(), uv_z=0.0):
    """Link a new object; meshes also get metre-scaled UVs (after their materials are set)."""
    from ..core.materials import _uv_metric

    ob = bpy.data.objects.new(name, data)
    coll.objects.link(ob)
    ob.parent = parent
    for m in mats:
        if m is not None:
            data.materials.append(m)
    if isinstance(data, bpy.types.Mesh) and not data.uv_layers:
        _uv_metric(data, nm.uv_scale, uv_z, nm.uv_from_floor)
    return ob


def _mat_index(me, mat):
    """Slot index of `mat` on the mesh, adding it if needed."""
    for i, m in enumerate(me.materials):
        if m == mat:
            return i
    me.materials.append(mat)
    return len(me.materials) - 1


def _paint_by_normal(me, top, bottom, side):
    """Faces looking up get `top`, down `bottom`, everything else `side`."""
    it, ib, isd = _mat_index(me, top), _mat_index(me, bottom), _mat_index(me, side)
    for p in me.polygons:
        p.material_index = it if p.normal.z > 0.5 else ib if p.normal.z < -0.5 else isd
    return me


def _solid(name, verts, faces):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


def _clip_mesh(me, planes):
    """Cut away everything on the outer side of each (point, normal) plane and cap the cuts."""
    bm = bmesh.new()
    bm.from_mesh(me)
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-5, plane_co=co, plane_no=no, clear_outer=True)
        edges = [e for e in bm.edges if e.is_boundary]
        if edges:
            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return me


def _sheared_box(p0, p1, half_t, z_lo, z_hi):
    """A slab between two points that follows their slope: half_t to each side of the
    line p0-p1, from z_lo to z_hi above it -> (verts, faces)."""
    u = Vector((p1[0] - p0[0], p1[1] - p0[1], 0.0)).normalized()
    s = Vector((-u.y, u.x, 0.0)) * half_t
    verts = []
    for p in (Vector(p0), Vector(p1)):
        for side in (-1, 1):
            for z in (z_lo, z_hi):
                verts.append(tuple(p + s * side + Vector((0, 0, z))))
    # 0..3 at p0 (-lo, -hi, +lo, +hi), 4..7 at p1
    faces = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4]]
    return verts, faces


def sloped_fence(name, rails, offset, height=0.92, hand=0.045, foot=0.08, post=0.05):
    """Glass balustrades along stair flights -> (glass mesh, metal mesh).

    Each rail is ((x, y, z) low end, (x, y, z) high end) on the line of the tread
    nosings; the fence stands `height` above that line, following the slope.
    """
    glass, metal = [], []
    for a, b in rails:
        a, b = Vector(a) + offset, Vector(b) + offset
        u = Vector((b.x - a.x, b.y - a.y, 0.0)).normalized()
        k = post / 2 + 0.01
        ga, gb = a + u * k, b - u * k                       # glass stops short of the posts
        rise = (b.z - a.z) / max((b - a).xy.length, 1e-6)
        ga.z, gb.z = a.z + rise * k, b.z - rise * k
        glass.append(_sheared_box(ga, gb, 0.007, foot, height - hand))
        metal.append(_sheared_box(a, b, hand / 2 + 0.005, height - hand, height))     # handrail
        for p, d in ((a, 1), (b, -1)):                                              # end posts
            q = p + u * d * post / 2
            metal.append(_sheared_box(q - u * post / 2, q + u * post / 2, post / 2, 0.0, height))

    def mesh(label, parts):
        verts, faces = [], []
        for v, f in parts:
            base = len(verts)
            verts += v
            faces += [[base + i for i in face] for face in f]
        return _solid(f"{name}_{label}", verts, faces)

    return mesh("Glass", glass), mesh("Rail", metal)


def glass_fence(boxes, post=0.05, step=1.1, hand=0.045, foot=0.07):
    """Turn solid rail slabs into a glass balustrade -> (glass boxes, metal boxes).

    Each slab (x0, y0, z0, x1, y1, z1) marks where a fence runs: along its long side, as
    high as the slab. The glass floats `foot` above the floor between slim posts and
    under a round-ish handrail.
    """
    glass, metal = [], []
    for x0, y0, z0, x1, y1, z1 in boxes:
        along_x = (x1 - x0) >= (y1 - y0)
        a0, a1 = (x0, x1) if along_x else (y0, y1)
        c = (y0 + y1) / 2 if along_x else (x0 + x1) / 2
        n = max(1, round((a1 - a0) / step))
        h = hand / 2

        def box(s0, s1, lo, hi, half):
            return (s0, c - half, lo, s1, c + half, hi) if along_x else (c - half, s0, lo, c + half, s1, hi)

        for i in range(n):
            g0 = a0 + (a1 - a0) * i / n + (post if i else 0.0) / 2 + 0.01
            g1 = a0 + (a1 - a0) * (i + 1) / n - (post if i < n - 1 else 0.0) / 2 - 0.01
            glass.append(box(g0, g1, z0 + foot, z1 - hand, 0.007))
        for i in range(n + 1):
            m = a0 + (a1 - a0) * i / n
            lo, hi = min(max(m - post / 2, a0), a1 - post), max(min(m + post / 2, a1), a0 + post)
            metal.append(box(lo, hi, z0, z1, post / 2))
        metal.append(box(a0, a1, z1 - hand, z1, h + 0.005))
    return glass, metal
