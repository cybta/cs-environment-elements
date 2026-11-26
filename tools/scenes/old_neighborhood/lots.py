"""One lot of the old neighbourhood: cottage, fence (door + driveway gate), driveway, front path and the
yard (sitting corner, laundry, firewood shed, work clutter, bins, a tree and bushes).

Everything is laid out in the lot's own frame (layout.Lot: u across, v away from the road) and turned
into world coordinates at the end; the terrain gives every piece its height.
"""
import math
import random

import bpy
import numpy as np
from mathutils import Vector

from cs_environment_elements.buildings import fence_build as fb, house
from cs_environment_elements.buildings.fence_paint import PALETTE, quiet as fence_quiet
from cs_environment_elements.core import library, naming
from cs_environment_elements.core import neighborhood_materials as nm
from cs_environment_elements.core.paint import quiet as paint_quiet
from cs_environment_elements.interior import CATALOG as INTERIOR
from cs_environment_elements.props import CATALOG as PROPS

from . import terrain as tr
from .layout import DRIVE_HALF, densify

HALF_PI = math.pi / 2


# ------------------------------------------------------------------ small helpers
def coll(name, parent=None):
    c = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    sc = bpy.context.scene
    parent = parent or sc.collection
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def adopt(child, parent):
    """Move a collection the generators made at the scene root under `parent`."""
    sc = bpy.context.scene
    if child.name not in parent.children:
        parent.children.link(child)
    if child.name in sc.collection.children:
        sc.collection.children.unlink(child)


def _item(cat, kind, key):
    return next(it for st in ("OLD", "NEW", "ANY") for it in cat.items(kind, st) if it.key == key)


def place(cat, kind, key, at, rot, target, extra=False):
    it = _item(cat, kind, key)
    ob = library.place(it, cat.folder, target, Vector(at), rot)
    if extra and it.extra:
        att = library.place(it.extra, cat.folder, target, Vector(at), rot)
        bpy.context.view_layer.update()
        att.parent = ob
        att.matrix_parent_inverse = ob.matrix_world.inverted()
    return ob


class Occupancy:
    """Axis-aligned rectangles in a lot's (u, v) frame."""

    def __init__(self, bounds):
        self.bounds = bounds              # u0, u1, v0, v1 (inside the fence)
        self.rects = []

    def add(self, u0, u1, v0, v1):
        self.rects.append((min(u0, u1), max(u0, u1), min(v0, v1), max(v0, v1)))

    def free(self, u0, u1, v0, v1):
        b = self.bounds
        if u0 < b[0] or u1 > b[1] or v0 < b[2] or v1 > b[3]:
            return False
        return all(u1 <= r[0] or u0 >= r[1] or v1 <= r[2] or v0 >= r[3] for r in self.rects)

    def find(self, rng, w, d, region=None, tries=80, pad=0.25):
        """A free spot (u, v centre) for a w x d footprint inside `region` (default: the whole lot)."""
        u0, u1, v0, v1 = region or self.bounds
        for _ in range(tries):
            u = rng.uniform(u0 + w / 2, u1 - w / 2) if u1 - u0 > w else (u0 + u1) / 2
            v = rng.uniform(v0 + d / 2, v1 - d / 2) if v1 - v0 > d else (v0 + v1) / 2
            if self.free(u - w / 2 - pad, u + w / 2 + pad, v - d / 2 - pad, v + d / 2 + pad):
                self.add(u - w / 2, u + w / 2, v - d / 2, v + d / 2)
                return u, v
        return None


