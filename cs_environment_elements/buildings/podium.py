"""Raised podium: lifts a house or villa onto a solid stone plinth with a terrace round it,
a flight of steps up to the entrance (and optionally the garden) and a balustrade along
the edge. Its settings are their own section of the House Generator panel.

Built by house._onto_ground once everything else is up, in the root's own coordinates
(ground at z = 0). The podium's top is where the plan's outdoor ground was, so terraces,
entrance steps, patios and the pool all stand on it.
"""

import math

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import PropertyGroup
from mathutils import Vector

from ..core import neighborhood_materials as nm
from .mesh_utils import _boxes_mesh, _clip_mesh, _obj, _paint_by_normal, _solid

TYPES = ("HOUSE", "VILLA_MODERN", "VILLA_GABLE", "VILLA_MEDITERRANEAN")
ON_GROUND = 0.3          # objects starting below this (plan z) stand on the ground: the podium goes under them
RISE, TREAD = 0.16, 0.32
CUBE = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [1, 5, 7, 3], [0, 2, 6, 4]]


class PODIUM_Settings(PropertyGroup):
    enabled: BoolProperty(name="Raised Podium", default=False,
                          description="Lift the house onto a solid stone podium with steps and a terrace round it")
    show: BoolProperty(name="Show", default=True)
    height: FloatProperty(name="Height (m)", default=1.2, min=0.3, max=4.0, step=10,
                          description="How far the podium lifts the house above the ground")
    margin: FloatProperty(name="Terrace Front/Back (m)", default=1.5, min=0.0, max=8.0, step=10,
                          description="How far the podium reaches out past the front and back walls (and the pool)")
    side_margin: FloatProperty(name="Terrace Sides (m)", default=3.5, min=0.0, max=12.0, step=10,
                               description="How far the podium reaches out past the side walls")
    pool_gap: FloatProperty(name="Pool to Steps (m)", default=3.0, min=0.5, max=12.0, step=10,
                            description="Terrace between the pool and the garden steps at the back edge")
    stair_width: FloatProperty(name="Stair Width (m)", default=3.0, min=1.0, max=12.0, step=10)
    back_stairs: BoolProperty(name="Garden Steps", default=True,
                              description="A second flight down from the back of the terrace")
    cladding: EnumProperty(name="Cladding", default="ASHLAR", items=[
        ("ASHLAR", "Ashlar", "Cut limestone blocks"),
        ("STONE", "Rustic Stone", "Rough coursed stone"),
        ("CONCRETE", "Concrete", "Plain cast stone"),
        ("FACADE", "Facade", "The same finish as the house walls"),
    ])
    edge: EnumProperty(name="Edge", default="BALUSTERS", items=[
        ("BALUSTERS", "Balustrade", "Stone balusters between piers, with a top rail"),
        ("PARAPET", "Parapet", "A low solid wall with a coping"),
        ("NONE", "Open", "No rail: just the coping"),
    ])
    rail_height: FloatProperty(name="Rail Height (m)", default=0.9, min=0.4, max=1.5, step=5)


def active(s):
    return s.building_type in TYPES and s.podium.enabled


def draw(layout, s):
    p = s.podium
    box = layout.box()
    row = box.row(align=True)
    row.prop(p, "show", text="", emboss=False, icon="TRIA_DOWN" if p.show else "TRIA_RIGHT")
    row.prop(p, "enabled")
    if not p.show:
        return
    col = box.column(align=True)
    col.enabled = p.enabled
    col.prop(p, "height")
    col.prop(p, "margin")
    col.prop(p, "side_margin")
    if s.villa_pool and s.building_type.startswith("VILLA"):
        col.prop(p, "pool_gap")
    col.prop(p, "stair_width")
    col.prop(p, "back_stairs", toggle=True)
    col.separator()
    col.prop(p, "cladding")
    col.prop(p, "edge")
    sub = col.column(align=True)
    sub.enabled = p.edge != "NONE"
    sub.prop(p, "rail_height")


