"""Levels of detail for every generated building and fence.

LOD0 is what the generators build (separate objects, interiors, door leaves that open).
LOD1..LOD3 are each ONE mesh (one draw call per material), built from LOD0 by:

  1. dropping small parts (each box / extrusion is one loose part; a part goes when it
     is thin or small enough for the level: frame bars, balusters, casings, hardware...),
  2. culling faces nobody can see from outside: rays are cast from points on each face
     over its hemisphere; a face is kept only if some ray gets away (to the sky or past
     the building) without hitting anything. That removes the whole interior, the faces
     where boxes touch, the undersides of slabs, everything behind (now opaque) glass,
  3. welding and merging coplanar faces that share a material and continuous UVs.

Glass becomes an opaque dark window material (no transparency sorting, no interior to
see). Fences can carry "cards" (see lod_cards): at LOD2/3 their boards and slats are
swapped for one alpha-cut quad per run.

Names follow the common engine convention: <root>_LOD1, <root>_LOD2, <root>_LOD3, all
parented to the root empty; LOD0 objects are tagged lod=0 (custom property).
"""

import math

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# level -> part filter: drop a part whose middle size < thin, or longest x middle < area (m²);
# 'cards' drops what the cards replace (boards, slats, rails: anything under 5 cm thick);
# 'slim' (fences only, see build): a part thinner than this keeps only its two broad faces and its top: the
# thin sides and the bottom of a 2 cm board are ~2 px wide at LOD1's 25 m+, and they are ~40 % of a fence
LEVELS = {
    1: dict(thin=0.0, area=0.004, cards=False, slim=0.04),
    2: dict(thin=0.035, area=0.08, cards=True, slim=0.0),
    3: dict(thin=0.1, area=0.35, cards=True, slim=0.0),
}
CARD_THICK = 0.05
GLASS_NAMES = {"C_window_glass", "C_villa_stair_glass", "RoomGen_Glass", "C_villa_stair_glass"}
LOD_GLASS = "C_window_lod"
RAY_FAR = 500.0
WEAR_UV = "WearUV"      # fence_geom.WEAR_UV (kept through the LODs)
TILT = 1.2              # side rays lean ~50 degrees off the normal


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------

def _is_glass(mat):
    if mat is None:
        return False
    if mat.name in GLASS_NAMES:
        return True
    bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.use_nodes and mat.node_tree else None
    if bsdf is None:
        return False
    for key in ("Transmission Weight", "Transmission"):
        if key in bsdf.inputs and bsdf.inputs[key].default_value > 0.5:
            return True
    return bsdf.inputs["Alpha"].default_value < 0.6


def lod_glass():
    """Windows seen from a distance: dark, glossy, opaque."""
    mat = bpy.data.materials.get(LOD_GLASS)
    if mat:
        return mat
    mat = bpy.data.materials.new(LOD_GLASS)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.04, 0.05, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.08
    mat.diffuse_color = (0.08, 0.1, 0.12, 1.0)
    return mat


# --------------------------------------------------------------------------
# Gathering LOD0
# --------------------------------------------------------------------------

def lod0_objects(root):
    """Every mesh under the root that belongs to LOD0 (not an earlier LOD)."""
    return [o for o in root.children_recursive if o.type == "MESH" and o.get("lod", 0) == 0]


def _parts(me):
    """Loose parts of a mesh: vertex index -> part id (union-find over faces). Vertices at
    the same spot count as one, since some builders give every face its own corners."""
    parent = list(range(len(me.vertices)))
    if len(me.loops) == len(me.vertices):            # no shared corners at all: weld by position
        first = {}                                   # (touching boxes elsewhere stay separate parts)
        for v in me.vertices:
            k = (round(v.co.x, 4), round(v.co.y, 4), round(v.co.z, 4))
            parent[v.index] = first.setdefault(k, v.index)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for p in me.polygons:
        vs = p.vertices
        r0 = find(vs[0])
        for v in vs[1:]:
            r = find(v)
            if r != r0:
                parent[r] = r0
    return [find(i) for i in range(len(parent))]


def part_size(pts, normals):
    """(thin, middle, long) sizes of a part in its own orientation: thinnest across one of
    its face normals, longest along its main axis square to that, middle across both."""
    def extent(d):
        vals = [p.dot(d) for p in pts]
        return max(vals) - min(vals)

    a, na = min(((extent(n), n) for n in normals), key=lambda t: t[0])
    lo = [min(p[k] for p in pts) for k in range(3)]
    hi = [max(p[k] for p in pts) for k in range(3)]
    axes = sorted(range(3), key=lambda k: lo[k] - hi[k])
    for k in axes:                                   # the longest box axis not along na
        e = Vector([1.0 if i == k else 0.0 for i in range(3)])
        e -= na * e.dot(na)
        if e.length > 0.3:
            break
    e.normalize()
    b, c = extent(na.cross(e)), extent(e)
    return sorted((a, b, c))


