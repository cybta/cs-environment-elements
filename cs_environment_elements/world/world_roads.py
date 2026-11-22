"""World roads: new asphalt streets (sidewalks, kerbs, centre line, street lamps), old
dirt roads (ragged edges, wooden utility poles), the footpath and the mountain trail,
bridges wherever a road crosses water, and the shops' parking lot.

Road heights follow the terrain mesh; where a road meets water the deck runs straight
from bank to bank and a bridge is built under it (concrete for streets, timber for
dirt roads and paths).
"""

import math

import numpy as np

from . import world_layout as wl
from . import world_materials as wm
from .world_mesh import Parts, linked_copy, normals

KERB = 0.12             # sidewalk top above the road
LIFT = {"NEW": 0.03, "OLD": 0.035, "PATH": 0.06, "TRAIL": 0.1}


def _clear_of_others(road, others, pts, pad):
    """True for each point that is outside every other road's carriageway (+pad)."""
    keep = np.ones(len(pts), bool)
    for o in others:
        if o is road or o.kind == "TRAIL":
            continue
        keep &= wl.seg_dist(pts, o.loop_pts()) > o.hw + pad
    return keep


def road_heights(T, road):
    """Height of the road surface at each centre point, and the bridge spans (i0, i1)."""
    pts = road.pts
    z = T.sample(pts).astype(float)
    wet = z < wl.WATER_Z + 1.0
    spans = []
    i, n = 0, len(pts)
    while i < n:
        if wet[i]:
            j = i
            while j + 1 < n and wet[j + 1]:
                j += 1
            a, b = max(i - 3, 0), min(j + 3, n - 1)
            za, zb = max(z[a], wl.WATER_Z + 1.0), max(z[b], wl.WATER_Z + 1.0)
            z[a:b + 1] = np.linspace(za, zb, b - a + 1)
            spans.append((a, b))
            i = j + 1
        else:
            i += 1
    return z + LIFT[road.kind] + road.z_bias, spans


