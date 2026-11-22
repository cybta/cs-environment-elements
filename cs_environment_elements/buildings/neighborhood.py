"""Surroundings: a richer neighbourhood built in a ring around an existing compound.

Layout, seen from the compound outwards (all sizes in metres):

    compound wall | grass verge + trees | sidewalk | ring road | sidewalk |
    big plots (house, lawn, driveway, pool) or corner parks | outer wall

Everything is built in a "canonical" frame where the gate side is +X, under
one empty that is rotated to the real gate side. The compound's access road
crosses the ring and leaves through a gap in the outer wall, where a copy of
the compound's gate (barrier down) closes the new neighbourhood.

Houses come from the house generator with the neighborhood materials; trees,
cars and street lamps are linked copies of objects already in the scene.
"""

import math
import random

import bmesh
import bpy

from ..core import ui as cs_ui
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Matrix, Vector

from . import house
from ..core import neighborhood_materials as nm

COLL_NAME = "Surroundings"

# Heights (the scene's sidewalks are 0.17 m tall, its asphalt tops out at 0.02)
Z_ROAD = 0.03
Z_SIDEWALK = 0.17
Z_CURB = 0.2
Z_LAWN = 0.12
Z_PAVING = 0.14
Z_HOUSE = 0.3          # ground-floor level of the new houses

FRONT_YARD = 9.0       # house set back from the plot front


# --------------------------------------------------------------------------
# Small geometry helpers (canonical frame, z up)
# --------------------------------------------------------------------------

def _grow(r, d):
    return (r[0] - d, r[1] - d, r[2] + d, r[3] + d)


def _ring(inner, outer, z0, z1, gap=None):
    """Boxes filling outer minus inner. `gap` = (y0, y1) cut out of the +X side."""
    ix0, iy0, ix1, iy1 = inner
    ox0, oy0, ox1, oy1 = outer
    boxes = [
        (ox0, oy0, z0, ox1, iy0, z1),          # south
        (ox0, iy1, z0, ox1, oy1, z1),          # north
        (ox0, iy0, z0, ix0, iy1, z1),          # west
    ]
    east = [(iy0, iy1)]
    if gap:
        east = [(iy0, gap[0]), (gap[1], iy1)]
    boxes += [(ix1, a, z0, ox1, b, z1) for a, b in east if b - a > 1e-3]
    return boxes


def _mesh(name, boxes):
    return house._boxes_mesh(name, boxes, Vector())


def _add(name, me, coll, parent, mat=None):
    return house._obj(name, me, coll, parent, [mat] if mat else ())


def _add_boxes(name, boxes, coll, parent, mat=None, top=None):
    """Boxes as one object; `top` gives the upward faces their own material."""
    if not boxes:
        return None
    me = _mesh(name, boxes)
    if top:
        house._paint_by_normal(me, top, mat, mat)
        return _add(name, me, coll, parent)
    return _add(name, me, coll, parent, mat)


def _cylinder(name, cx, cy, r, z0, z1, seg=40):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=seg, radius1=r, radius2=r,
                          depth=z1 - z0, matrix=Matrix.Translation((cx, cy, (z0 + z1) / 2)))
    bm.to_mesh(me)
    bm.free()
    return me


def _rot_box(name, a, b, width, z0, z1):
    """A box running from point a to point b (x, y) at any angle."""
    a, b = Vector((a[0], a[1], 0)), Vector((b[0], b[1], 0))
    d = b - a
    m = (Matrix.Translation(((a + b) / 2).to_tuple()[:2] + ((z0 + z1) / 2,)) @
         Matrix.Rotation(math.atan2(d.y, d.x), 4, "Z") @
         Matrix.Diagonal((d.length, width, z1 - z0, 1.0)))
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    bm.to_mesh(me)
    bm.free()
    return me


def _instance(src, name, coll, parent, loc, rot_z, scale=1.0):
    """Linked copy of a scene object (shares its mesh and materials)."""
    ob = src.copy()
    ob.name = name
    coll.objects.link(ob)
    ob.parent = parent
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.location = loc
    ob.rotation_euler = (0.0, 0.0, rot_z)
    ob.scale = (scale, scale, scale)
    return ob


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------

