"""The east side's ground surfaces, from the plan's geometry (east_plan.json) and the driveways as built:

- the asphalt edge is ROAD_W / 2 from any road's centreline, the sidewalk's outer edge ROAD_W / 2 + SIDEWALK from a
  street's (not the parking accesses' or the back road's), the parking is the plan's pads, and each driveway cuts
  the sidewalk 1.5 m either side of its line;
- one asphalt base under the streets, the parking and the sidewalks, and the sidewalks raised on top (WALK_TOP over
  the terrain, a 0.15 m kerb over the asphalt) with kerb faces down all their edges: both are terrain-following quads
  (CELL m) whose outline corners are then put exactly on those edges, so the kerbs run smooth;
- the driveways as 3 m paved strips from each parking place to the asphalt, through their cut in the sidewalk, and
  the 1.2 m footpaths from each front door through the fence's door to the sidewalk;
- a road end cut square (east_plan.json "flat_ends": the user's cul-de-sac) stops there, asphalt and sidewalks
  alike; its plaza ("cul_de_sacs") is paved at sidewalk height with kerbs, and `fountain_spot` stands a placeholder
  basin where the fountain goes;
- nothing over the river (the bridge spans it; the game's road meshes leave that gap too).
"""
import bmesh
import bpy
import numpy as np

from cs_environment_elements.core import neighborhood_materials as nm
from old_neighborhood import terrain as tr
from old_neighborhood.drawn import inside
from old_neighborhood.layout import densify

CELL = 0.5               # m
ASPHALT_LIFT = 0.03      # over the terrain
WALK_TOP = 0.18
KERB_FOOT = -0.05        # kerb faces reach this far into the ground
DRIVE_LIFT = 0.06
DRIVE_W = 3.0
WALK_W = 1.2             # a footpath from a front door to the street
SNAP = 0.45              # outline corners this close to an edge go onto it


def _segments(polylines, square=()):
    """Segments of polylines; `square` = {(polyline index, 0 | -1)}: ends cut square (a point past one isn't near it:
    the user's cul-de-sac, plan_east.py CUL_DE_SACS), the others round."""
    a, b, s0, s1 = [], [], [], []
    for i, p in enumerate(polylines):
        if len(p) < 2:
            continue
        n = len(p) - 1
        a.append(np.array(p[:-1], float))
        b.append(np.array(p[1:], float))
        s0 += [k == 0 and (i, 0) in square for k in range(n)]
        s1 += [k == n - 1 and (i, -1) in square for k in range(n)]
    if not a:
        return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, bool), np.zeros(0, bool)
    return np.vstack(a), np.vstack(b), np.array(s0), np.array(s1)


def _square(polylines, flat_ends):
    """east_plan.json "flat_ends" [[road, 0 | -1], ...] -> {(road, 0 | -1)}."""
    return {(int(i), -1 if int(j) == -1 else 0) for i, j in flat_ends}


def _nearest(pts, segs, chunk=4096):
    """Distance from each point to the nearest segment, and that nearest point."""
    A, B = segs[0], segs[1]
    s0, s1 = (segs[2], segs[3]) if len(segs) > 2 else (np.zeros(len(A), bool), np.zeros(len(A), bool))
    d_out = np.full(len(pts), np.inf)
    q_out = np.zeros((len(pts), 2))
    if not len(A):
        return d_out, q_out
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    for s in range(0, len(pts), chunk):
        P = pts[s:s + chunk, None, :]
        t_raw = ((P - A) * AB).sum(2) / L2
        t = np.clip(t_raw, 0, 1)
        Q = A + t[..., None] * AB
        d = np.linalg.norm(P - Q, axis=2)
        d[(s0 & (t_raw < 0)) | (s1 & (t_raw > 1))] = 1e9            # past a square end: not near it
        k = d.argmin(1)
        d_out[s:s + chunk] = d[np.arange(len(k)), k]
        q_out[s:s + chunk] = Q[np.arange(len(k)), k]
    return d_out, q_out