# --------------------------------------------------------------------------
# Geometry in edge coordinates: a = along the edge, d = out from it (negative = on the terrace)
# --------------------------------------------------------------------------

class _Edge:
    def __init__(self, side, rect):
        x0, y0, x1, y1 = rect
        self.side = side
        self.line = {"S": y0, "N": y1, "W": x0, "E": x1}[side]
        self.span = (x0, x1) if side in "SN" else (y0, y1)
        self.out = -1.0 if side in "SW" else 1.0

    def pt(self, a, d, z):
        c = self.line + self.out * d
        return (a, c, z) if self.side in "SN" else (c, a, z)

    def box(self, a0, a1, d0, d1, z0, z1):
        (xa, ya, _), (xb, yb, _) = self.pt(a0, d0, 0), self.pt(a1, d1, 0)
        return (min(xa, xb), min(ya, yb), z0, max(xa, xb), max(ya, yb), z1)

    def wedge(self, a0, a1, d0, d1, z0, za, zb):
        """Corners for a block whose top slopes from za (at d0) to zb (at d1)."""
        return [self.pt(a, d, z) for a in (a0, a1) for d in (d0, d1) for z in (z0, za if d == d0 else zb)]


def _wedges_mesh(name, blocks):
    verts, faces = [], []
    for corners in blocks:
        # corners: a0d0lo a0d0hi a0d1lo a0d1hi a1d0lo a1d0hi a1d1lo a1d1hi -> the cube's 0..7 order
        order = [0, 1, 4, 5, 2, 3, 6, 7]
        base = len(verts)
        verts += [Vector(corners[i]) for i in order]
        faces += [[base + k for k in f] for f in CUBE]
    return _solid(name, verts, faces)


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def _materials(s, mats):
    from ..core.materials import _material
    if s.material_style == "NEIGHBORHOOD":
        clad = {"ASHLAR": "C_villa_ashlar", "STONE": "C_wall_stone", "CONCRETE": "C_stone"}.get(s.podium.cladding)
        return {"clad": nm.ensure(clad) if clad else mats["wall_out"], "coping": nm.ensure("C_villa_limestone"),
                "base": nm.ensure("C_plinth"), "paving": mats.get("paving") or nm.ensure("C_sidewalk")}
    clad = {"ASHLAR": ("RoomGen_PodiumAshlar", (0.78, 0.73, 0.63)), "STONE": ("RoomGen_PodiumStone", (0.6, 0.52, 0.42)),
            "CONCRETE": ("RoomGen_PodiumConcrete", (0.55, 0.53, 0.5))}.get(s.podium.cladding)
    return {"clad": _material(*clad) if clad else mats["wall_out"],
            "coping": _material("RoomGen_PodiumCoping", (0.82, 0.77, 0.68)),
            "base": _material("RoomGen_PodiumBase", (0.45, 0.43, 0.4)),
            "paving": mats.get("paving") or _material("RoomGen_Sidewalk", (0.62, 0.6, 0.57))}


def _bounds(obs):
    xs, ys = [], []
    for ob in obs:
        for v in ob.bound_box:
            xs.append(v[0])
            ys.append(v[1])
    return min(xs), min(ys), max(xs), max(ys)


def _entrance_side(plan, center, rect):
    """(side, middle along that edge) of the front door, in root coordinates."""
    ent = next((o for o in plan.floors[0].openings if o.kind == "ENTRANCE"), None)
    if ent is None:
        return "S", (rect[0] + rect[2]) / 2
    mid = (ent.s0 + ent.s1) / 2
    if ent.axis == "X":       # wall along X at y = coord
        return ("S" if ent.coord < plan.D / 2 else "N"), mid + center.x
    return ("W" if ent.coord < plan.W / 2 else "E"), mid + center.y