class Plot:
    """A plot facing the road. Local (u, v): u along the front, v into the plot."""

    def __init__(self, front_center, inward, width, depth):
        self.f = Vector((front_center[0], front_center[1], 0.0))
        self.d = Vector((inward[0], inward[1], 0.0))
        self.r = Vector((-inward[1], inward[0], 0.0))   # d rotated +90 degrees
        self.w, self.depth = width, depth

    def pt(self, u, v, z=0.0):
        p = self.f + self.r * u + self.d * v
        return Vector((p.x, p.y, z))

    def box(self, u0, v0, u1, v1, z0, z1):
        a, b = self.pt(u0, v0), self.pt(u1, v1)
        return (min(a.x, b.x), min(a.y, b.y), z0, max(a.x, b.x), max(a.y, b.y), z1)

    def uv(self, p):
        q = Vector((p[0], p[1], 0.0)) - self.f
        return q.dot(self.r), q.dot(self.d)

    @property
    def facing(self):
        """Angle (radians) of the direction from the plot to the road."""
        return math.atan2(-self.d.y, -self.d.x)


def _split(a, b, target):
    n = max(1, round((b - a) / target))
    step = (b - a) / n
    return [(a + i * step, a + (i + 1) * step) for i in range(n)]


def _free(u, v, blocked):
    return all(not (r[0] <= u <= r[2] and r[1] <= v <= r[3]) for r in blocked)