class Field:
    """The edges everything is cut to."""

    def __init__(self, plan, drives):
        self.ra = plan["road_width_m"] / 2
        self.rw = self.ra + plan["sidewalk_width_m"]
        self.rd = DRIVE_W / 2
        square = _square(plan["roads"], plan.get("flat_ends", []))
        self.roads = _segments(plan["roads"], square)
        walked = [i for i, w in enumerate(plan["road_sidewalks"]) if w]
        self.walk = _segments([plan["roads"][i] for i in walked],
                              {(walked.index(i), j) for i, j in square if i in walked})
        self.drives = _segments(drives)
        self.pads = [np.array(p["outline"], float) for p in plan["parking"]]
        self.pad_edges = _segments([list(p) + [p[0]] for p in self.pads])
        # a cul-de-sac's plaza: paved at sidewalk height, round its fountain
        self.plazas = [np.array(c["plaza"], float) for c in plan.get("cul_de_sacs", [])]
        self.plaza_edges = _segments([list(p) + [p[0]] for p in self.plazas])

    def classes(self, pts):
        da = _nearest(pts, self.roads)[0] - self.ra
        dw = _nearest(pts, self.walk)[0] - self.rw
        dd = _nearest(pts, self.drives)[0] - self.rd
        pad = np.zeros(len(pts), bool)
        for p in self.pads:
            pad |= inside(pts, p)
        plaza = np.zeros(len(pts), bool)
        for p in self.plazas:
            plaza |= inside(pts, p)
        asphalt = da <= 0
        zone = asphalt | (dw <= 0) | pad | plaza
        walk = ((dw <= 0) | plaza) & ~asphalt & ~pad & (dd > 0)
        return zone, walk

    def snap(self, bm, edges):
        """Boundary corners onto the nearest of the given edges ('asphalt', 'walk', 'pad', 'drive'), if close."""
        vs = [v for v in bm.verts if v.is_boundary]
        if not vs:
            return
        p = np.array([v.co[:2] for v in vs])
        best = np.full(len(p), SNAP)
        new = p.copy()
        for kind in edges:
            segs, r = {"asphalt": (self.roads, self.ra), "walk": (self.walk, self.rw),
                       "pad": (self.pad_edges, 0.0), "drive": (self.drives, self.rd),
                       "plaza": (self.plaza_edges, 0.0)}[kind]
            d, q = _nearest(p, segs)
            move = np.abs(d - r)
            out = (p - q) / np.maximum(d, 1e-9)[:, None]
            cand = q + out * r
            take = move < best
            best[take], new[take] = move[take], cand[take]
        for v, xy in zip(vs, new):
            v.co.x, v.co.y = float(xy[0]), float(xy[1])


class Grid:
    """CELL-sized cells over the plan; which cells are what."""

    def __init__(self, plan, field, terrain, margin=8.0):
        pts = np.array([q for r in plan["roads"] for q in r] + [q for p in plan["parking"] for q in p["outline"]])
        self.x0, self.y0 = pts.min(0) - margin
        x1, y1 = pts.max(0) + margin
        self.nx, self.ny = int((x1 - self.x0) / CELL) + 1, int((y1 - self.y0) / CELL) + 1
        cx = self.x0 + (np.arange(self.nx) + 0.5) * CELL
        cy = self.y0 + (np.arange(self.ny) + 0.5) * CELL
        gx, gy = np.meshgrid(cx, cy)
        c = np.stack([gx.ravel(), gy.ravel()], -1)
        zone, walk = field.classes(c)
        dry = ~terrain.water(c)
        self.zone = (zone & dry).reshape(self.ny, self.nx)
        self.walk = (walk & dry).reshape(self.ny, self.nx)

    def mesh(self, keep, smooth=2):
        """Quads for the kept cells (shared corners), the staircase outline eased a little."""
        bm = bmesh.new()
        verts = {}

        def vert(j, i):
            v = verts.get((j, i))
            if v is None:
                v = verts[(j, i)] = bm.verts.new((self.x0 + i * CELL, self.y0 + j * CELL, 0.0))
            return v

        for j, i in zip(*np.nonzero(keep)):
            bm.faces.new((vert(j, i), vert(j, i + 1), vert(j + 1, i + 1), vert(j + 1, i)))
        for _ in range(smooth):
            new = {}
            for v in bm.verts:
                if v.is_boundary:
                    nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
                    if len(nb) == 2:
                        new[v] = (v.co * 2 + nb[0].co + nb[1].co) / 4
            for v, co in new.items():
                v.co = co
        return bm