def build(s, plan, mats, coll, root, name, center, lift):
    """Everything has already been raised by `lift` (house floor + podium height)."""
    p = s.podium
    top = lift - plan.slab                     # where the plan's outdoor ground now is
    if top < 0.15:
        return
    m = _materials(s, mats)
    root["podium_height"] = round(top, 3)

    meshes = [ob for ob in coll.all_objects if ob.type == "MESH" and ob.parent == root]
    # The front planters come down off the terrace to stand beside the steps (rebuilt below)
    planters = {}
    for ob in [ob for ob in meshes if ob.name.endswith(("_Planters", "_PlanterHedges"))]:
        planters["hedge" if ob.name.endswith("Hedges") else "rim"] = ob.data.materials[0] if ob.data.materials else None
        meshes.remove(ob)
        bpy.data.objects.remove(ob)
    pool = any(ob.name.endswith("_PoolEdge") for ob in meshes)
    loose = [ob for ob in meshes if ob.name.endswith(("_Driveway", "_FrontPath"))]
    standing = [ob for ob in meshes if ob not in loose
                and min(v[2] for v in ob.bound_box) < ON_GROUND]
    if not standing:
        return
    x0, y0, x1, y1 = _bounds(standing)
    front, _ = _entrance_side(plan, center, (x0, y0, x1, y1))
    back = {"S": "N", "N": "S", "W": "E", "E": "W"}[front]
    g = {k: p.margin if k in (front, back) else p.side_margin for k in "SNWE"}
    if pool:                                   # the pool is at the back: keep it clear of the garden steps
        g[back] = max(g[back], p.pool_gap)
    rect = (x0 - g["W"], y0 - g["S"], x1 + g["E"], y1 + g["N"])
    edges = {k: _Edge(k, rect) for k in "SNWE"}

    n = max(2, round(top / RISE))
    rise, run = top / n, (n - 1) * TREAD
    rh = p.rail_height if p.edge != "NONE" else 0.15
    gaps = {k: [] for k in "SNWE"}
    cheek_t = 0.3

    # A ramp down from the terrace where the driveway was (it runs out from the front, -y)
    ramps, drives, paths = [], [], []
    e = edges["S"]
    length = top / 0.12
    for ob in loose:
        bx0, by0, bx1, by1 = _bounds([ob])
        if by1 < e.line - 0.5 or bx1 < rect[0] or bx0 > rect[2]:
            _ground(ob, lift, None, None)
        elif ob.name.endswith("_FrontPath"):
            paths.append(ob)
        else:
            ramps.append(e.wedge(bx0, bx1, -0.01, length, -0.05, top, 0.03))
            drives.append((bx0, bx1))
            gaps["S"].append((bx0, bx1))
            _ground(ob, lift, Vector((0, e.line - length, 0)), Vector((0, 1, 0)))

    # Steps up to the door, and down to the garden from the opposite edge
    front, mid = _entrance_side(plan, center, rect)
    flights = [(front, mid)]
    if p.back_stairs:
        e = edges[back]
        flights.append((back, (e.span[0] + e.span[1]) / 2))

    steps, cheeks, posts = [], [], []
    moved = False
    beside = None                                 # the front flight: (a0, a1) along its edge
    for side, a in flights:
        e = edges[side]
        w = min(p.stair_width, e.span[1] - e.span[0] - 2 * cheek_t - 0.4)
        lo, hi = e.span[0] + w / 2 + cheek_t + 0.2, e.span[1] - w / 2 - cheek_t - 0.2
        a = min(max(a, lo), hi)
        half = w / 2 + cheek_t + 0.4                  # clear of a ramp, with room for its pier
        if side == "S":
            for d0, d1 in drives:
                if a - half < d1 and a + half > d0:   # beside the ramp, on whichever side is nearer and fits
                    options = [c for c in (d0 - half, d1 + half) if lo <= c <= hi]
                    if options:
                        a = min(options, key=lambda c: abs(c - a))
                        moved = True
        a0, a1 = a - w / 2, a + w / 2
        for k in range(n - 1):
            steps.append(e.box(a0, a1, 0.0, (n - 1 - k) * TREAD, -0.05, (k + 1) * rise))
        for c0, c1 in ((a0 - cheek_t, a0), (a1, a1 + cheek_t)):
            cheeks.append(e.wedge(c0, c1, -0.01, run + 0.1, -0.05, top + rh, rh * 0.6))
            posts.append(e.box(c0 - 0.05, c1 + 0.05, run + 0.1, run + 0.1 + cheek_t + 0.1, -0.05, rh + 0.08))
        gaps[side].append((a0 - cheek_t, a1 + cheek_t))
        if beside is None:
            beside = (a0 - cheek_t, a1 + cheek_t)

    # The front path goes back on the ground up to the bottom step (the ramp is the way in
    # when the steps had to move off the path)
    e = edges["S"]
    for ob in paths:
        if moved:
            bpy.data.objects.remove(ob)
        else:
            _ground(ob, lift, Vector((0, e.line - (run if front == "S" else 0.0), 0)), Vector((0, 1, 0)))

    # The podium: the clad body right down to the ground (one material, no concrete base course:
    # user, 2026-11-26), and a coping slab paved on top
    off = Vector()
    body = [(rect[0], rect[1], -0.05, rect[2], rect[3], top - 0.08)]
    cap = [(rect[0] - 0.06, rect[1] - 0.06, top - 0.08, rect[2] + 0.06, rect[3] + 0.06, top)]
    _obj(f"{name}_Podium", _boxes_mesh(f"{name}_Podium", body, off), coll, root, [m["clad"]])
    cme = _paint_by_normal(_boxes_mesh(f"{name}_PodiumTop", cap, off), m["paving"], m["coping"], m["coping"])
    _obj(f"{name}_PodiumTop", cme, coll, root)
    _obj(f"{name}_PodiumSteps", _boxes_mesh(f"{name}_PodiumSteps", steps, off), coll, root, [m["coping"]])
    cheeks_me = _wedges_mesh(f"{name}_PodiumCheeks", cheeks)
    _obj(f"{name}_PodiumCheeks", cheeks_me, coll, root, [m["clad"]])
    _obj(f"{name}_PodiumPiers", _boxes_mesh(f"{name}_PodiumPiers", posts, off), coll, root, [m["coping"]])
    if ramps:
        _obj(f"{name}_PodiumRamp", _wedges_mesh(f"{name}_PodiumRamp", ramps), coll, root, [m["paving"]])
    if p.edge != "NONE":
        _edge(p, edges, gaps, top, rh, m, coll, root, name)
    if planters and beside:
        _planters(edges[front], beside, drives if front == "S" else [], planters, coll, root, name)