class Builder:
    def __init__(self, context, cfg, rng):
        self.ctx, self.cfg, self.rng = context, cfg, rng
        self.trees = [o for o in context.scene.objects if o.type == "MESH" and o.name.startswith("Tree_")]
        self.round_trees = [o for o in self.trees if o.data.name.startswith("TreeRound")] or self.trees
        self.cars = [o for o in context.scene.objects if o.type == "MESH" and o.name.startswith("Car_")]
        self.lamp = bpy.data.objects.get("Street_Lamp_01") or bpy.data.objects.get("A_street_lamp")
        self.n = 0
        self.m = {k: nm.ensure_any(k) for k in (
            "C_asphalt", "C_sidewalk", "C_curb", "C_line_white", "C_grass", "C_path", "C_stone",
            "C_water", "C_hedge_leaves", "C_compound_wall", "C_wall_cap", "C_plinth")}

    def uid(self, prefix):
        self.n += 1
        return f"SR_{prefix}_{self.n:03d}"

    def tree(self, coll, parent, x, y, round_only=False):
        pool = self.round_trees if round_only else self.trees
        if not pool:
            return
        src = self.rng.choice(pool)
        _instance(src, self.uid("Tree"), coll, parent, (x, y, 0.0),
                  self.rng.uniform(0, math.tau), self.rng.uniform(0.85, 1.25))

    # ---- one house plot --------------------------------------------------
    def plot(self, p, coll, houses_coll, parent, idx, estate=False):
        rng, m, s = self.rng, self.m, self.ctx.scene.house_gen
        name = f"SR_Plot_{idx:02d}"
        pc = bpy.data.collections.new(name)
        pc["roomgen"] = True
        coll.children.link(pc)
        hw = p.w / 2

        # House: generated with the neighbourhood materials, then turned to face the road
        s.house_name = f"{name}_House"
        s.building_type = "HOUSE"       # the plot layout below is for the plain house
        s.total_area = rng.uniform(320, 400) if estate else rng.uniform(230, 340)
        s.floors = 2
        s.bedrooms = rng.randint(4, 5)
        s.bathrooms = rng.randint(3, 4)
        s.open_plan = True
        s.seed = rng.randint(0, 99999)
        s.ceiling_height = 3.0
        s.ext_wall = 0.3
        s.roof_type = rng.choice(("HIP", "HIP", "GABLE", "GABLE", "PARAPET"))
        s.roof_pitch = rng.uniform(24, 34)
        s.roof_overhang = 0.6
        s.material_style = "NEIGHBORHOOD"
        s.facade = rng.choice(("WHITE", "WHITE", "CREAM", "GREY", "BRICK"))
        s.roof_color = rng.choice(("DARK", "DARK", "RED", "TEAL"))
        s.bath_tiles = True
        s.add_inserts, s.add_labels, s.add_lights = True, False, False
        plan = house._build(self.ctx, s, lambda *a: None)
        if plan is None:
            return
        hc = bpy.data.collections[s.house_name]
        self.ctx.scene.collection.children.unlink(hc)
        houses_coll.children.link(hc)
        root = bpy.data.objects[s.house_name]

        W, D = plan.W, plan.D
        ent = next((o for o in plan.floors[0].openings if o.kind == "ENTRANCE"), None)
        ent_angle = -math.pi / 2 if (ent is None or ent.coord < 1e-3) else math.pi / 2
        rot = p.facing - ent_angle

        side = rng.choice((-1, 1))                      # driveway side
        drive_out = W / 2 + 5.5
        u_off = -side * max(0.0, drive_out - (hw - 1.4))
        vc = FRONT_YARD + D / 2
        root.parent = parent
        root.matrix_parent_inverse = Matrix.Identity(4)
        root.location = p.pt(u_off, vc, Z_HOUSE)
        root.rotation_euler = (0, 0, rot)

        # Front door position in plot coordinates
        if ent:
            local = Vector(((ent.s0 + ent.s1) / 2 - W / 2, ent.coord - D / 2, 0))
            world = Matrix.Rotation(rot, 4, "Z") @ local + root.location
            ue, _ = p.uv(world)
        else:
            ue = u_off

        blocked = []
        house_r = (u_off - W / 2, FRONT_YARD, u_off + W / 2, FRONT_YARD + D)
        blocked.append(_grow(house_r, 2.5))

        # Lawn
        _add_boxes(f"{name}_Lawn", [p.box(-hw, 0, hw, p.depth, 0.0, Z_LAWN)], pc, parent, m["C_grass"])

        # Driveway + car, walkway + entrance step
        d0, d1 = sorted((u_off + side * (W / 2 + 1.5), u_off + side * drive_out))
        drive_len = FRONT_YARD + D * 0.85
        paving = [p.box(d0, 0, d1, drive_len, 0.0, Z_PAVING)]
        blocked.append(_grow((d0, 0, d1, drive_len), 1.5))
        walk = (ue - 0.8, 0, ue + 0.8, FRONT_YARD)
        blocked.append(_grow(walk, 1.0))
        walkway = [p.box(walk[0], 0, walk[2], FRONT_YARD - 0.05, 0.0, Z_PAVING)]
        step = [p.box(ue - 1.0, FRONT_YARD - 1.0, ue + 1.0, FRONT_YARD, 0.0, Z_HOUSE - 0.01)]
        _add_boxes(f"{name}_Driveway", paving, pc, parent, m["C_stone"])
        _add_boxes(f"{name}_Walkway", walkway, pc, parent, m["C_path"])
        _add_boxes(f"{name}_Step", step, pc, parent, m["C_plinth"])
        cars = [c for c in self.cars if c.name != "Car_13"] or self.cars
        if cars and rng.random() < 0.85:
            car = rng.choice(cars)
            # Car models run along their local X; park nose-in
            _instance(car, f"{name}_Car", pc, parent, p.pt((d0 + d1) / 2, drive_len - 3.2, Z_PAVING),
                      math.atan2(p.d.y, p.d.x))

        # Pool in the back garden
        back0, back1 = FRONT_YARD + D + 2.5, p.depth - 2.0
        if back1 - back0 >= 8.0 and rng.random() < 0.8:
            pw, pd = rng.uniform(8, 11), rng.uniform(4, 5)
            pu = max(-hw + 3 + pw / 2, min(hw - 3 - pw / 2, u_off + rng.uniform(-3, 3)))
            pv = back0 + 1.5 + pd / 2
            x0, x1, y0, y1, b = pu - pw / 2, pu + pw / 2, pv - pd / 2, pv + pd / 2, 1.5
            zd = Z_LAWN + 0.12                          # deck top; water sits just below it
            deck = [p.box(x0 - b, y0 - b, x1 + b, y0, 0, zd), p.box(x0 - b, y1, x1 + b, y1 + b, 0, zd),
                    p.box(x0 - b, y0, x0, y1, 0, zd), p.box(x1, y0, x1 + b, y1, 0, zd)]
            _add_boxes(f"{name}_PoolDeck", deck, pc, parent, m["C_path"])
            _add_boxes(f"{name}_Pool", [p.box(x0, y0, x1, y1, 0, zd - 0.06)], pc, parent, m["C_water"])
            blocked.append(_grow((x0 - b, y0 - b, x1 + b, y1 + b), 2.0))

        # Boundary: tall stucco side walls, low front wall with pillars, hedge behind it
        gaps = sorted([(d0 - 0.3, d1 + 0.3), (walk[0] - 0.3, walk[2] + 0.3)])
        merged = []
        for a, b in gaps:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        front, hedge, cur = [], [], -hw
        for a, b in merged + [(hw, hw)]:
            if a > cur + 0.05:
                front.append(p.box(cur, 0, a, 0.3, 0, 0.9))
                if a - cur > 1.5:
                    hedge.append(p.box(cur + 0.3, 0.45, a - 0.3, 1.25, 0, 1.15))
            cur = max(cur, b)
        pillars = [p.box(e - 0.25, -0.1, e + 0.25, 0.4, 0, 1.35) for a, b in merged for e in (a, b)]
        walls = front + pillars + [p.box(-hw, 0.3, -hw + 0.25, p.depth - 0.4, 0, 1.8),
                                   p.box(hw - 0.25, 0.3, hw, p.depth - 0.4, 0, 1.8)]
        _add_boxes(f"{name}_Walls", walls, pc, parent, m["C_compound_wall"], top=m["C_wall_cap"])
        _add_boxes(f"{name}_Hedge", hedge, pc, parent, m["C_hedge_leaves"])

        # Trees wherever there is lawn left
        blocked += [(-hw, 0, hw, 2.5), (-hw, 0, -hw + 2.0, p.depth), (hw - 2.0, 0, hw, p.depth),
                    (-hw, p.depth - 2.0, hw, p.depth)]
        want, tries = rng.randint(4, 7) + (3 if estate else 0), 0
        while want and tries < 200:
            tries += 1
            u, v = rng.uniform(-hw, hw), rng.uniform(0, p.depth)
            if _free(u, v, blocked):
                q = p.pt(u, v)
                self.tree(pc, parent, q.x, q.y)
                blocked.append((u - 4, v - 4, u + 4, v + 4))
                want -= 1

    # ---- corner park -------------------------------------------------------
    def park(self, rect, corner, coll, parent, idx):
        rng, m = self.rng, self.m
        name = f"SR_Park_{idx}"
        pc = bpy.data.collections.new(name)
        pc["roomgen"] = True
        coll.children.link(pc)
        x0, y0, x1, y1 = rect
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        _add_boxes(f"{name}_Lawn", [(x0, y0, 0, x1, y1, Z_LAWN)], pc, parent, m["C_grass"])
        # Path from the road corner to the fountain, and a loop around it
        _add(f"{name}_Path", _rot_box(f"{name}_Path", corner, (cx, cy), 3.0, 0, Z_PAVING), pc, parent, m["C_path"])
        _add(f"{name}_Plaza", _cylinder(f"{name}_Plaza", cx, cy, 8.0, 0, Z_PAVING + 0.005, 48), pc, parent, m["C_path"])
        _add(f"{name}_FountainRim", _cylinder(f"{name}_FountainRim", cx, cy, 4.2, 0, 0.5), pc, parent, m["C_stone"])
        _add(f"{name}_FountainWater", _cylinder(f"{name}_FountainWater", cx, cy, 3.8, 0, 0.42), pc, parent, m["C_water"])
        _add(f"{name}_FountainColumn", _cylinder(f"{name}_FountainColumn", cx, cy, 0.5, 0, 1.6, 20), pc, parent, m["C_stone"])
        # Trees, kept off the path and the plaza
        d = Vector((cx - corner[0], cy - corner[1], 0)).normalized()
        want, tries = rng.randint(10, 14), 0
        while want and tries < 300:
            tries += 1
            x, y = rng.uniform(x0 + 2.5, x1 - 2.5), rng.uniform(y0 + 2.5, y1 - 2.5)
            q = Vector((x - corner[0], y - corner[1], 0))
            off_path = (q - d * q.dot(d)).length
            if math.hypot(x - cx, y - cy) > 11 and off_path > 4.5:
                self.tree(pc, parent, x, y)
                want -= 1