def _drape(bm, terrain, lift, verts=None):
    verts = list(bm.verts) if verts is None else verts
    z = terrain.height(np.array([v.co[:2] for v in verts])) + lift
    for v, zz in zip(verts, z):
        v.co.z = float(zz)


def _finish(bm, name, mats, coll):
    uvl = bm.loops.layers.uv.verify()
    for f in bm.faces:
        s = nm.uv_scale(mats[f.material_index])
        vertical = abs(f.normal.z) < 0.5
        for lp in f.loops:
            co = lp.vert.co
            lp[uvl].uv = ((co.x + co.y) * s, co.z * s) if vertical else (co.x * s, co.y * s)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def asphalt(grid, field, terrain, coll):
    bm = grid.mesh(grid.zone)
    field.snap(bm, ("walk", "asphalt", "pad", "plaza"))
    _drape(bm, terrain, ASPHALT_LIFT)
    bm.normal_update()
    return _finish(bm, "east-asphalt", [nm.ensure("C_asphalt")], coll)


def sidewalks(grid, field, terrain, coll):
    bm = grid.mesh(grid.walk)
    field.snap(bm, ("walk", "asphalt", "pad", "drive", "plaza"))
    _drape(bm, terrain, WALK_TOP)
    edges = [e for e in bm.edges if e.is_boundary]
    res = bmesh.ops.extrude_edge_only(bm, edges=edges)
    _drape(bm, terrain, KERB_FOOT, [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)])
    for g in res["geom"]:
        if isinstance(g, bmesh.types.BMFace):
            g.material_index = 1
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)   # consistent; then the walking surface up, kerbs out
    bm.normal_update()
    if sum(f.normal.z for f in bm.faces if f.material_index == 0) < 0:
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.normal_update()
    return _finish(bm, "east-sidewalks", [nm.ensure("C_sidewalk"), nm.ensure("C_curb")], coll)


def driveway(name, start, end, terrain, coll, mat="C_path", width=DRIVE_W, lift=DRIVE_LIFT):
    line = densify(np.array([start, end], float), 1.0)
    return tr.ribbon(name, line, terrain.height, -width / 2, width / 2, lift, nm.ensure(mat), coll, nm.uv_scale)


def walk(name, start, end, terrain, coll):
    """A footpath from a front door through the fence's door to the street's sidewalk."""
    return driveway(name, start, end, terrain, coll, mat="C_sidewalk", width=WALK_W, lift=DRIVE_LIFT - 0.01)


def fountain_spot(name, centre, r, terrain, coll, rim=0.35, wall=0.45, segs=48):
    """A placeholder where the user's fountain goes (user, 2026-11-25: "a round shape which will be a small fountain
    later"): a round stone basin standing on the plaza, water in it, a column in the middle. Replace it freely."""
    z0 = float(terrain.height([centre])[0]) + WALK_TOP
    bm = bmesh.new()
    ang = np.linspace(0, 2 * np.pi, segs, endpoint=False)

    def ring(rad, z):
        return [bm.verts.new((centre[0] + rad * np.cos(a), centre[1] + rad * np.sin(a), z)) for a in ang]

    def band(lo, hi, mat):
        for k in range(segs):
            f = bm.faces.new((lo[k], lo[(k + 1) % segs], hi[(k + 1) % segs], hi[k]))
            f.material_index = mat

    out0, out1 = ring(r, z0 - 0.05), ring(r, z0 + wall)
    in1, in0 = ring(r - rim, z0 + wall), ring(r - rim, z0 + 0.05)
    band(out0, out1, 0)                       # outside of the wall
    band(out1, in1, 0)                        # its top
    band(in1, in0, 0)                         # inside
    water = ring(r - rim, z0 + wall - 0.12)
    f = bm.faces.new(water)
    f.material_index = 1
    c0, c1 = ring(0.35, z0 + wall - 0.12), ring(0.35, z0 + 1.1)
    band(c0, c1, 0)                           # the column
    bm.faces.new(c1).material_index = 0       # and its top
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.normal_update()
    return _finish(bm, name, [nm.ensure("C_stone"), nm.ensure("C_water")], coll)
