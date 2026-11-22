"""World sites: a building on every plot (old cottages in the poor district, new houses
in the mid-range one, villas on the north road), a fence round each plot with its door
in line with the front path and its gate at the driveway, paths and driveways, and the
shopping row by the bridge.

Buildings and fences come from the addon's own generators (house._build, fence_build),
so they get their LODs like any other generated building.
"""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from ..buildings import fence_build as fb
from ..buildings import house
from . import world_layout as wl
from . import world_materials as wm
from .world_mesh import Parts


def _move_collection(coll, dest):
    for parent in [bpy.context.scene.collection] + list(bpy.data.collections):
        if coll.name in parent.children:
            parent.children.unlink(coll)
    dest.children.link(coll)


def _local_bounds(root):
    """(x0, y0, z0, x1, y1, z1) of the building's level-0 meshes in the root's frame
    (pools and other sunken parts left out of the bottom)."""
    inv = root.matrix_world.inverted()
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    zlo = np.inf
    for ob in root.children_recursive:
        if ob.type != "MESH" or ob.get("lod", 0) not in (0, None) or "_LOD" in ob.name:
            continue
        m = inv @ ob.matrix_world
        pts = np.array([tuple(m @ Vector(c)) for c in ob.bound_box])
        lo, hi = np.minimum(lo, pts.min(0)), np.maximum(hi, pts.max(0))
        if not any(k in ob.name for k in ("Pool", "Water")):
            zlo = min(zlo, pts[:, 2].min())
    return lo[0], lo[1], (zlo if np.isfinite(zlo) else lo[2]), hi[0], hi[1], hi[2]


def _front_dir(plan, building_type):
    """Unit vector (plan frame, centred) of the side the front door is on."""
    if building_type != "HOUSE":
        return (0.0, -1.0)
    ent = next((o for o in plan.floors[0].openings if o.kind == "ENTRANCE"), None)
    if ent is None:
        return (0.0, -1.0)
    span = plan.D if ent.axis == "X" else plan.W
    far = ent.coord > span / 2
    return ((0.0, 1.0 if far else -1.0) if ent.axis == "X" else (1.0 if far else -1.0, 0.0))


def _entrance_local(plan):
    """Centre of the front door in the root's (centred) frame, or None."""
    ent = next((o for o in plan.floors[0].openings if o.kind == "ENTRANCE"), None)
    if ent is None:
        return None
    m = (ent.s0 + ent.s1) / 2
    if ent.axis == "X":
        return Vector((m - plan.W / 2, ent.coord - plan.D / 2, 0.0))
    return Vector((ent.coord - plan.W / 2, m - plan.D / 2, 0.0))


# --------------------------------------------------------------------------
# Generator settings per district
# --------------------------------------------------------------------------

def _configure(s, district, rng, idx):
    s.add_labels, s.add_lights, s.add_inserts = False, False, True
    s.seed = rng.randint(0, 99999)
    if district == "POOR":
        s.building_type = "COTTAGE"
        s.cottage_style = rng.choice(("TIMBER", "PAINTED", "PAINTED"))
        s.total_area = rng.uniform(42, 72)
        s.bedrooms = rng.randint(1, 2)
        s.bathrooms = 0
        from ..core.paint import quiet
        with quiet():
            for k in ("cottage_roof", "cottage_paint", "cottage_siding"):
                setattr(s, k, "RANDOM")
            s.cottage_peel = rng.uniform(0.15, 0.55)          # how worn each cottage's paint is
            s.cottage_roof_peel = rng.uniform(0.15, 0.65)
        s.cottage_chimney = rng.random() < 0.8
    elif district == "MID":
        s.building_type = "HOUSE"
        s.floors = rng.choice((1, 2, 2))
        s.total_area = rng.uniform(110, 150) if s.floors == 1 else rng.uniform(150, 210)
        s.bedrooms = rng.randint(2, 4)
        s.bathrooms = rng.randint(1, 2)
        s.open_plan = rng.random() < 0.6
        s.ceiling_height = 2.8
        s.ext_wall = 0.25
        s.roof_type = rng.choice(("HIP", "HIP", "GABLE", "GABLE", "GABLE"))
        s.roof_pitch = rng.uniform(24, 36)
        s.roof_overhang = 0.5
        s.material_style = "NEIGHBORHOOD"
        s.facade, s.roof_color = "RANDOM", "RANDOM"
        s.bath_tiles = True
    else:
        s.building_type = "VILLA_GABLE" if idx % 2 else "VILLA_MODERN"
        s.total_area = rng.uniform(210, 290)
        s.bedrooms = rng.randint(3, 5)
        s.bathrooms = rng.randint(2, 4)
        s.villa_site = True
        s.villa_pool = rng.random() < 0.6
        s.facade, s.roof_color = "RANDOM", "RANDOM"