def thin_axis(pts, normals):
    """The face normal across which a part is thinnest."""
    def extent(d):
        vals = [p.dot(d) for p in pts]
        return max(vals) - min(vals)

    return min(normals, key=extent)


def _keep_part(size, spec):
    if spec["cards"] and size[0] < CARD_THICK:
        return False
    return size[1] >= spec["thin"] and size[2] * size[1] >= spec["area"]


class Soup:
    """Faces from many objects in the root's space: verts, faces, per-loop UVs, material per face, and the
    fences' second UV layer (fence_geom.WEAR_UV) where the source had one."""

    def __init__(self):
        self.verts, self.faces, self.uvs, self.mat_of = [], [], [], []
        self.wear = {}                     # face index -> per-loop WearUV
        self.mats = []

    def mat_index(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def add_face(self, pts, uvs, mat, wear=None):
        b = len(self.verts)
        self.verts += [Vector(p) for p in pts]
        self.faces.append(list(range(b, b + len(pts))))
        self.uvs.append([tuple(u) for u in uvs])
        if wear is not None:
            self.wear[len(self.faces) - 1] = [tuple(w) for w in wear]
        self.mat_of.append(self.mat_index(mat))


def gather(root, objs, spec, soup):
    inv = root.matrix_world.inverted()
    glass = lod_glass()
    for ob in objs:
        me = ob.data
        if not me.polygons:
            continue
        M = inv @ ob.matrix_world
        co = [M @ v.co for v in me.vertices]
        part = _parts(me)
        pts, nors = {}, {}
        for i, pid in enumerate(part):
            pts.setdefault(pid, []).append(co[i])
        rot = M.to_3x3()
        for p in me.polygons:
            n = (rot @ p.normal).normalized()
            seen = nors.setdefault(part[p.vertices[0]], [])
            if n.length > 0.5 and len(seen) < 12 and all(abs(n.dot(q)) < 0.999 for q in seen):
                seen.append(n)
        sizes = {pid: part_size(pts[pid], nors.get(pid) or [Vector((0, 0, 1))]) for pid in pts}
        keep = {pid: _keep_part(sizes[pid], spec) for pid in pts}
        slim = {pid: thin_axis(pts[pid], nors[pid]) for pid in pts
                if spec.get("slim") and nors.get(pid) and sizes[pid][0] < spec["slim"]}
        uvl = me.uv_layers.active.data if me.uv_layers.active else None
        wl = me.uv_layers.get(WEAR_UV)
        wl = wl.data if wl is not None else None
        slots = [s.material for s in ob.material_slots] or [None]
        for p in me.polygons:
            pid = part[p.vertices[0]]
            if not keep[pid]:
                continue
            if pid in slim:                          # a board: the broad faces and the top only
                n = (rot @ p.normal).normalized()
                if abs(n.dot(slim[pid])) < 0.9 and n.z < 0.5:
                    continue
            mat = slots[min(p.material_index, len(slots) - 1)]
            if _is_glass(mat):
                mat = glass
            uvs = [uvl[li].uv for li in p.loop_indices] if uvl else [(0.0, 0.0)] * len(p.vertices)
            wear = [wl[li].uv for li in p.loop_indices] if wl else None
            soup.add_face([co[v] for v in p.vertices], uvs, mat, wear)


# --------------------------------------------------------------------------
# Hidden-face culling
# --------------------------------------------------------------------------

def _normal(pts):
    n = Vector()
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        n += Vector(((a.y - b.y) * (a.z + b.z), (a.z - b.z) * (a.x + b.x), (a.x - b.x) * (a.y + b.y)))
    return n.normalized() if n.length > 1e-12 else None


def cull_hidden(soup):
    """Keep the faces some ray from outside can reach -> list of face indices."""
    if not soup.faces:
        return []
    tree = BVHTree.FromPolygons(soup.verts, soup.faces, epsilon=0.0)
    ground = min(v.z for v in soup.verts) + 0.02
    keep = []
    for fi, f in enumerate(soup.faces):
        pts = [soup.verts[i] for i in f]
        n = _normal(pts)
        if n is None or max(p.z for p in pts) < ground:
            continue
        c = sum(pts, Vector()) / len(pts)
        samples = [c] + [p + (c - p) * 0.12 for p in pts[:8]]
        t1 = n.orthogonal().normalized()
        t2 = n.cross(t1)
        dirs = [n] + [(n + t * TILT).normalized() for t in (t1, -t1, t2, -t2)]
        if _reaches_out(tree, samples, dirs, n, ground):
            keep.append(fi)
    return keep


def _reaches_out(tree, samples, dirs, n, ground):
    """True if a ray from one of the samples gets out. A ray going down stops at the
    ground; it still counts if it ran far enough for someone to stand in its way
    (the gap under a house on piles), not if it only crossed a crack."""
    for d in dirs:
        down = d.z < -1e-6
        for s in samples:
            o = s + n * 1e-3
            if o.z < ground and d.z <= 1e-6:
                continue                                     # starts underground
            far = (ground - o.z) / d.z if down else RAY_FAR
            if down and far < 0.3:
                continue
            if tree.ray_cast(o, d, min(far, RAY_FAR))[0] is None:
                return True
    return False


# --------------------------------------------------------------------------
# Mesh out
# --------------------------------------------------------------------------

def to_mesh(name, soup, faces):
    me = bpy.data.meshes.new(name)
    used = sorted({v for fi in faces for v in soup.faces[fi]})
    remap = {v: i for i, v in enumerate(used)}
    me.from_pydata([tuple(soup.verts[v]) for v in used], [], [[remap[v] for v in soup.faces[fi]] for fi in faces])
    uv = me.uv_layers.new(name="UVMap")
    li = 0
    for fi in faces:
        for u in soup.uvs[fi]:
            uv.data[li].uv = u
            li += 1
    if soup.wear:
        wear = me.uv_layers.new(name=WEAR_UV)
        li = 0
        for fi in faces:
            for u in soup.wear.get(fi, soup.uvs[fi]):
                wear.data[li].uv = u
                li += 1
        uv.active = uv.active_render = True
    for m in soup.mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", [soup.mat_of[fi] for fi in faces])

    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=5e-4)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=1e-4)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), use_dissolve_boundaries=False,
                             verts=bm.verts, edges=bm.edges, delimit={"MATERIAL", "UV"})
    bm.to_mesh(me)
    bm.free()
    _drop_unused_materials(me)
    me.update()
    return me


