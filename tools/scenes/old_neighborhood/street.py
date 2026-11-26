"""The street furniture of the old neighbourhood: electric poles along the roads with sagging wires between
them and a service drop to every cottage, rocks here and there, a few trees in the open ground, and the old
playground in the middle of the loop.
"""
import math
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from cs_environment_elements.core import neighborhood_materials as nm
from cs_environment_elements.props import CATALOG as PROPS

from . import terrain as tr
from .layout import FRONT, densify, polys_overlap, resample, seg_dist
from .lots import place

# the old poles (tools/props/build_electric_pole.py): height, arms (drop from the top, insulator x, sides)
XS4 = (-0.62, -0.3, 0.3, 0.62)
XS6 = (-0.66, -0.42, -0.18, 0.18, 0.42, 0.66)
POLES = {
    "pole_old_3arm": (8.0, [(0.2, XS6, (-1,)), (0.8, XS6, (-1,)), (1.4, XS4, (-1,))]),
    "pole_old_2arm_double": (8.0, [(0.2, XS4, (-1, 1)), (0.85, XS4, (-1, 1))]),
    "pole_old_2arm": (8.2, [(0.2, XS4, (-1,)), (0.85, XS4, (-1,))]),
    "pole_old_1arm": (8.4, [(0.2, XS4, (-1,))]),
}
R0, R1 = 0.13, 0.10
POLE_OFF = 5.15            # pole axis off the road centre line (between the gravel and the fences)
SPACING = 32.0


def _rad(z, h):
    return R0 + (R1 - R0) * min(max(z / h, 0), 1)


def insulators(key, matrix):
    """World positions of the wire seats, per arm (top arm first): [[(side, Vector), ...], ...]."""
    h, arms = POLES[key]
    out = []
    for dz, xs, sides in arms:
        z = h - dz
        y0 = _rad(z, h) - 0.01 + 0.036
        out.append([(sd, matrix @ Vector((x, sd * y0, z + 0.11))) for sd in sides for x in xs])
    return out


def wire_material():
    m = bpy.data.materials.get("ON_Wire")
    if m is None:
        m = bpy.data.materials.new("ON_Wire")
        m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (0.025, 0.025, 0.025, 1)
        b.inputs["Roughness"].default_value = 0.55
    return m