# ------------------------------------------------------------------ the builder
class LotBuilder:
    def __init__(self, ctx, terrain, lot, seed, colls, poles=()):
        self.ctx, self.t, self.L = ctx, terrain, lot
        self.rng = random.Random(seed * 1000 + lot.idx)
        self.seed = seed
        self.c = colls
        self.poles = [np.array(p[:2]) for p in poles]
        L = lot
        self.occ = Occupancy((-L.wl + 0.35, L.wr - 0.35, L.v0 + 0.35, L.v1 - 0.35))
        self.info = dict(idx=L.idx)

    # world helpers --------------------------------------------------
    def at(self, u, v, dz=0.0):
        p = self.L.world(u, v)
        return Vector((p[0], p[1], self.t.z(p[0], p[1]) + dz))

    def rot(self, quarter=0, jitter=0.0):
        return self.L.angle + quarter * HALF_PI + jitter

    def put(self, cat, kind, key, u, v, quarter=0, jitter=0.0, dz=0.0, target=None, extra=False):
        return place(cat, kind, key, self.at(u, v, dz), self.rot(quarter, jitter), target or self.c["yards"], extra)

    # ----------------------------------------------------------------
    def build(self):
        self._cottage()
        self._grounds()
        self._fence()
        self._yard()
        return self.info

    def _cottage(self):
        ctx, rng, L = self.ctx, self.rng, self.L
        s = ctx.scene.house_gen
        s.building_type = "COTTAGE"
        s.add_labels, s.add_lights, s.add_inserts = False, False, True
        s.cottage_style = "PAINTED" if rng.random() < 0.6 else "TIMBER"
        roomy = min(L.wl, L.wr) + max(L.wl, L.wr) > 16 and L.depth > 24
        s.total_area = rng.uniform(55, 74) if roomy else rng.uniform(42, 58)
        s.bedrooms = 2 if s.total_area > 60 else 1
        s.bathrooms = 0
        s.seed = 1000 + self.seed * 37 + L.idx
        with paint_quiet():
            for k in ("cottage_roof", "cottage_paint", "cottage_siding"):
                setattr(s, k, "RANDOM")
            s.cottage_peel = rng.uniform(0.15, 0.6)
            s.cottage_roof_peel = rng.uniform(0.2, 0.75)
        s.cottage_chimney = rng.random() < 0.75
        name = naming.next_name("cottage-%s" % s.cottage_style.lower())
        ctx.scene.cursor.location = (0, 0, 0)
        plan = house._build(ctx, s, lambda *a: print("cottage:", a), name=name, site=True)
        root = bpy.data.objects[name]
        ctx.view_layer.update()
        lo, hi = library.bounds(root)
        hw_l, hw_r, front, back = -lo.x, hi.x, -lo.y, hi.y
        ent = next((o for o in plan.floors[0].openings if o.kind == "ENTRANCE"), None)
        door_lx = ((ent.s0 + ent.s1) / 2 - plan.W / 2) if ent is not None and ent.axis == "X" else 0.0

        # the house beside the driveway (side with more room), else straight at its end
        v_front = L.v0 + rng.uniform(3.0, 5.0)
        span = [L.path_u(v) for v in np.linspace(L.v0, v_front + front + back, 6)]
        # score = room left over on that side; a shared border counts against it, so two neighbours' houses
        # don't end up either side of the one fence
        options = []
        u_right = max(span) + DRIVE_HALF + 0.9 + hw_l
        if u_right + hw_r + 1.2 <= L.wr:
            options.append((L.wr - (u_right + hw_r) - 8 * hasattr(L, "shared_right"), u_right))
        u_left = min(span) - DRIVE_HALF - 0.9 - hw_r
        if u_left - hw_l - 1.2 >= -L.wl:
            options.append((u_left - hw_l + L.wl - 8 * hasattr(L, "shared_left"), u_left))
        # straight at the driveway's end (car parked in front) when it fits: preferred over a shared side
        u_end = L.path_u(L.drive_end_v)
        v_end_front = max(v_front, L.drive_end_v + DRIVE_HALF + 1.5)
        if v_end_front + front + back <= L.v1 - 2.0 and -L.wl + 1.2 <= u_end - hw_l and u_end + hw_r <= L.wr - 1.2:
            options.append((0.5, None))
        best = max(options, key=lambda o: o[0]) if options else (0, None)
        if best[1] is not None:
            u_h = best[1]
            beside = True
        else:                                                   # driveway ends at the front yard
            u_h = L.path_u(L.drive_end_v)
            v_front = max(v_front, L.drive_end_v + DRIVE_HALF + 1.5)
            beside = False
        v_h = v_front + front
        if v_h + back > L.v1 - 2.0:                             # short lot: smaller front yard
            v_h = max(L.v0 + 1.5 + front, L.v1 - 2.0 - back)
        p = L.world(u_h, v_h)
        root.location = (p[0], p[1], self.t.z(p[0], p[1]))
        root.rotation_euler.z = L.angle
        adopt(bpy.data.collections[name], self.c["cottages"])
        self.occ.add(u_h - hw_l - 0.3, u_h + hw_r + 0.3, v_h - front - 0.2, v_h + back + 0.3)
        self.house = dict(u=u_h, v=v_h, front=front, back=back, hw_l=hw_l, hw_r=hw_r, door_u=u_h + door_lx,
                          beside=beside)
        self.info.update(name=name, root=root, W=plan.W, D=plan.D, lift=s.ground_lift, angle=L.angle,
                         center=(p[0], p[1]), u=u_h, v=v_h)

    def _grounds(self):
        """Driveway (gravel, into the lot to a parking spot) and the trodden front path."""
        L, h = self.L, self.house
        gravel, dirt = nm.ensure("C_world_gravel"), nm.ensure("C_world_dirt")
        v_end = max(L.drive_end_v, L.v0 + 7.5)
        if not h["beside"]:
            v_end = min(v_end, h["v"] - h["front"] - 0.4)
        line = [(L.path_u(v), v) for v in np.arange(3.2, v_end, 1.0)] + [(L.path_u(v_end), v_end)]
        world = np.array([L.world(u, v) for u, v in line])
        tr.ribbon("%s_Driveway" % self.info["name"], densify(world, 1.0), self.t.height, -DRIVE_HALF,
                  DRIVE_HALF, 0.14, gravel, self.c["ground"], nm.uv_scale)
        us = [u for u, _ in line]
        self.occ.add(min(us) - DRIVE_HALF - 0.4, max(us) + DRIVE_HALF + 0.4, L.v0 - 1, v_end + 0.8)
        self.gate_u = L.path_u(L.v0)
        self.occ.add(self.gate_u - 1.9, self.gate_u + 1.9, L.v0, L.v0 + 2.0)      # gate leaves swing in
        # front path from the fence door to the veranda steps
        du = h["door_u"]
        self.door = abs(du - self.gate_u) > DRIVE_HALF + 1.9 and -L.wl + 0.8 < du < L.wr - 0.8
        if self.door:
            v_steps = h["v"] - h["front"] + 0.3
            pts = np.array([L.world(du, L.v0 - 0.3), L.world(du, v_steps)])
            mat = gravel if self.rng.random() < 0.5 else dirt
            tr.ribbon("%s_Path" % self.info["name"], densify(pts, 1.0), self.t.height, -0.6, 0.6, 0.03, mat,
                      self.c["ground"], nm.uv_scale)
            self.occ.add(du - 1.0, du + 1.0, L.v0, v_steps)

    def _fence(self):
        ctx, L, rng = self.ctx, self.L, self.rng
        cs = L.corners()
        z = self.t.height(cs)
        me = bpy.data.meshes.new("%s_lot" % self.info["name"])
        me.from_pydata([(p[0], p[1], zz) for p, zz in zip(cs, z)], [(0, 1), (1, 2), (2, 3), (3, 0)], [])
        outline = bpy.data.objects.new("lot-%02d-outline" % L.idx, me)
        self.c["outlines"].objects.link(outline)
        g = ctx.scene.house_gen.fence
        # a shared border (layout._share_borders) is built once, by the lot on its left
        g.style, g.seed, g.flip = "OLD", 100 + L.idx, False
        g.skip_sides = ", ".join(str(k) for k in sorted(L.skip))
        g.shared_posts = False
        g.height = rng.choice((1.2, 1.35, 1.5, 1.5, 1.6))
        g.uneven, g.gap = rng.uniform(0.025, 0.06), rng.uniform(0.05, 0.08)
        with fence_quiet():
            g.paint = rng.random() < 0.85
            g.paint_color = rng.choice(PALETTE)[1]
            g.peel = rng.uniform(0.35, 0.8)
        g.outline = outline
        u0, u1 = L.local(cs[0])[0], L.local(cs[1])[0]          # the front side (side 1), maybe a quad's

        def along_front(u):
            return min(max((u - u0) / (u1 - u0), 0.02), 0.98)

        g.gate, g.gate_side, g.gate_width = True, 1, 3.2
        g.gate_pos = along_front(self.gate_u)
        g.gate_leaves = rng.choice((1, 2))
        g.door, g.door_side, g.door_width = self.door, 1, 1.0
        if self.door:
            g.door_pos = along_front(self.house["door_u"])
        name = naming.next_name("fence-old")
        res = fb.build(ctx, g, outline, fb.outline_chains(outline, ctx, sync_edit=False), name=name)
        fc = res[0] if isinstance(res, tuple) else res
        if fc is not None:
            adopt(fc, self.c["fences"])
            warn = res[1] if isinstance(res, tuple) else []
            for w in warn:
                print("fence %s: %s" % (name, w))
        self.info["fence"] = name

    # ------------------------------------------------------------ the yard
    def _yard(self):
        rng, L, h, occ = self.rng, self.L, self.house, self.occ
        back = (occ.bounds[0], occ.bounds[1], h["v"] + h["back"] + 0.8, occ.bounds[3])
        if rng.random() < 0.45:
            self._woodshed()
        if rng.random() < 0.6:
            self._laundry(back)
        if rng.random() < 0.6:
            self._sitting()
        for _ in range(rng.choice((1, 2, 2, 3))):
            self._clutter()
        if rng.random() < 0.45:
            self._hose_and_can()
        if rng.random() < 0.65:
            self._bins()
        self._green()

    def _woodshed(self):
        occ, L = self.occ, self.L
        v1 = occ.bounds[3]
        spot = occ.find(self.rng, 3.4, 1.4, (occ.bounds[0], occ.bounds[1], v1 - 1.45, v1))
        if spot:
            u, v = spot
            self.put(PROPS, "YARD", "woodshed_old", u, v, jitter=self.rng.uniform(-0.03, 0.03))
            for k, key in enumerate(("garden_shovel", "garden_fork")):
                if self.rng.random() < 0.6 and occ.free(u + 1.9 + k * 0.3, u + 2.2 + k * 0.3, v - 0.2, v + 0.2):
                    self.put(PROPS, "GARDEN", key, u + 1.95 + k * 0.32, v + 0.3, jitter=self.rng.uniform(-0.3, 0.3))

    def _laundry(self, back):
        rng = self.rng
        spot = self.occ.find(rng, 5.4, 2.8, back) or self.occ.find(rng, 5.4, 2.8)
        if not spot:
            return
        u, v = spot
        j = rng.uniform(-0.08, 0.08)
        self.put(PROPS, "YARD", "clothesline_laundry" if rng.random() < 0.8 else "clothesline_empty", u, v + 0.6,
                 jitter=j)
        if rng.random() < 0.7:
            self.put(PROPS, "YARD", "laundry_basket", u - 1.4, v - 0.6, jitter=rng.uniform(-0.6, 0.6))
        if rng.random() < 0.5:
            self.put(PROPS, "YARD", "wash_tub", u + 1.8, v - 0.7, jitter=rng.uniform(-0.6, 0.6))

    def _sitting(self):
        rng = self.rng
        q = rng.choice((0, 1, 2, 3))
        w, d = (3.8, 2.6) if q % 2 == 0 else (2.6, 3.8)
        spot = self.occ.find(rng, w, d)
        if not spot:
            return
        u0, v0 = spot
        a = self.rot(q)
        ca, sa = math.cos(q * HALF_PI), math.sin(q * HALF_PI)

        def rel(x, y):                                        # group frame -> lot (u, v)
            return u0 + x * ca - y * sa, v0 + x * sa + y * ca

        j = rng.uniform(-0.1, 0.1)
        self.put(PROPS, "YARD", "yard_table_old", *rel(0, 0), quarter=q, jitter=j)
        self.put(PROPS, "YARD", "yard_bench_old", *rel(0, 0.95), quarter=q + 2, jitter=j)
        if rng.random() < 0.7:
            self.put(PROPS, "YARD", "yard_stool_old", *rel(1.15, -0.6), quarter=q, jitter=rng.uniform(-1, 1))
        if rng.random() < 0.35:
            self.put(INTERIOR, "SOFA", "old_armchair", *rel(-1.45, -0.2), quarter=q - 1, jitter=0.25)
        del a
        # trodden earth under the set
        L = self.L
        uu, vv = rel(0, 0.2)
        line = np.array([L.world(uu - w / 2 + 0.3, vv), L.world(uu + w / 2 - 0.3, vv)])
        mat = nm.ensure("C_world_dirt")
        tr.ribbon("lot-%02d_Patch" % L.idx, densify(line, 1.0), self.t.height, -d / 2 + 0.3, d / 2 - 0.3, 0.015,
                  mat, self.c["ground"], nm.uv_scale)

    def _clutter(self):
        rng = self.rng
        kind = rng.choice(("barrow", "crates", "blocks", "gravel", "gravel", "barrow"))
        q = rng.choice((0, 1, 2, 3))
        if kind == "barrow":
            w, d = (1.0, 1.8) if q % 2 == 0 else (1.8, 1.0)
            spot = self.occ.find(rng, w, d)
            if spot:
                self.put(PROPS, "GARDEN", "wheelbarrow", *spot, quarter=q, jitter=rng.uniform(-0.4, 0.4))
        elif kind == "crates":
            spot = self.occ.find(rng, 1.4, 0.8)
            if spot:
                u, v = spot
                self.put(PROPS, "GARDEN", "wooden_crate", u - 0.32, v, jitter=rng.uniform(-0.1, 0.1))
                self.put(PROPS, "GARDEN", "wooden_crate", u + 0.32, v, jitter=rng.uniform(-0.2, 0.2))
                if rng.random() < 0.6:
                    self.put(PROPS, "GARDEN", "wooden_crate", u - 0.3, v, dz=0.302, jitter=rng.uniform(-0.1, 0.1))
        elif kind == "blocks":
            spot = self.occ.find(rng, 1.6, 0.7)
            if spot:
                u, v = spot
                for k in range(3):
                    self.put(PROPS, "GARDEN", "concrete_block", u - 0.42 + k * 0.42, v, quarter=1,
                             jitter=rng.uniform(-0.08, 0.08))
                if rng.random() < 0.6:
                    self.put(PROPS, "GARDEN", "concrete_block", u - 0.2, v, dz=0.19, quarter=1, jitter=0.1)
        else:
            key, w, d = rng.choice((("gravel_pile_small", 1.8, 1.3), ("gravel_spill", 2.5, 1.8),
                                    ("gravel_pile_large", 3.2, 2.2)))
            spot = self.occ.find(rng, w, d)
            if spot:
                self.put(PROPS, "RUBBLE", key, *spot, jitter=rng.uniform(-0.3, 0.3))

    def _hose_and_can(self):
        h, rng = self.house, self.rng
        near = (h["u"] - h["hw_l"] - 2.5, h["u"] + h["hw_r"] + 2.5, h["v"] - h["front"] - 2.0,
                h["v"] + h["back"] + 2.0)
        spot = self.occ.find(rng, 1.4, 1.0, near)
        if spot:
            u, v = spot
            self.put(PROPS, "GARDEN", "garden_hose", u - 0.3, v, jitter=rng.uniform(0, math.tau))
            if rng.random() < 0.7:
                self.put(PROPS, "GARDEN", "watering_can", u + 0.45, v + 0.1, jitter=rng.uniform(0, math.tau))

    def _bins(self):
        """Wheelie bins out by the gate, between the fence and the road gravel."""
        L, rng = self.L, self.rng
        side = rng.choice((-1, 1))
        for s in (side, -side):
            u = self.gate_u + s * rng.uniform(2.2, 2.8)
            if not (-L.wl + 0.4 < u < L.wr - 0.4):
                continue
            p = L.world(u, L.v0 - 0.5)
            if any(np.linalg.norm(p - q) < 1.4 for q in self.poles):
                continue
            keys = ["wheelie_bin_green", "wheelie_bin_black"]
            rng.shuffle(keys)
            for k, key in enumerate(keys[:rng.choice((1, 2))]):
                place(PROPS, "BINS", key, self.at(u + s * k * 0.72, L.v0 - 0.5), self.rot(0, rng.uniform(-0.12, 0.12)),
                      self.c["street"])
                self.info.setdefault("bins", []).append(L.world(u + s * k * 0.72, L.v0 - 0.5))
            return

    def _green(self):
        """A tree in a back corner and a few bushes along the fence."""
        from cs_environment_elements.nature import core as tree_core
        rng, occ, h = self.rng, self.occ, self.house
        ts = self.ctx.scene.treegen
        made = []
        if rng.random() < 0.5:
            b = occ.bounds
            corner = rng.choice(((b[0], b[0] + 3.0), (b[1] - 3.0, b[1])))
            region = (corner[0], corner[1], max(b[3] - 4.0, h["v"] + h["back"] + 5.0), b[3])
            spot = occ.find(rng, 1.4, 1.4, region) if region[3] - region[2] > 1.6 else None
            if spot:
                made.append((rng.choice(("OAK", "MAPLE", "MAPLE", "PINE", "MAPLE_AUTUMN")), spot,
                             rng.uniform(0.55, 0.75)))          # yard trees: fruit-tree size, clear of the roof
        for _ in range(rng.choice((1, 2, 3, 3, 4))):
            b = occ.bounds
            edge = rng.choice(("l", "r", "b"))
            region = {"l": (b[0], b[0] + 1.3, b[2] + 1, b[3]), "r": (b[1] - 1.3, b[1], b[2] + 1, b[3]),
                      "b": (b[0], b[1], b[3] - 1.3, b[3])}[edge]
            spot = occ.find(rng, 1.1, 1.1, region, tries=30)
            if spot:
                made.append(("BUSH", spot, rng.uniform(1.6, 2.6)))
        for species, (u, v), scale in made:
            ts.species = species
            values = {n: getattr(ts, n) for n in tree_core.COPIED_PROPS}
            values["seed"] = rng.randrange(1, 100000)
            ob = tree_core.create_tree(self.ctx, values, self.at(u, v, -0.05))
            for c in list(ob.users_collection):
                c.objects.unlink(ob)
            self.c["trees"].objects.link(ob)
            ob.rotation_euler.z = rng.uniform(0, math.tau)
            ob.scale = (scale, scale, scale * rng.uniform(0.85, 1.1))