# --------------------------------------------------------------------------
# Cutting the existing access-road strips where the ring road crosses them
# --------------------------------------------------------------------------

def _cut_strips(objs, to_world, x_band, y_band):
    """Remove the parts of `objs` inside the canonical band (the ring road)."""
    to_canon = to_world.inverted()
    for ob in objs:
        me = ob.data
        bm = bmesh.new()
        bm.from_mesh(me)
        mw = ob.matrix_world
        local = mw.inverted() @ to_world
        n_local = (local.to_3x3() @ Vector((1, 0, 0))).normalized()
        for x in x_band:
            co = local @ Vector((x, 0, 0))
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=n_local)
        kill = []
        for f in bm.faces:
            c = to_canon @ (mw @ f.calc_center_median())
            if x_band[0] + 1e-4 < c.x < x_band[1] - 1e-4 and y_band[0] < c.y < y_band[1]:
                kill.append(f)
        if kill:
            bmesh.ops.delete(bm, geom=kill, context="FACES")
            if not ob.name.startswith("Road_Markings"):   # close the cut ends of the kerb boxes
                bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=4)
        bm.to_mesh(me)
        bm.free()
        me.update()


# --------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------

GATE_ANGLE = {"POS_X": 0.0, "POS_Y": math.pi / 2, "NEG_X": math.pi, "NEG_Y": -math.pi / 2}