SETBACK = {"POOR": 5.0, "MID": 8.0, "VILLA": 7.0}


def _fence_settings(g, district, rng, number):
    g.seed = rng.randint(0, 99999)
    g.flip = False
    g.skip_sides = ""                  # shared sides here come from the open outline (Plot.shared)
    if district == "POOR":
        g.style = "OLD"
        g.height = rng.uniform(1.3, 1.8)
        g.uneven = rng.uniform(0.02, 0.06)
        g.gap = rng.uniform(0.05, 0.07)        # about half a 13 cm board
        from ..buildings.fence_paint import PALETTE, quiet
        with quiet():
            g.paint = rng.random() < 0.65      # most were painted once; some never were
            g.paint_color = rng.choice(PALETTE)[1]
            g.peel = rng.uniform(0.35, 0.85)
        g.door_width = 1.0
        g.gate_width, g.gate_leaves = 3.2, 2
    else:
        g.style = "MODERN"
        villa = district == "VILLA"
        g.height = rng.uniform(1.8, 2.1) if villa else rng.uniform(1.4, 1.8)
        g.plinth_h = rng.uniform(0.4, 0.6) if villa else rng.uniform(0.3, 0.5)
        g.pillars = "EVERY" if villa else rng.choice(("ENDS", "ENDS", "EVERY"))
        g.pillar_mat = "CONCRETE" if villa or rng.random() < 0.4 else "RENDER"
        g.infill = rng.choice(("METAL", "CEDAR")) if villa else rng.choice(("METAL", "CEDAR", "WEATHERED"))
        g.bay = 3.0
        g.mailbox, g.house_number = True, str(number)
        g.door_width = 1.1
        g.gate_width, g.gate_leaves = (4.6, 2) if villa else (3.6, rng.choice((1, 2)))


# --------------------------------------------------------------------------
# One plot
# --------------------------------------------------------------------------

