"""World parks: playgrounds with the user's old playground models, parks with paths,
benches, a fountain or a gazebo, and the summit round the hero cedar.

The playground models are appended once from PLAYGROUND_DIR into the hidden library
collection and placed as linked copies (shared meshes), keeping their parent/child
hierarchy (swing seats, seesaw beam, merry-go-round top stay separate, so they can
still move in the game).
"""

import math
import os

import bpy
import numpy as np
from mathutils import Matrix

from . import world_materials as wm
from .world_mesh import Parts

PLAYGROUND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "props", "assets", "playground")
MODELS = {          # file -> top-level object(s)
    "swing": ("playground_swing_set.blend", "SwingSet"),
    "slide": ("playground_slide.blend", "PlaygroundSlide"),
    "seesaw": ("playground_seesaw.blend", "SeesawBase"),
    "merry": ("playground_merry_go_round.blend", "MerryGoRoundBase"),
    "bench": ("playground_bench_bin.blend", "PlaygroundBench"),
    "bin": ("playground_bench_bin.blend", "PlaygroundBin"),
}


class Props:
    def __init__(self, lib, folder=PLAYGROUND_DIR):
        self.lib, self.folder = lib, folder
        self.files = {}             # file -> {original object name: appended object}
        self.placed = []            # (kind, object)
        self.missing = []

    def source(self, kind):
        fn, top = MODELS[kind]
        if fn not in self.files:
            self.files[fn] = {}
            path = os.path.join(self.folder, fn)
            if not os.path.exists(path):
                self.missing.append(path)
            else:
                with bpy.data.libraries.load(path, link=False) as (src, dst):
                    names = list(src.objects)
                    dst.objects = list(names)        # Blender swaps this list's names for objects
                for name, ob in zip(names, dst.objects):
                    if ob is None:
                        continue
                    self.lib.objects.link(ob)
                    ob.hide_viewport = ob.hide_render = True
                    self.files[fn][name] = ob
                    self._relink(ob)
        return self.files[fn].get(top)

    def _relink(self, ob):
        """Point the model's images at the add-on's bundled copies (matched by file name)."""
        from ..core.library import relink_images
        images = {node.image for slot in ob.material_slots if slot.material and slot.material.node_tree
                  for node in slot.material.node_tree.nodes if getattr(node, "image", None)}
        relink_images(images)

    def place(self, kind, coll, x, y, z, rot):
        src = self.source(kind)
        if src is None:
            return None
        root = self._dup(src, coll, None)
        root.matrix_world = Matrix.Translation((x, y, z)) @ Matrix.Rotation(rot, 4, "Z")
        self.placed.append((kind, root))
        return root

    def _dup(self, src, coll, parent):
        ob = src.copy()                     # shares the mesh
        coll.objects.link(ob)
        ob.hide_viewport = ob.hide_render = False
        if parent is not None:
            ob.parent = parent
            ob.matrix_parent_inverse = src.matrix_parent_inverse.copy()
            ob.matrix_basis = src.matrix_basis.copy()
        for child in src.children:
            self._dup(child, coll, ob)
        return ob


# --------------------------------------------------------------------------
# Playgrounds
# --------------------------------------------------------------------------

def playground(props, P, coll, zone, T, m, style="SAND", scale=1.0):
    """The five models and benches on a pad inside the zone (local u along, v across)."""
    z = T.z(*zone.c)
    hw, hd = min(zone.hw, 10.5) * scale, min(zone.hd, 8.0) * scale       # the kit stays together
    a = zone.angle
    if style == "SAND":
        P.box((zone.c[0], zone.c[1], z + 0.03), (2 * hw, 2 * hd, 0.08), a, m["C_world_sand"])
    for su in (-1, 1):                       # timber edging (gappy for the old one)
        for k in range(8 if style == "SAND" else 5):
            t0, t1 = -hw + k * (2 * hw / 8), -hw + (k + 0.9) * (2 * hw / 8)
            if style != "SAND" and k % 2:
                continue
            P.seg_box(zone.world(t0, su * hd), zone.world(t1, su * hd), 0.14, z - 0.05, z + 0.18, m["C_world_timber"])
    # metres from the pad centre (u along the zone, v across), turned about Z
    spots = (("swing", -5.5, 2.6, 0.0), ("slide", 5.2, 2.2, math.pi / 2), ("seesaw", -5.0, -3.2, 0.0),
             ("merry", 0.8, -2.6, 0.0), ("bench", 7.6, -5.0, math.pi), ("bin", 8.9, -5.1, 0.0),
             ("bench", -1.0, 5.6, 0.0), ("bin", 0.4, 5.8, 0.0))
    k = min(hw / 10.5, hd / 8.0)
    for kind, u, v, r in spots:
        p = zone.world(u * k, v * k)
        props.place(kind, coll, p[0], p[1], T.z(*p) + (0.06 if style == "SAND" else 0.0), a + r)


# --------------------------------------------------------------------------
# Parks
# --------------------------------------------------------------------------