def _planters(e, flight, drives, mats, coll, root, name, gap=0.3, w=1.2, d=1.9):
    """Two raised planters with clipped hedges on the ground, one either side of the front flight,
    against the podium wall (skipped where a ramp or the podium's end is in the way)."""
    rims, tops = [], []
    for c0, c1 in ((flight[0] - gap - w, flight[0] - gap), (flight[1] + gap, flight[1] + gap + w)):
        if c0 < e.span[0] or c1 > e.span[1] or any(c0 < r1 + 0.2 and c1 > r0 - 0.2 for r0, r1 in drives):
            continue
        rims.append(e.box(c0, c1, 0.05, 0.05 + d, -0.05, 0.5))
        tops += [e.box(c0 + 0.08, c1 - 0.08, 0.13, d - 0.03, 0.5, 0.74),        # clipped, rounded off
                 e.box(c0 + 0.15, c1 - 0.15, 0.2, d - 0.1, 0.74, 0.82)]
    off = Vector()
    if rims:
        _obj(f"{name}_Planters", _boxes_mesh(f"{name}_Planters", rims, off), coll, root,
             [mats["rim"]] if mats.get("rim") else ())
        hedge = mats.get("hedge") or mats.get("rim")
        _obj(f"{name}_PlanterHedges", _boxes_mesh(f"{name}_PlanterHedges", tops, off), coll, root,
             [hedge] if hedge else ())