def _drop_unused_materials(me):
    used = sorted({p.material_index for p in me.polygons})
    if len(used) == len(me.materials):
        return
    remap = {old: new for new, old in enumerate(used)}
    keep = [me.materials[i] for i in used]
    idx = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in keep:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)


def tris(me):
    return sum(len(p.vertices) - 2 for p in me.polygons)


# --------------------------------------------------------------------------
# Entry points
# --------------------------------------------------------------------------

def clear(root):
    for o in list(root.children_recursive):
        if o.get("lod", 0) > 0:
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if me is not None and me.users == 0:
                bpy.data.meshes.remove(me)
    coll = bpy.data.collections.get(f"{root.name} LODs")
    if coll is not None and not coll.objects:
        bpy.data.collections.remove(coll)


def build(root, levels=(1, 2, 3)):
    """(Re)build the LODs of one generated building or fence -> {level: tris}."""
    from . import lod_cards

    clear(root)
    src = lod0_objects(root)
    for o in root.children_recursive:
        o["lod"] = 0
    home = root.users_collection[0] if root.users_collection else bpy.context.scene.collection
    coll = bpy.data.collections.new(f"{root.name} LODs")
    coll["roomgen_lod"] = True
    home.children.link(coll)

    stats = {0: sum(tris(o.data) for o in src)}
    cards = lod_cards.load(root)
    from ..core import paint as paint_attr                     # painted fences and cottages (core.paint)
    paint = paint_attr.stored(root)
    for lv in levels:
        spec = dict(LEVELS[lv])
        spec["cards"] = spec["cards"] and bool(cards)
        spec["slim"] = spec["slim"] if cards else 0.0      # fences (they have cards); buildings keep their edges
        soup = Soup()
        gather(root, src, spec, soup)
        faces = cull_hidden(soup)
        if spec["cards"]:
            first = len(soup.faces)
            lod_cards.add(soup, cards)
            faces += list(range(first, len(soup.faces)))
        name = f"{root.name}_LOD{lv}"
        me = to_mesh(name, soup, faces)
        if paint is not None:
            paint_attr.fill(me, *paint)
        ob = bpy.data.objects.new(name, me)
        coll.objects.link(ob)
        ob.parent = root
        ob["lod"] = lv
        stats[lv] = tris(me)
    for lv, t in stats.items():
        root[f"lod{lv}_tris"] = t
    show(root, root.get("lod_preview", 0))
    return stats


def show(root, level):
    """Show one level of this root in the viewport and renders, hide the others."""
    root["lod_preview"] = level
    for o in root.children_recursive:
        if "lod" not in o:
            continue
        on = o["lod"] == level
        o.hide_render = not on
        try:
            o.hide_set(not on)
        except RuntimeError:            # not in the view layer (excluded collection)
            pass


def roots(context, everything=False):
    """The generated roots to work on: all of them, or the ones the selection belongs to."""
    def top(o):
        while o.parent is not None:
            o = o.parent
        return o

    def generated(o):
        return o.type == "EMPTY" and o.parent is None and any(
            c.get("roomgen") or c.get("roomgen_fence") for c in o.users_collection)

    if everything:
        return [o for o in context.scene.objects if generated(o)]
    picked = {top(o) for o in context.selected_objects}
    if context.active_object is not None:
        picked.add(top(context.active_object))
    return [o for o in picked if generated(o)]