def tube_mesh(name, lines, radius, mat, coll, sides=4):
    """Thin tubes along 3D polylines (wires), one mesh."""
    bm = bmesh.new()
    for pts in lines:
        rings = []
        for i, p in enumerate(pts):
            t = (pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]).normalized()
            side = t.cross(Vector((0, 0, 1)))
            side = side.normalized() if side.length > 1e-6 else Vector((1, 0, 0))
            up = side.cross(t).normalized()
            rings.append([bm.verts.new(p + (side * math.cos(a) + up * math.sin(a)) * radius)
                          for a in (k * math.tau / sides for k in range(sides))])
        for r0, r1 in zip(rings[:-1], rings[1:]):
            for k in range(sides):
                bm.faces.new((r0[k], r0[(k + 1) % sides], r1[(k + 1) % sides], r1[k]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


def sag(a, b, droop, n=14):
    return [a.lerp(b, t) - Vector((0, 0, 4 * droop * t * (1 - t))) for t in np.linspace(0, 1, n)]


class Street:
    def __init__(self, ctx, terrain, net, lots, colls, seed):
        self.ctx, self.t, self.net, self.c = ctx, terrain, net, colls
        self.lots = [L for L in lots if L.ok]
        self.polys = [L.corners() for L in self.lots]
        self.rng = random.Random(seed * 7 + 3)
        self.poles = []            # dicts: key, pos (2), obj, matrix, chain
        self.taken = []            # (x, y, radius) kept clear by later pieces

    # ------------------------------------------------------------ helpers
    def _free(self, p, road=FRONT - 0.85, drive=2.2, lot_gap=0.35, clear=1.2):
        p = np.asarray(p, float)
        if seg_dist(p[None], self.net.road_seg)[0] < road:
            return False
        if len(self.net.drive_seg) and seg_dist(p[None], self.net.drive_seg)[0] < drive:
            return False
        box = np.array([p + (-0.2, -0.2), p + (0.2, -0.2), p + (0.2, 0.2), p + (-0.2, 0.2)])
        if any(polys_overlap(box, q, lot_gap) for q in self.polys):
            return False
        if self.t.water(p[None])[0]:
            return False
        return all(np.hypot(p[0] - x, p[1] - y) >= r + clear for x, y, r in self.taken)

    def at(self, p, dz=0.0):
        return Vector((p[0], p[1], self.t.z(p[0], p[1]) + dz))

    # ------------------------------------------------------------ poles + wires
    def poles_and_wires(self):
        chains = self.net.road_chains()
        anchor_x = self.net.data["anchor"][0]
        per_chain = []
        for ci, line in enumerate(chains):
            total = float(np.sum(np.linalg.norm(np.diff(line, axis=0), axis=1)))
            if total < 25:
                per_chain.append([])
                continue
            if line[:, 0].max() > anchor_x - 60:
                key = "pole_old_3arm"            # the feeder from the bridge
            elif total < 70:
                key = "pole_old_1arm"
            else:
                key = "pole_old_2arm"
            n = max(1, round((total - 12) / SPACING))
            pts, tans, _ = resample(densify(line, 0.5), 0.5)
            want = [6 + k * (total - 12) / n for k in range(n + 1)]
            made = []
            for s in want:
                i0 = int(round(s / 0.5))
                got = None
                for shift in (0, 1.5, -1.5, 3, -3, 4.5, -4.5, 6, -6):
                    i = min(max(i0 + int(shift / 0.5), 0), len(pts) - 1)
                    for side in (1, -1):
                        nrm = np.array([-tans[i][1], tans[i][0]]) * side
                        p = pts[i] + nrm * POLE_OFF
                        if self._free(p, lot_gap=0.15, clear=0.5):
                            got = (p, nrm)
                            break
                    if got:
                        break
                if got:
                    made.append(self._pole(key, *got, lamp=len(self.poles) % 2 == 0, chain=ci))
            per_chain.append(made)
        spans = []
        for made in per_chain:
            spans += list(zip(made[:-1], made[1:]))
        # join the chains at their junctions: each chain end pole to the nearest pole of another chain
        ends = [m for made in per_chain if made for m in (made[0], made[-1])]
        for a in ends:
            cands = [b for b in self.poles if b["chain"] != a["chain"]]
            if not cands:
                continue
            b = min(cands, key=lambda b: np.linalg.norm(a["pos"] - b["pos"]))
            d = float(np.linalg.norm(a["pos"] - b["pos"]))
            if d < 45 and not any({id(a), id(b)} == {id(x), id(y)} for x, y in spans):
                spans.append((a, b))
        lines = []
        for a, b in spans:
            lines += self._span(a, b)
        tube_mesh("power-lines", lines, 0.007, wire_material(), self.c["street"])
        print("poles: %d, spans: %d, wires: %d" % (len(self.poles), len(spans), len(lines)))

    def _pole(self, key, p, nrm, lamp, chain):
        rot = math.atan2(nrm[1], nrm[0])          # local +X away from the road: the lamp (-X) hangs over it
        ob = place(PROPS, "POLES", key, self.at(p), rot, self.c["street"], extra=lamp)
        self.ctx.view_layer.update()
        d = dict(key=key, pos=np.asarray(p, float), obj=ob, matrix=ob.matrix_world.copy(), chain=chain)
        self.poles.append(d)
        self.taken.append((p[0], p[1], 0.4))
        return d

    def _span(self, a, b):
        ia, ib = insulators(a["key"], a["matrix"]), insulators(b["key"], b["matrix"])
        ab = b["pos"] - a["pos"]
        span = float(np.linalg.norm(ab))
        across = Vector((-ab[1], ab[0], 0)).normalized()
        droop = 0.25 + 0.012 * span
        out = []
        for arm_a, arm_b in zip(ia, ib):
            def facing(arm, other):                # a double crossarm: the bar on the span's side
                sides = {sd for sd, _ in arm}
                if len(sides) == 1:
                    return [p for _, p in arm]
                o = Vector((other[0], other[1], 0))
                best = min(sides, key=lambda s: sum(((p.to_2d().to_3d() - o).length for sd, p in arm if sd == s)))
                return [p for sd, p in arm if sd == best]
            pa = sorted(facing(arm_a, b["pos"]), key=lambda p: p.dot(across))
            pb = sorted(facing(arm_b, a["pos"]), key=lambda p: p.dot(across))
            for k, p in enumerate(pa):
                q = pb[round(k * (len(pb) - 1) / max(len(pa) - 1, 1))]
                out.append(sag(p, q, droop * self.rng.uniform(0.9, 1.15)))
        return out

    def service_drops(self, infos):
        """One twisted cable from the nearest pole to each cottage's side wall under the eaves."""
        lines = []
        for info in infos:
            if not self.poles or "root" not in info:
                continue
            c = np.array(info["center"])
            pole = min(self.poles, key=lambda p: np.linalg.norm(p["pos"] - c))
            if np.linalg.norm(pole["pos"] - c) > 48:
                continue
            root = info["root"]
            m = root.matrix_world
            to_pole = m.inverted() @ Vector((pole["pos"][0], pole["pos"][1], m.translation.z))
            sx = 1 if to_pole.x > 0 else -1
            house_pt = m @ Vector((sx * (info["W"] / 2 + 0.08), -info["D"] / 2 + 0.5, info["lift"] + 2.95))
            pm = pole["matrix"]
            toward = (house_pt.to_2d() - Vector(pole["pos"])).normalized()
            pole_pt = pm.translation + Vector((toward.x * 0.13, toward.y * 0.13, 6.2))
            span = (house_pt - pole_pt).length
            lines.append(sag(pole_pt, house_pt, 0.25 + 0.01 * span, 10))
        if lines:
            tube_mesh("service-drops", lines, 0.009, wire_material(), self.c["street"])

    # ------------------------------------------------------------ rocks
    def rocks(self, infos, count_verge=18, count_open=14):
        from cs_environment_elements.nature import rocks as rk
        for info in infos:
            for b in info.get("bins", []):
                self.taken.append((b[0], b[1], 0.6))
        rng = self.rng
        chains = [c for c in self.net.road_chains()]
        made = 0
        tries = 0
        while made < count_verge and tries < 600:           # on the verge, between the gravel and the fences
            tries += 1
            line = rng.choice(chains)
            pts, tans, _ = resample(densify(line, 1.0), 1.0)
            i = rng.randrange(len(pts))
            nrm = np.array([-tans[i][1], tans[i][0]]) * rng.choice((1, -1))
            p = pts[i] + nrm * rng.uniform(4.9, 5.4)
            if not self._free(p, road=4.75, drive=2.4, lot_gap=0.15, clear=0.6):
                continue
            group = rng.choice((1, 1, 2, 3))
            for k in range(group):
                q = p + np.array([rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9)]) * (k > 0)
                size = rng.uniform(0.35, 0.8) if k else rng.uniform(0.5, 1.0)
                self._rock(rk, q, rng.choice(("BOULDER", "BOULDER", "BOULDER", "JAGGED")), size)
            self.taken.append((p[0], p[1], 1.0))
            made += 1
        made = tries = 0
        lo = np.min([q.min(0) for q in self.polys], axis=0) - 15
        hi = np.max([q.max(0) for q in self.polys], axis=0) + 15
        while made < count_open and tries < 800:            # out in the open ground
            tries += 1
            p = np.array([rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])])
            if not self._free(p, road=7.5, drive=3.0, lot_gap=1.5, clear=2.0):
                continue
            kind = rng.choice(("BOULDER", "BOULDER", "SLAB", "JAGGED"))
            size = {"BOULDER": rng.uniform(0.7, 1.6), "SLAB": rng.uniform(1.0, 2.0), "JAGGED": rng.uniform(0.5, 1.0)}
            self._rock(rk, p, kind, size[kind])
            self.taken.append((p[0], p[1], 1.5))
            made += 1

    def _rock(self, rk, p, kind, size):
        spec = rk.TYPES[kind]
        values = {k: spec[k] for k in ("size", "elongation", "flatness", "roughness", "facets", "strata", "surface")}
        values.update(rock_type=kind, size=size, moss=self.rng.uniform(0.2, 0.6), seed=self.rng.randrange(1, 10 ** 6),
                      detail=3 if size < 0.9 else 4)
        ob = rk.create_rock(self.ctx, values, self.at(p, -0.08 * size))
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        self.c["rocks"].objects.link(ob)
        ob.rotation_euler.z = self.rng.uniform(0, math.tau)

    # ------------------------------------------------------------ trees in the open
    def trees(self, count=10, bushes=14):
        from cs_environment_elements.nature import core as tree_core
        rng = self.rng
        ts = self.ctx.scene.treegen
        lo = np.min([q.min(0) for q in self.polys], axis=0) - 20
        hi = np.max([q.max(0) for q in self.polys], axis=0) + 20
        for n, (want, species, gap) in enumerate(((count, ("OAK", "MAPLE", "PINE", "PINE", "MAPLE_AUTUMN"), 6.0),
                                                  (bushes, ("BUSH",), 1.0))):
            made = tries = 0
            while made < want and tries < 800:
                tries += 1
                p = np.array([rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])])
                if not self._free(p, road=9.0 if n == 0 else 6.0, drive=4.0, lot_gap=gap, clear=gap):
                    continue
                ts.species = rng.choice(species)
                values = {k: getattr(ts, k) for k in tree_core.COPIED_PROPS}
                values["seed"] = rng.randrange(1, 10 ** 5)
                ob = tree_core.create_tree(self.ctx, values, self.at(p, -0.05))
                for c in list(ob.users_collection):
                    c.objects.unlink(ob)
                self.c["trees"].objects.link(ob)
                ob.rotation_euler.z = rng.uniform(0, math.tau)
                if n == 1:
                    s = rng.uniform(1.8, 3.0)
                    ob.scale = (s, s, s * rng.uniform(0.8, 1.1))
                self.taken.append((p[0], p[1], gap))
                made += 1

    # ------------------------------------------------------------ playground in the loop
    def playground(self, w=24.0, d=15.0):
        """The old playground set on a patch of trodden earth, in the free middle of the loop."""
        loop = max(self.net.road_chains(), key=len)
        lo, hi = loop.min(0), loop.max(0)
        centre = loop.mean(0)
        best = None
        for x in np.arange(lo[0] + 10, hi[0] - 10, 2.0):
            for y in np.arange(lo[1] + 8, hi[1] - 8, 2.0):
                c = np.array([x, y])
                rect = np.array([c + (-w / 2, -d / 2), c + (w / 2, -d / 2), c + (w / 2, d / 2), c + (-w / 2, d / 2)])
                from .layout import perimeter
                per = perimeter(rect, 1.0)
                if seg_dist(per, self.net.road_seg).min() < 7 or seg_dist(per, self.net.drive_seg).min() < 3:
                    continue
                if any(polys_overlap(rect, q, 2.0) for q in self.polys):
                    continue
                score = np.linalg.norm(c - centre)
                if best is None or score < best[0]:
                    best = (score, c)
        if best is None:
            print("playground: no room in the loop")
            return
        c = best[1]
        tr.ribbon("playground-ground", densify(np.array([c + (-w / 2 + 1, 0), c + (w / 2 - 1, 0)]), 1.0),
                  self.t.height, -d / 2 + 1, d / 2 - 1, 0.015, nm.ensure("C_world_dirt"), self.c["playground"],
                  nm.uv_scale)
        rng = self.rng
        pieces = [("old_swing", (-6.5, 3.0), 0.0), ("old_slide", (1.0, 3.5), 0.0), ("old_seesaw", (7.0, 3.0), 0.1),
                  ("old_merry", (-5.0, -3.0), 0.0), ("old_sandbox", (2.5, -3.0), 0.0),
                  ("old_bench", (9.5, -4.5), math.pi / 2), ("old_bench", (-10.0, -4.0), -math.pi / 2),
                  ("old_bin", (9.6, -2.6), 0.0)]
        for key, (x, y), r in pieces:
            p = c + (x, y)
            place(PROPS, "PLAYGROUND", key, self.at(p), r + rng.uniform(-0.05, 0.05), self.c["playground"])
            self.taken.append((p[0], p[1], 1.5))
        self.taken.append((c[0], c[1], max(w, d) / 2))
        print("playground at (%.1f, %.1f)" % tuple(c))