def _ground(ob, lift, co, no):
    """Put a path / driveway back down on the ground, cut off where the steps or ramp begin."""
    ob.location.z -= lift
    if co is not None:
        _clip_mesh(ob.data, [(co - ob.location, no)])
        if not ob.data.polygons:
            bpy.data.objects.remove(ob)


def _segments(span, gaps, pier):
    """The stretches of an edge left between its stair gaps, inset at the corners for the piers."""
    out, cur = [], span[0] + pier
    for g0, g1 in sorted(gaps):
        if g0 - cur > 0.3:
            out.append((cur, g0))
        cur = max(cur, g1)
    if span[1] - pier - cur > 0.3:
        out.append((cur, span[1] - pier))
    return out


def _edge(p, edges, gaps, top, rh, m, coll, root, name):
    pier, inset = 0.34, 0.04                    # pier size; how far the rail sits in from the coping edge
    piers, rails, balusters, walls = [], [], [], []
    d_out, d_in = -inset, -inset - pier
    mid_out, mid_in = d_out - 0.06, d_in + 0.06     # rails and walls are slimmer than the piers
    for side, e in edges.items():
        a_lo, a_hi = e.span
        for a in (a_lo, a_hi):                 # corner piers
            aa = a if a == a_lo else a - pier
            piers.append(e.box(aa, aa + pier, d_in, d_out, top, top + rh + 0.06))
        for s0, s1 in _segments(e.span, [(g0 - pier, g1 + pier) for g0, g1 in gaps[side]], pier):
            bays = max(1, math.ceil((s1 - s0) / 3.0))
            step = (s1 - s0) / bays
            for i in range(bays):
                b0, b1 = s0 + i * step, s0 + (i + 1) * step
                if i:                         # a pier between bays
                    piers.append(e.box(b0 - pier / 2, b0 + pier / 2, d_in, d_out, top, top + rh + 0.06))
                if 0 < i:
                    b0 += pier / 2
                if i < bays - 1:
                    b1 -= pier / 2
                if b1 - b0 < 0.1:
                    continue
                if p.edge == "PARAPET":
                    walls.append(e.box(b0, b1, mid_in, mid_out, top, top + rh - 0.06))
                    rails.append(e.box(b0, b1, mid_in - 0.03, mid_out + 0.03, top + rh - 0.06, top + rh))
                    continue
                rails.append(e.box(b0, b1, mid_in, mid_out, top, top + 0.12))                  # foot
                rails.append(e.box(b0, b1, mid_in - 0.03, mid_out + 0.03, top + rh - 0.08, top + rh))
                count = max(1, int((b1 - b0) / 0.26))
                gap = (b1 - b0) / count
                for k in range(count):
                    c = b0 + (k + 0.5) * gap
                    balusters.append(e.box(c - 0.055, c + 0.055, (mid_in + mid_out) / 2 - 0.055,
                                           (mid_in + mid_out) / 2 + 0.055, top + 0.12, top + rh - 0.08))
        # ends of each segment next to a stair gap get a pier too
        for g0, g1 in gaps[side]:
            for a in (g0 - pier, g1):
                if a_lo + pier < a < a_hi - 2 * pier:
                    piers.append(e.box(a, a + pier, d_in, d_out, top, top + rh + 0.06))
    off = Vector()
    _obj(f"{name}_PodiumRailPiers", _boxes_mesh(f"{name}_PodiumRailPiers", piers, off), coll, root, [m["coping"]])
    if rails:
        _obj(f"{name}_PodiumRail", _boxes_mesh(f"{name}_PodiumRail", rails, off), coll, root, [m["coping"]])
    if balusters:
        _obj(f"{name}_PodiumBalusters", _boxes_mesh(f"{name}_PodiumBalusters", balusters, off), coll, root,
             [m["coping"]])
    if walls:
        _obj(f"{name}_PodiumParapet", _boxes_mesh(f"{name}_PodiumParapet", walls, off), coll, root, [m["clad"]])