class Sites:
    def __init__(self, context, L, T, colls, lib, rng, fences=True):
        self.ctx, self.L, self.T, self.colls, self.lib, self.rng = context, L, T, colls, lib, rng
        self.fences = fences
        self.yard = Parts()
        self.buildings = []           # (root, district)
        self.counts = {}
        self.m = {k: wm.ensure(k) for k in ("C_path", "C_stone", "C_world_gravel", "C_world_dirt", "C_plinth")}

    def _place_root(self, root, plan, btype, box, setback, shift=0.0):
        """Turn the building so its front faces the street and set it back from it."""
        root.location = (0, 0, 0)
        root.rotation_euler = (0, 0, 0)
        self.ctx.view_layer.update()
        x0, y0, z0, x1, y1, z1 = _local_bounds(root)
        fx, fy = _front_dir(plan, btype)
        r = -math.pi / 2 - math.atan2(fy, fx)        # local front -> plot -v
        R = Matrix.Rotation(r, 3, "Z")
        corners = [R @ Vector((x, y, 0)) for x in (x0, x1) for y in (y0, y1)]
        u0, u1 = min(c.x for c in corners), max(c.x for c in corners)
        v0, v1 = min(c.y for c in corners), max(c.y for c in corners)
        uc = shift - (u0 + u1) / 2
        vc = -box.hd + setback - v0
        p = box.world(uc, vc)
        ground = self.T.z(*p)
        root.location = (p[0], p[1], ground - z0 - 0.04)
        root.rotation_euler = (0, 0, box.angle + r)
        self.ctx.view_layer.update()
        return (uc + u0, -box.hd + setback, uc + u1, -box.hd + setback + v1 - v0), ground

    def plot(self, box, idx):
        L, rng, s = self.L, self.rng, self.ctx.scene.house_gen
        dist = box.district
        n = self.counts[dist] = self.counts.get(dist, 0) + 1
        name = f"{dist.title()}_{n:02d}"
        _configure(s, dist, rng, n)
        s.house_name = name
        plan = house._build(self.ctx, s, lambda *a: None)
        if plan is None:
            return
        root = bpy.data.objects[name]
        _move_collection(bpy.data.collections[name], self.colls[dist])

        setback = SETBACK[dist]
        room = box.w - 6.0
        shift = 0.0
        if dist == "MID":
            shift = rng.choice((-1, 1)) * min(3.5, max(0.0, room / 2 - 6.0))
        elif dist == "POOR":
            shift = rng.uniform(-1, 1) * max(0.0, room / 2 - 5.0)
        foot, ground = self._place_root(root, plan, s.building_type, box, setback, shift)
        root["world_district"] = dist
        self.buildings.append((root, dist))

        # Front door in plot coordinates
        ent = _entrance_local(plan)
        door_u = shift
        if ent is not None:
            w = root.matrix_world @ ent
            door_u, _ = box.local((w.x, w.y))
        door_u = float(np.clip(door_u, -box.hw + 1.5, box.hw - 1.5))
        z = ground + 0.03

        # Driveway / gate
        gate_u = None
        if dist == "VILLA":
            drive = next((o for o in root.children_recursive if o.name.endswith("_Driveway")), None)
            if drive is not None:
                c = drive.matrix_world @ Vector(np.mean([tuple(v) for v in drive.bound_box], 0))
                gate_u, _ = box.local((c.x, c.y))
                vdr = min(box.local(tuple(drive.matrix_world @ Vector(v))[:2])[1] for v in drive.bound_box)
                self.yard.box(tuple(box.world(gate_u, (-box.hd + vdr) / 2)) + (z - 0.02,),
                              (4.2, vdr + box.hd, 0.08), box.angle, self.m["C_stone"])
        elif dist == "MID":
            side = 1 if shift < 0 else -1
            gate_u = float(np.clip(side * (box.hw - 3.5), -box.hw + 2.5, box.hw - 2.5))
            if abs(gate_u - door_u) < 3.5:
                gate_u = door_u - side * 3.6 if abs(door_u - side * 3.6) < box.hw - 2.5 else None
            if gate_u is not None:
                v1 = foot[1] + 6.0
                self.yard.box(tuple(box.world(gate_u, (-box.hd + v1) / 2)) + (z - 0.02,),
                              (3.2, v1 + box.hd, 0.08), box.angle, self.m["C_stone"])
        elif rng.random() < 0.45:
            gate_u = float(np.clip(door_u + rng.choice((-1, 1)) * 5.0, -box.hw + 2.5, box.hw - 2.5))
            if abs(gate_u - door_u) < 3.5:
                gate_u = None

        # Front path from the fence door to the house
        walk_mat = self.m["C_world_gravel"] if dist == "POOR" else self.m["C_path"]
        v_door = foot[1]
        if v_door > -box.hd + 0.6:
            self.yard.box(tuple(box.world(door_u, (-box.hd + v_door) / 2)) + (z,),
                          (1.2 if dist == "POOR" else 1.5, v_door + box.hd, 0.06), box.angle, walk_mat)

        if self.fences:
            self._fence(box, name, dist, door_u, gate_u, ground, n)

        # Garden tree spots: behind and beside the house, off the paths
        want = {"POOR": rng.randint(1, 3), "MID": rng.randint(1, 3), "VILLA": rng.randint(4, 8)}[dist]
        for _ in range(60):
            if want == 0:
                break
            u = rng.uniform(-box.hw + 2.5, box.hw - 2.5)
            v = rng.uniform(-box.hd + 3.0, box.hd - 2.5)
            if foot[0] - 3 < u < foot[2] + 3 and foot[1] - 3 < v < foot[3] + 3:
                continue
            if abs(u - door_u) < 2.5 or (gate_u is not None and abs(u - gate_u) < 3.5 and v < foot[3]):
                continue
            if dist == "VILLA" and v > foot[3] - 2 and abs(u) < 9:          # pool and terrace
                continue
            p = box.world(u, v)
            if any(np.hypot(*(p - q[:2])) < 5.0 for q in box.trees):
                continue
            box.trees.append((p[0], p[1], dist))
            want -= 1

    def _fence(self, box, name, dist, door_u, gate_u, ground, number):
        g = self.ctx.scene.house_gen.fence
        _fence_settings(g, dist, self.rng, number)
        # Corners FL, FR, BR, BL; sides front, +u, back, -u. A side shared with the
        # neighbour is left out (the neighbour's fence stands there) and the fence runs on
        # to meet it, so the plot's fence is an open run starting just after the gap.
        hw, hd = box.hw - 0.3, box.hd - 0.3
        front = -box.hd + 0.4
        ul, ur = -hw, hw
        if box.shared == "-u":
            ul = -box.hw - 0.3
        elif box.shared == "+u":
            ur = box.hw + 0.3
        corners = [box.world(ul, front), box.world(ur, front), box.world(ur, hd), box.world(ul, hd)]
        if box.shared == "-u":
            order, front_side = [0, 1, 2, 3], 1
        elif box.shared == "+u":
            order, front_side = [2, 3, 0, 1], 3
        else:
            order, front_side = [0, 1, 2, 3], 1
        pts = [corners[i] for i in order]
        edges = [(i, i + 1) for i in range(3)] + ([] if box.shared else [(3, 0)])
        me = bpy.data.meshes.new(f"{name} Plot")
        me.from_pydata([(p[0], p[1], ground) for p in pts], edges, [])
        outline = bpy.data.objects.new(f"{name} Plot", me)
        self.lib.objects.link(outline)
        g.outline = outline

        def along_front(u):
            return float(np.clip((u - ul) / (ur - ul), 0.02, 0.98))

        g.door, g.door_side = True, front_side
        g.door_pos = along_front(door_u)
        g.mailbox_side = "RIGHT" if (gate_u is None or gate_u < door_u) else "LEFT"
        g.gate = gate_u is not None
        if g.gate:
            g.gate_side = front_side
            g.gate_pos = along_front(gate_u)
        chains = fb.outline_chains(outline, self.ctx, sync_edit=False)
        coll, _ = fb.build(self.ctx, g, outline, chains)
        for o in coll.objects:
            o["roomgen_fence_part"] = True
        _move_collection(coll, self.colls[dist])
        from ..buildings import lod_ui
        lod_ui.after_build(self.ctx, next((o for o in coll.objects if o.type == "EMPTY" and o.parent is None), None))

    # ----------------------------------------------------------------------
    def shops(self, zone):
        s = self.ctx.scene.house_gen
        s.building_type = "SHOPS"
        s.seed = self.rng.randint(0, 99999)
        s.add_labels, s.add_lights, s.add_inserts = False, False, True
        sh = s.shop
        sh.count, sh.width, sh.vary, sh.depth = 3, 6.0, True, 11.0
        sh.entrance, sh.side_windows, sh.awnings, sh.signs = "MIDDLE", True, True, True
        sh.sidewalk, sh.planters, sh.flower_boxes, sh.fittings, sh.stockrooms = True, True, True, True, True
        s.house_name = "Shops"
        plan = house._build(self.ctx, s, lambda *a: None)
        if plan is None:
            return
        root = bpy.data.objects["Shops"]
        _move_collection(bpy.data.collections["Shops"], self.colls["SHOPS"])
        # Face the nearest street: turn the zone so that its -v side looks at it
        road = self.L.road("Main Street")
        k = int(np.argmin(np.linalg.norm(road.pts - zone.c, axis=1)))
        to_road = road.pts[k] - zone.c
        to_road /= np.linalg.norm(to_road)
        box = wl.Box(zone.c, (-to_road[1], to_road[0]), zone.hw, zone.hd)     # v = -to_road
        setback = box.hd - (np.linalg.norm(road.pts[k] - zone.c) - road.outer - 0.6)
        self._place_root(root, plan, "SHOPS", box, setback)
        root["world_district"] = "SHOPS"
        self.buildings.append((root, "SHOPS"))

    def finish(self, coll):
        self.yard.build("Yards_Paths", coll)