def build(L, T, coll, rng, lib):
    """Every road, bridge, lamp and pole. Returns {'lamps': [...], 'poles': [...]}."""
    m = {k: wm.ensure(k) for k in ("C_asphalt", "C_sidewalk", "C_curb", "C_world_line", "C_world_gravel",
                                    "C_world_dirt", "C_world_concrete", "C_world_timber", "C_world_steel",
                                    "C_world_lamp", "C_world_old_concrete")}
    roads = L.roads
    asphalt, kerbs, lines = Parts(), Parts(), Parts()
    dirt = Parts()
    bridges = Parts()
    placements = {"lamps": [], "poles": []}
    lamp_src = _lamp_mesh(lib, m)
    pole_src = _pole_mesh(lib, m)

    for road in roads:
        pts = road.loop_pts() if road.closed else road.pts
        z, spans = road_heights(T, road) if not road.closed else (None, [])
        if road.closed:
            z = T.sample(road.pts).astype(float) + LIFT[road.kind]
            pts = road.pts
        nrm = normals(pts, road.closed)
        L.bridges += [(road, a, b) for a, b in spans]
        mid = (pts + np.roll(pts, -1, 0)) / 2 if road.closed else (pts[:-1] + pts[1:]) / 2

        if road.kind == "NEW":
            asphalt.ribbon(pts, z, -road.hw, road.hw, m["C_asphalt"], closed=road.closed)
            # Sidewalks + kerbs, dropped where they would run across another street
            for side in (1, -1):
                probe = mid + normals(mid) * side * (road.hw + road.sidewalk / 2)
                keep = _clear_of_others(road, roads, probe, 0.4)
                o0, o1 = (road.hw, road.outer) if side > 0 else (-road.outer, -road.hw)
                zt = z + KERB
                kerbs.ribbon(pts, zt, o0, o1, m["C_sidewalk"], keep=keep)
                edge = road.hw * side
                kerbs.wall(pts, z - 0.02, zt, edge, m["C_curb"], keep=keep, flip=side < 0)
                kerbs.wall(pts, z - 0.3, zt, road.outer * side, m["C_curb"], keep=keep, flip=side > 0)
            # Dashed centre line, kept out of junctions
            keep = _clear_of_others(road, roads, mid, 8.0)
            s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
            dash = ((s[:-1] % 9.0) < 3.0) & keep
            lines.ribbon(pts, z + 0.004, -0.07, 0.07, m["C_world_line"], keep=dash)
            # Street lamps, alternating sides
            k = 0
            for i in range(8, len(pts) - 8, 16):
                side = 1 if k % 2 else -1
                k += 1
                p = pts[i] + nrm[i] * side * (road.outer - 0.45)
                if not _clear_of_others(road, roads, p[None], road.sidewalk + 1.0)[0]:
                    continue
                if any(a - 4 <= i <= b + 4 for a, b in spans):
                    continue
                ang = math.atan2(-nrm[i][1] * side, -nrm[i][0] * side)       # arm over the road
                ob = linked_copy(lamp_src, f"Lamp_{len(placements['lamps']) + 1:03d}", coll,
                                 (p[0], p[1], z[i] + KERB), ang)
                placements["lamps"].append(ob)
        elif road.kind == "OLD":
            jag0 = -road.hw - np.array([rng.uniform(-0.35, 0.45) for _ in pts])
            jag1 = road.hw + np.array([rng.uniform(-0.35, 0.45) for _ in pts])
            dirt.ribbon(pts, z, jag0, jag1, m["C_world_gravel"], closed=road.closed)
            k = 0
            for i in range(6, len(pts) - (6 if not road.closed else 0), 19):
                p = pts[i] + nrm[i] * (road.hw + 1.6)
                if not _clear_of_others(road, roads, p[None], 1.5)[0]:
                    continue
                if any(a - 3 <= i <= b + 3 for a, b in spans):
                    continue
                ob = linked_copy(pole_src, f"Pole_{len(placements['poles']) + 1:03d}", coll,
                                 (p[0], p[1], float(T.z(*p)) - 0.4),
                                 math.atan2(nrm[i][1], nrm[i][0]) + rng.uniform(-0.06, 0.06))
                ob.rotation_euler[0] = rng.uniform(-0.03, 0.03)            # old poles lean a little
                placements["poles"].append(ob)
                k += 1
        else:
            mat = m["C_world_dirt"] if road.kind == "TRAIL" else m["C_world_gravel"]
            # each edge follows the ground under it (the mesh is coarser than the bench),
            # except on the bridges, where the deck height rules
            nr = normals(pts)
            zl = np.maximum(T.sample(pts - nr * road.hw) + LIFT[road.kind], z - 0.3)
            zr = np.maximum(T.sample(pts + nr * road.hw) + LIFT[road.kind], z - 0.3)
            for a, b in spans:
                zl[a:b + 1] = zr[a:b + 1] = z[a:b + 1]
            dirt.ribbon(pts, (zl, zr), -road.hw, road.hw, mat)

        for a, b in spans:
            _bridge(bridges, road, pts[a:b + 1], z[a:b + 1], m)

    asphalt.build("Roads_Asphalt", coll)
    kerbs.build("Roads_Sidewalks", coll)
    lines.build("Roads_Markings", coll)
    dirt.build("Roads_Dirt", coll)
    bridges.build("Bridges", coll)
    _parking(L, T, coll, m)
    return placements


# --------------------------------------------------------------------------
# Bridges
# --------------------------------------------------------------------------