def build(context, cfg):
    from ..core.scene_utils import _delete_collection

    inner_obj = cfg.inner or bpy.data.objects.get("Compound_Wall")
    gate_obj = cfg.gate or bpy.data.objects.get("Gate_Barrier_GuardBooth")
    if inner_obj is None:
        raise RuntimeError("Pick the compound's wall (or any object that outlines the old neighbourhood)")

    old = bpy.data.collections.get(COLL_NAME)
    if old and old.get("roomgen"):
        _delete_collection(old)

    rng = random.Random(cfg.seed)
    to_world = Matrix.Rotation(GATE_ANGLE[cfg.gate_side], 4, "Z")
    to_canon = to_world.inverted()

    # Old neighbourhood outline, in the canonical frame
    pts = [to_canon @ (inner_obj.matrix_world @ Vector(c)) for c in inner_obj.bound_box]
    inner = (min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts))

    sw, road, lot = cfg.sidewalk, cfg.road_width, cfg.lot_depth
    r_in = _grow(inner, cfg.verge)            # inner edge of the ring road
    r_road = _grow(r_in, road)                # outer edge of the ring road
    r_os = _grow(r_road, sw)                  # outer edge of the outer sidewalk
    r_out = _grow(r_os, lot)                  # outer wall
    ay0, ay1 = cfg.access_center - cfg.access_half, cfg.access_center + cfg.access_half
    gap = (ay0, ay1)

    coll = bpy.data.collections.new(COLL_NAME)
    coll["roomgen"] = True
    context.scene.collection.children.link(coll)
    subs = {}
    for key in ("Roads", "Plots", "Houses", "Parks", "Walls", "Trees", "Lamps"):
        c = bpy.data.collections.new(f"{COLL_NAME}_{key}")
        c["roomgen"] = True
        coll.children.link(c)
        subs[key] = c
    root = bpy.data.objects.new(f"{COLL_NAME}_Root", None)
    root.empty_display_type = "PLAIN_AXES"
    root.matrix_world = to_world
    coll.objects.link(root)
    root["seed"] = cfg.seed

    b = Builder(context, cfg, rng)
    m = b.m

    # ---- roads -------------------------------------------------------------
    R = subs["Roads"]
    _add_boxes("SR_RingRoad", _ring(r_in, r_road, -0.02, Z_ROAD), R, root, m["C_asphalt"])
    sidewalks = _ring(_grow(r_in, -sw), r_in, 0, Z_SIDEWALK, gap) + _ring(r_road, r_os, 0, Z_SIDEWALK, gap)
    _add_boxes("SR_Sidewalks", sidewalks, R, root, m["C_sidewalk"])
    curbs = _ring(_grow(r_in, -0.18), r_in, 0, Z_CURB, gap) + _ring(r_road, _grow(r_road, 0.18), 0, Z_CURB, gap)
    _add_boxes("SR_Curbs", curbs, R, root, m["C_curb"])
    verge = _ring(inner, _grow(r_in, -sw), 0, 0.1, gap)
    _add_boxes("SR_Verge", verge, R, root, m["C_grass"])

    # Dashed centre line, broken at the corners and at the junction
    c = _grow(r_in, road / 2)
    dashes = []
    for (ax, a0, a1, fixed) in (("x", c[0], c[2], c[1]), ("x", c[0], c[2], c[3]),
                                ("y", c[1], c[3], c[0]), ("y", c[1], c[3], c[2])):
        t = a0 + road
        while t + 3 <= a1 - road:
            if not (ax == "y" and fixed == c[2] and ay0 - 4 < t + 1.5 < ay1 + 4):
                if ax == "x":
                    dashes.append((t, fixed - 0.075, Z_ROAD, t + 3, fixed + 0.075, Z_ROAD + 0.004))
                else:
                    dashes.append((fixed - 0.075, t, Z_ROAD, fixed + 0.075, t + 3, Z_ROAD + 0.004))
            t += 6
    _add_boxes("SR_RoadMarkings", dashes, R, root, m["C_line_white"])

    # Street lamps on the outer sidewalk, arms over the road
    if b.lamp:
        L = subs["Lamps"]
        lx0, ly0, lx1, ly1 = _grow(r_road, 0.6)
        runs = (((lx0, ly0), (lx1, ly0), math.pi / 2), ((lx0, ly1), (lx1, ly1), -math.pi / 2),
                ((lx0, ly0), (lx0, ly1), 0.0), ((lx1, ly0), (lx1, ly1), math.pi))
        for (sx, sy), (ex, ey), ang in runs:
            length = math.hypot(ex - sx, ey - sy)
            n = max(1, int(length // 26))
            for i in range(1, n):
                t = i / n
                x, y = sx + (ex - sx) * t, sy + (ey - sy) * t
                if ang == math.pi and ay0 - 6 < y < ay1 + 6:
                    continue
                _instance(b.lamp, b.uid("Lamp"), L, root, (x, y, Z_SIDEWALK), ang)

    # Avenue trees on the verge along the old wall
    T = subs["Trees"]
    vx0, vy0, vx1, vy1 = _grow(inner, (cfg.verge - sw) / 2)
    for (sx, sy), (ex, ey) in (((vx0, vy0), (vx1, vy0)), ((vx0, vy1), (vx1, vy1)),
                               ((vx0, vy0), (vx0, vy1)), ((vx1, vy0), (vx1, vy1))):
        length = math.hypot(ex - sx, ey - sy)
        n = max(1, int(length // 14))
        for i in range(n + 1):
            x, y = sx + (ex - sx) * i / n, sy + (ey - sy) * i / n
            if abs(x - vx1) < 1e-3 and ay0 - 9 < y < ay1 + 9:
                continue  # keep the gate clear
            b.tree(T, root, x, y, round_only=True)

    # ---- plots and parks ------------------------------------------------------
    plots = []
    ox0, oy0, ox1, oy1 = r_os
    for a, c_ in _split(ox0, ox1, cfg.plot_width):            # south and north rows
        plots.append(Plot(((a + c_) / 2, oy0), (0, -1), c_ - a, lot))
        plots.append(Plot(((a + c_) / 2, oy1), (0, 1), c_ - a, lot))
    for a, c_ in _split(oy0, oy1, cfg.plot_width):            # west row
        plots.append(Plot((ox0, (a + c_) / 2), (-1, 0), c_ - a, lot))
    for lo, hi in ((oy0, ay0 - 1.5), (ay1 + 1.5, oy1)):       # east, either side of the access road
        for a, c_ in _split(lo, hi, cfg.plot_width):
            plots.append(Plot((ox1, (a + c_) / 2), (1, 0), c_ - a, lot))
    for i, p in enumerate(plots, start=1):
        b.plot(p, subs["Plots"], subs["Houses"], root, i, estate=p.w > 45)

    X0, Y0, X1, Y1 = r_out
    corners = (((X0, Y0, ox0, oy0), (ox0, oy0)), ((ox1, Y0, X1, oy0), (ox1, oy0)),
               ((X0, oy1, ox0, Y1), (ox0, oy1)), ((ox1, oy1, X1, Y1), (ox1, oy1)))
    for i, (rect, corner) in enumerate(corners, start=1):
        b.park(rect, corner, subs["Parks"], root, i)

    # ---- outer wall and gate ------------------------------------------------
    W = subs["Walls"]
    wall_gap = (ay0 - 0.5, ay1 + 0.5)
    _add_boxes("SR_OuterWall", _ring(_grow(r_out, -0.4), r_out, 0, 3.0, wall_gap), W, root, m["C_compound_wall"])
    _add_boxes("SR_OuterWallCap", _ring(_grow(r_out, -0.45), _grow(r_out, 0.05), 3.0, 3.12, wall_gap),
               W, root, m["C_wall_cap"])
    pillars = [(X1 - 0.8, wall_gap[1], 0, X1 + 0.3, wall_gap[1] + 1.1, 3.7),
               (X1 - 0.8, wall_gap[0] - 1.1, 0, X1 + 0.3, wall_gap[0], 3.7)]
    _add_boxes("SR_GatePillars", pillars, W, root, m["C_compound_wall"], top=m["C_wall_cap"])
    if gate_obj:
        dx = X1 - inner[2]
        g = gate_obj.copy()
        g.name = "SR_Gate_Barrier_GuardBooth"
        W.objects.link(g)
        g.parent = None
        g.matrix_world = to_world @ Matrix.Translation((dx, 0, 0)) @ to_canon @ gate_obj.matrix_world

    # ---- open up the old access-road strips where the ring road crosses ------
    cut = [bpy.data.objects[n.strip()] for n in cfg.cut_objects.split(",")
           if n.strip() in bpy.data.objects and bpy.data.objects[n.strip()].type == "MESH"]
    _cut_strips(cut, to_world, (r_in[2], r_road[2]), (r_in[1], r_in[3]))

    return len(plots), len(corners)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

class SURROUND_Settings(PropertyGroup):
    inner: PointerProperty(name="Old Neighbourhood", type=bpy.types.Object,
                           description="Object outlining the existing compound (default: Compound_Wall)")
    gate: PointerProperty(name="Gate To Copy", type=bpy.types.Object,
                          description="Gate placed on the outer wall (default: Gate_Barrier_GuardBooth)")
    gate_side: EnumProperty(name="Gate Side", items=[
        ("POS_X", "+X", ""), ("NEG_X", "-X", ""), ("POS_Y", "+Y", ""), ("NEG_Y", "-Y", "")], default="POS_X")
    access_center: FloatProperty(name="Access Road Offset", default=0.0,
                                 description="Where the access road crosses the gate side, along that side")
    access_half: FloatProperty(name="Access Road Half Width", default=4.5, min=1.0,
                               description="Half the width of the access road including its sidewalks")
    seed: IntProperty(name="Seed", default=7, min=0)
    verge: FloatProperty(name="Wall to Road (m)", default=6.5, min=3.0)
    road_width: FloatProperty(name="Road Width (m)", default=8.0, min=4.0)
    sidewalk: FloatProperty(name="Sidewalk (m)", default=2.5, min=1.0)
    lot_depth: FloatProperty(name="Plot Depth (m)", default=40.0, min=25.0)
    plot_width: FloatProperty(name="Plot Width (m)", default=35.0, min=22.0)
    cut_objects: StringProperty(name="Cut Where Crossed", default="Sidewalks,Curbs,Road_Markings",
                                description="Existing road strips to open up where the ring road crosses them")


class SURROUND_OT_generate(Operator):
    bl_idname = "house_gen.surround"
    bl_label = "Build Surroundings"
    bl_description = "Ring the old neighbourhood with a road, big house plots, parks and an outer wall with a gate"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        s = context.scene.house_gen
        keep = {k: getattr(s, k) for k in s.bl_rna.properties.keys() if k not in ("rna_type", "name")}
        try:
            n_plots, n_parks = build(context, context.scene.surround_gen)
        except RuntimeError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        finally:
            for k, v in keep.items():
                try:
                    setattr(s, k, v)
                except (AttributeError, TypeError):
                    pass
        self.report({"INFO"}, f"Surroundings: {n_plots} plots, {n_parks} parks")
        return {"FINISHED"}


class SURROUND_PT_panel(Panel):
    bl_label = "Surroundings"
    bl_idname = "SURROUND_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = cs_ui.CATEGORY

    @classmethod
    def poll(cls, context):
        return cs_ui.in_section(context, "BUILDINGS")
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        c = context.scene.surround_gen
        col = self.layout.column(align=True)
        for k in ("inner", "gate", "gate_side", "access_center", "access_half", "seed",
                  "verge", "road_width", "sidewalk", "lot_depth", "plot_width", "cut_objects"):
            col.prop(c, k)
        row = self.layout.row()
        row.scale_y = 1.4
        row.operator("house_gen.surround", icon="WORLD")


classes = (SURROUND_Settings, SURROUND_OT_generate, SURROUND_PT_panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.surround_gen = PointerProperty(type=SURROUND_Settings)


def unregister():
    del bpy.types.Scene.surround_gen
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