def park(props, P, coll, zone, T, m, rng, tree_spots):
    x = zone.extra
    z0 = T.z(*zone.c)
    hw, hd, a = zone.hw, zone.hd, zone.angle
    path_mat = m["C_world_dirt"] if x.get("old") else m["C_path"]
    # Oval path round the park and a straight one through it
    k = 48
    ring = [zone.world(0.72 * hw * math.cos(2 * math.pi * i / k), 0.62 * hd * math.sin(2 * math.pi * i / k))
            for i in range(k)]
    for i in range(k):
        p, q = ring[i], ring[(i + 1) % k]
        P.seg_box(p, q, 2.2, z0 - 0.05, z0 + 0.06, path_mat)
    P.seg_box(zone.world(-hw, 0), zone.world(hw, 0), 2.4, z0 - 0.05, z0 + 0.065, path_mat)
    if x.get("fountain"):
        c = zone.c
        P.cylinder(c, 7.5, z0 - 0.05, z0 + 0.07, path_mat, seg=32)
        P.cylinder(c, 3.6, z0, z0 + 0.55, m["C_stone"], seg=32)
        P.cylinder(c, 3.25, z0, z0 + 0.47, m["C_world_water"], seg=32)
        P.cylinder(c, 0.45, z0, z0 + 1.7, m["C_stone"], seg=12)
        P.cylinder(c, 1.2, z0 + 1.2, z0 + 1.35, m["C_stone"], seg=16)
    if x.get("beach"):                       # a gazebo looking over the lake
        g = zone.world(0.35 * hw, 0.45 * hd)
        _gazebo(P, g, T.z(*g), m)
    # Benches along the oval path, facing it
    for i in range(0, k, 8):
        p = np.array(ring[i])
        out = p - zone.c
        out /= max(np.linalg.norm(out), 1e-6)
        b = p + out * 1.9
        props.place("bench", coll, b[0], b[1], T.z(*b), math.atan2(out[1], out[0]) + math.pi / 2)
        if i % 16 == 0:
            q = b + np.array([-out[1], out[0]]) * 1.3
            props.place("bin", coll, q[0], q[1], T.z(*q), 0.0)
    if x.get("playground"):
        from .world_layout import Zone
        pg = Zone(zone.name + " Playground", "PLAYGROUND", zone.world(-0.5 * hw, 0.0), zone.u,
                  min(14.0, 0.3 * hw), min(10.0, 0.45 * hd))
        playground(props, P, coll, pg, T, m, "SAND")
    # Tree spots: between the oval and the edge, and inside the oval off the paths
    want = int(2 * hw * 2 * hd / 140)
    for _ in range(want * 6):
        if want <= 0:
            break
        u, v = rng.uniform(-hw + 2, hw - 2), rng.uniform(-hd + 2, hd - 2)
        e = (u / (0.72 * hw)) ** 2 + (v / (0.62 * hd)) ** 2
        if 0.75 < e < 1.35 or abs(v) < 3.5:
            continue
        if x.get("fountain") and abs(u) < 12 and abs(v) < 12:
            continue
        if x.get("playground") and abs(u + 0.5 * hw) < 0.3 * hw + 4 and abs(v) < 0.45 * hd + 4:
            continue
        if x.get("beach") and u > 0.1 * hw and v > 0.25 * hd:
            continue
        p = zone.world(u, v)
        if any(np.hypot(p[0] - t[0], p[1] - t[1]) < 7.0 for t in tree_spots):
            continue
        tree_spots.append((p[0], p[1], "PARK"))
        want -= 1


def _gazebo(P, c, z, m):
    r, posts, h = 3.2, 6, 2.6
    P.cylinder(c, r + 0.4, z - 0.1, z + 0.25, m["C_stone"], seg=posts)
    for i in range(posts):
        ang = 2 * math.pi * i / posts
        P.cylinder((c[0] + r * math.cos(ang), c[1] + r * math.sin(ang)), 0.1, z + 0.25, z + h, m["C_world_timber"], seg=6)
    P.cylinder(c, r + 0.25, z + h, z + h + 0.2, m["C_world_timber"], seg=posts)
    P.cylinder(c, r + 0.7, z + h + 0.2, z + h + 1.9, m["C_roof_dark"], seg=posts, r_top=0.15)


def summit(props, P, coll, zone, T, m, rng, way_in):
    """A low dry-stone ring round the cedar, open towards the trail, and two benches."""
    c = zone.c
    z = T.z(*c)
    R = 11.5
    k = 40
    gap = math.atan2(way_in[1] - c[1], way_in[0] - c[0])
    for i in range(k):
        a0, a1 = 2 * math.pi * i / k, 2 * math.pi * (i + 1) / k
        if abs(((a0 + math.pi / k - gap) + math.pi) % (2 * math.pi) - math.pi) < 0.3:
            continue                          # the way in from the trail
        p = (c[0] + R * math.cos(a0), c[1] + R * math.sin(a0))
        q = (c[0] + R * math.cos(a1), c[1] + R * math.sin(a1))
        P.seg_box(p, q, 0.6, T.z(*p) - 0.3, T.z(*p) + rng.uniform(0.45, 0.6), m["C_world_rock"])
    for ang in (gap + math.radians(150), gap - math.radians(150)):
        b = (c[0] + (R + 2.0) * math.cos(ang), c[1] + (R + 2.0) * math.sin(ang))
        props.place("bench", coll, b[0], b[1], T.z(*b), ang + math.pi / 2)


def build(L, T, coll, lib, rng, tree_spots, folder=PLAYGROUND_DIR):
    m = {k: wm.ensure(k) for k in ("C_path", "C_stone", "C_world_sand", "C_world_timber", "C_world_dirt",
                                    "C_world_rock", "C_roof_dark")}
    m["C_world_water"] = wm.water()
    props = Props(lib, folder)
    P = Parts()
    for zone in L.zones:
        if zone.kind == "PARK":
            park(props, P, coll, zone, T, m, rng, tree_spots)
        elif zone.kind == "PLAYGROUND":
            playground(props, P, coll, zone, T, m, zone.extra.get("style", "SAND"))
        elif zone.kind == "SUMMIT":
            summit(props, P, coll, zone, T, m, rng, L.road("Cedar Trail").pts[-1])
    P.build("Parks_Ground", coll)
    return props