def _bridge(P, road, pts, z, m):
    nrm = normals(pts)
    n = len(pts)
    if road.kind == "NEW":
        w = road.outer + 0.35                       # deck reaches past the sidewalks
        P.ribbon(pts, z - 0.7, w, -w, m["C_world_concrete"])           # soffit (faces down)
        P.wall(pts, z - 0.7, z + KERB, w, m["C_world_concrete"], flip=True)
        P.wall(pts, z - 0.7, z + KERB, -w, m["C_world_concrete"])
        for side in (1, -1):                        # parapets
            o = side * (road.outer + 0.15)
            for i in range(n - 1):
                a = pts[i] + nrm[i] * o
                b = pts[i + 1] + nrm[i + 1] * o
                P.seg_box(a, b, 0.4, z[i] + KERB, z[i] + KERB + 0.95, m["C_world_concrete"])
        mid = n // 2                               # one pier mid-river, two abutments
        for i in (0, mid, n - 1):
            c = pts[i]
            ang = math.atan2(nrm[i][1], nrm[i][0])
            P.box((c[0], c[1], (wl.WATER_Z - 3.0 + z[i] - 0.7) / 2), (2 * w, 1.2, z[i] - 0.7 - wl.WATER_Z + 3.0),
                  ang, m["C_world_concrete"])
    else:
        w = road.hw + 0.3
        P.ribbon(pts, z + 0.06, -w, w, m["C_world_timber"])
        P.ribbon(pts, z - 0.25, w, -w, m["C_world_timber"])
        P.wall(pts, z - 0.25, z + 0.06, w, m["C_world_timber"], flip=True)
        P.wall(pts, z - 0.25, z + 0.06, -w, m["C_world_timber"])
        for side in (1, -1):
            o = side * (w - 0.06)
            for i in range(0, n, 2):
                c = pts[i] + nrm[i] * o
                P.box((c[0], c[1], z[i] + 0.55), (0.1, 0.1, 1.0), math.atan2(nrm[i][1], nrm[i][0]),
                      m["C_world_timber"])
            for i in range(n - 1):
                a = pts[i] + nrm[i] * o
                b = pts[i + 1] + nrm[i + 1] * o
                P.seg_box(a, b, 0.08, z[i] + 0.95, z[i] + 1.05, m["C_world_timber"])
        for i in (0, n // 2, n - 1):               # timber trestles
            c = pts[i]
            ang = math.atan2(nrm[i][1], nrm[i][0])
            for side in (1, -1):
                q = c + nrm[i] * side * (w - 0.2)
                P.box((q[0], q[1], (wl.WATER_Z - 2.5 + z[i] - 0.25) / 2), (0.25, 0.25, z[i] - 0.25 - wl.WATER_Z + 2.5),
                      ang, m["C_world_timber"])


# --------------------------------------------------------------------------
# Street furniture (one mesh each, placed as linked copies)
# --------------------------------------------------------------------------

def _lamp_mesh(coll, m):
    """Street lamp, base at the origin, arm reaching along +X."""
    P = Parts()
    P.cylinder((0, 0), 0.13, 0.0, 0.5, m["C_world_steel"], seg=8)
    P.cylinder((0, 0), 0.08, 0.5, 7.2, m["C_world_steel"], seg=8, r_top=0.06)
    P.seg_box((0, 0), (1.6, 0), 0.07, 7.05, 7.15, m["C_world_steel"])
    P.box((1.75, 0, 7.05), (0.6, 0.26, 0.14), 0.0, m["C_world_steel"])
    P.box((1.75, 0, 6.965), (0.5, 0.2, 0.03), 0.0, m["C_world_lamp"])
    ob = P.build("World_StreetLamp", coll)
    ob.hide_viewport = ob.hide_render = True
    ob["world_library"] = True
    return ob


def _pole_mesh(coll, m):
    """Old wooden utility pole with a cross arm and insulators."""
    P = Parts()
    P.cylinder((0, 0), 0.14, 0.0, 8.6, m["C_world_timber"], seg=8, r_top=0.11)
    P.box((0, 0, 8.0), (0.12, 1.8, 0.12), 0.0, m["C_world_timber"])
    for y in (-0.75, -0.25, 0.25, 0.75):
        P.cylinder((0, y), 0.04, 8.06, 8.2, m["C_world_line"], seg=6)
    ob = P.build("World_UtilityPole", coll)
    ob.hide_viewport = ob.hide_render = True
    ob["world_library"] = True
    return ob


def _parking(L, T, coll, m):
    for z in L.zones:
        if z.kind != "PARKING":
            continue
        P = Parts()
        h = T.z(*z.c) + 0.035
        P.box((z.c[0], z.c[1], h - 0.1), (2 * z.hw, 2 * z.hd, 0.2), z.angle, m["C_asphalt"])
        # two rows of stalls facing a middle aisle, lines 0.12 m wide
        stall_w, stall_d = 2.6, 5.0
        k = int((2 * z.hw - 1.0) // stall_w)
        for row in (-1, 1):
            v_edge = row * z.hd
            v_in = v_edge - row * stall_d
            for i in range(k + 1):
                u = -z.hw + 0.5 + i * stall_w
                a, b = z.world(u, v_edge - row * 0.4), z.world(u, v_in)
                P.seg_box(a, b, 0.12, h, h + 0.006, m["C_world_line"])
        for u in (-z.hw, z.hw):                     # kerbs on the short sides
            a, b = z.world(u, -z.hd), z.world(u, z.hd)
            P.seg_box(a, b, 0.2, h - 0.1, h + KERB, m["C_curb"])
        P.build(f"{z.name}_Lot", coll)
