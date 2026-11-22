"""Makes the sofas look old and heavily used. Load AFTER bentwood_lib.py and sofa_lib.py.

build_sofa.py tags every face with a 'part' int layer (see PART_* below) while building,
then calls age_sofa(dims) right before finish(). age_sofa works on the global `bm`:

  1. densify()     triangulates the flat sweep caps and splits long upholstery edges so
                   the panels have enough vertices to bend (legs are left alone).
  2. deform        seat cushions sag where people sat (one seat much more than the
                   others), bulge at the sides, droop at the front lip, slide forward and
                   twist a little; the backrest is dented where backs leaned; arm rolls are
                   crushed at the front and the arms splay outward; the base droops between
                   the legs; everything gets lumpy, uneven stuffing.
  3. tears         a few patches switch to slot 2 'ExposedStuffing' and sink in, as if
                   the cover had torn or worn through.
  4. grime         a 'Wear' colour attribute darkens hand / head / seat / floor-kick zones.
                   The fabric material multiplies its texture by it; glTF exports it as
                   COLOR_0 (Godot: albedo from vertex colour).
Everything is seeded, so a rebuild gives the same sofa.
"""
import math, random
import bmesh, bpy
from mathutils import Vector, noise

PART_LEGS, PART_DECK, PART_CUSHION, PART_ARM, PART_DISC, PART_BACK, PART_WING = 0, 1, 10, 20, 22, 30, 40
FABRIC_SLOT, WOOD_SLOT, STUFFING_SLOT = 0, 1, 2
MAX_EDGE = 0.055         # upholstery edges longer than this get split (metres)

def part_layer():
    return bm.faces.layers.int.get("part") or bm.faces.layers.int.new("part")

def tag(faces, part):
    lay = part_layer()
    for f in faces: f[lay] = part
    return faces

def _clamp(x, a=0.0, b=1.0): return a if x < a else b if x > b else x
def _smooth(e0, e1, x):
    t = _clamp((x - e0)/(e1 - e0)); return t*t*(3 - 2*t)
def _gauss(x): return math.exp(-0.5*x*x)
def _bell(u, p=0.8): return math.sin(math.pi*_clamp(u))**p

def densify():
    fab = [f for f in bm.faces if f.material_index == FABRIC_SLOT]
    ngons = [f for f in fab if len(f.verts) > 4]
    bmesh.ops.triangulate(bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
    for _ in range(6):
        edges = [e for e in bm.edges if e.calc_length() > MAX_EDGE
                 and all(f.material_index == FABRIC_SLOT for f in e.link_faces)]
        if not edges: break
        bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
    # subdivision can leave long thin quads: split them into triangles evenly
    bm.faces.ensure_lookup_table()

def _vert_parts():
    lay = part_layer()
    vp = {}
    for f in bm.faces:
        for v in f.verts: vp[v] = f[lay]
    return vp

def age_sofa(D, seed=1):
    """D: dims from build_sofa.py (seats, chair, XI, Y0, Y1, BACK_Y0, ARM_W, ARM_H,
    LEG_H, SEAT_W, SEAT_Z0, SEAT_Z1, back_top). Ages the global bm in place."""
    rng = random.Random(seed)
    densify()
    bm.normal_update()
    vp = _vert_parts()
    orig = {v: v.co.copy() for v in bm.verts}
    nrm = {v: v.normal.copy() for v in bm.verts}
    S, chair = D["seats"], D["chair"]
    XI, Y0, Y1, ARM_H, LEG_H = D["XI"], D["Y0"], D["Y1"], D["ARM_H"], D["LEG_H"]
    Z0, Z1 = D["SEAT_Z0"], D["SEAT_Z1"]
    noise_off = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))

    # per-seat use: one favourite seat sags deeply, the others less
    fav = rng.randrange(S)
    depth = [rng.uniform(0.034, 0.048) for _ in range(S)]
    depth[fav] = rng.uniform(0.072, 0.085)
    cush = {}                                   # part -> bounds from original coords
    for v, p in vp.items():
        if PART_CUSHION <= p < PART_CUSHION + 10:
            b = cush.setdefault(p, [9, -9, 9, -9, 9, -9]); c = orig[v]
            b[0], b[1] = min(b[0], c.x), max(b[1], c.x)
            b[2], b[3] = min(b[2], c.y), max(b[3], c.y)
            b[4], b[5] = min(b[4], c.z), max(b[5], c.z)
    motion = {p: (math.radians(rng.uniform(-2.2, 2.2)), rng.uniform(-0.006, 0.006),
                  -rng.uniform(0.008, 0.028), rng.uniform(0.006, 0.018)) for p in cush}

    for v, p in vp.items():
        c, n = orig[v], nrm[v]
        d = Vector((0, 0, 0))
        if p == PART_LEGS: continue
        # ---- lumpy, uneven stuffing everywhere ----
        q = c*6.0 + noise_off
        d += n*(0.009*noise.noise(q) + 0.0035*noise.noise(q*2.7))

        if p in cush:                          # ---- seat cushions ----
            x0, x1, y0, y1, z0, z1 = cush[p]; i = p - PART_CUSHION
            u, w, t = (c.x - x0)/(x1 - x0), (c.y - y0)/(y1 - y0), (c.z - z0)/(z1 - z0)
            wv = _clamp(w*1.15) if w < 0.45 else 0.52 + (w - 0.45)*0.87   # dip sits forward
            sag = depth[i]*_bell(u)*_bell(wv, 1.0)*t**1.4
            d.z -= sag + 0.012*t                # foam has lost its loft overall
            d.z -= 0.014*(1 - _smooth(0.0, 0.22, w))*_smooth(0.3, 1.0, t)   # front lip droops
            side = Vector((n.x, n.y, 0))
            if side.length > 0.3:              # squashed foam bulges out of the sides
                d += side.normalized()*depth[i]*0.35*_bell(t, 1.0)
            # crease: the seat surface wrinkles across the dip
            d.z += 0.003*math.sin(u*math.pi*7 + i)*_bell(u)*_bell(wv)*t

        elif p == PART_BACK:                   # ---- backrest dents where backs leaned ----
            front = _clamp(-n.y*1.4)
            centres = ([0.0] if chair else [-XI + (k + 0.5)*D["SEAT_W"] for k in range(S)])
            dent = 0.0
            for k, xc in enumerate(centres):
                dk = (depth[k]/0.055)*0.030
                dent += dk*_gauss((c.x - xc)/0.17)*_gauss((c.z - (Z1 + 0.20))/0.13)
                if chair or k == fav:          # head rest spot
                    dent += 0.012*_gauss((c.x - xc)/0.11)*_gauss((c.z - (Z1 + 0.48))/0.08)
            d.y += dent*front
            # the crown has gone soft and droops a little between the arms
            d.z -= 0.012*_smooth(D["back_top"] - 0.15, D["back_top"], c.z)*_bell((c.x + XI)/(2*XI), 1.0)

        elif p in (PART_ARM, PART_ARM + 1, PART_DISC, PART_DISC + 1):   # ---- arms ----
            s = 1 if p in (PART_ARM, PART_DISC) else -1
            h = _clamp((c.z - LEG_H)/(ARM_H - LEG_H))
            d.x += s*0.013*h*h                 # frame joints loosened: arms lean out
            fr = 0.35 + 0.65*_clamp((Y1 - c.y)/(Y1 - Y0))   # more crushed at the front
            d.z -= 0.020*fr*_smooth(ARM_H - 0.10, ARM_H, c.z)
            d.x += s*0.008*fr*_smooth(ARM_H - 0.12, ARM_H - 0.03, c.z)  # roll flattens wider

        elif p == PART_DECK:                   # ---- webbing gone: base droops ----
            u = (c.x + XI)/(2*XI)
            sag = abs(math.sin(math.pi*u*(2 if S == 3 else 1)))
            d.z -= 0.009*sag*(1 - _smooth(LEG_H, LEG_H + 0.05, c.z))
            d.y -= 0.006*sag*_clamp(-n.y)*(1 - _smooth(LEG_H, Z0, c.z))  # front panel bags out

        elif p in (PART_WING, PART_WING + 1):  # ---- wings: tired and slightly drooping ----
            s = 1 if p == PART_WING else -1
            d.x += s*0.012*_smooth(0.7, 1.05, c.z)
        v.co = c + d

    # rigid moves of each cushion (slid forward, twisted, front tipped down)
    for v, p in vp.items():
        if p in motion:
            x0, x1, y0, y1, z0, z1 = cush[p]
            ang, dx, dy, tip = motion[p]
            cx, cy = (x0 + x1)/2, (y0 + y1)/2
            px, py = v.co.x - cx, v.co.y - cy
            v.co.x = cx + px*math.cos(ang) - py*math.sin(ang) + dx
            v.co.y = cy + px*math.sin(ang) + py*math.cos(ang) + dy
            v.co.z -= tip*_clamp((y1 - orig[v].y)/(y1 - y0))*_clamp((orig[v].z - z0)/(z1 - z0))

    _tears(D, rng, vp, orig, nrm)
    _grime(D, vp, orig, depth, fav, noise_off)
    bm.normal_update()
    print("aged: favourite seat", fav + 1, "sag depths", [round(x, 3) for x in depth])

def _tear_list(D):
    XI, Y0, ARM_H, ARM_W, Z1 = D["XI"], D["Y0"], D["ARM_H"], D["ARM_W"], D["SEAT_Z1"]
    arm_x = XI + ARM_W*0.5
    if D["chair"]:
        return [((PART_CUSHION,), (-0.12, Y0 - 0.01, Z1 - 0.03), (0.06, 0.04, 0.035), (0, -1, 0)),
                ((PART_ARM + 1,), (-arm_x, Y0 + 0.12, ARM_H), (0.05, 0.07, 0.05), (0, 0, 1))]
    if D["seats"] == 3:
        return [((PART_BACK,), (-0.32, 0.30, Z1 + 0.20), (0.11, 0.25, 0.075), (0, -1, 0)),
                ((PART_ARM + 1, PART_DISC + 1), (-arm_x, Y0 + 0.05, ARM_H - 0.01), (0.06, 0.07, 0.05), (0, 0, 1)),
                ((PART_CUSHION + 2,), (XI - 0.18, Y0 - 0.01, Z1 - 0.04), (0.06, 0.04, 0.03), (0, -1, 0))]
    return [((PART_BACK,), (0.34, 0.30, Z1 + 0.13), (0.03, 0.25, 0.10), (0, -1, 0)),
            ((PART_ARM, PART_DISC), (arm_x, Y0, ARM_H - 0.12), (0.07, 0.04, 0.06), (0, -1, 0))]

def _tears(D, rng, vp, orig, nrm):
    lay = part_layer()
    for parts, ctr, rad, facing in _tear_list(D):
        ctr, rad, facing = Vector(ctr), Vector(rad), Vector(facing)
        sel = set()
        for f in bm.faces:
            if f[lay] not in parts or f.material_index != FABRIC_SLOT: continue
            c = sum((orig[v] for v in f.verts), Vector())/len(f.verts)
            fn = sum((nrm[v] for v in f.verts), Vector()).normalized()
            if fn.dot(facing) < 0.25: continue
            r = Vector(((c.x - ctr.x)/rad.x, (c.y - ctr.y)/rad.y, (c.z - ctr.z)/rad.z)).length
            if r + 0.30*noise.noise(c*14) + 0.12*noise.noise(c*45) < 1.0: sel.add(f)   # ragged edge
        for f in sel: f.material_index = STUFFING_SLOT
        inner = {v for f in sel for v in f.verts if all(g in sel for g in v.link_faces)}
        for v in inner:                        # stuffing sits below the cover, lumpy
            v.co -= nrm[v]*(0.016 + 0.008*noise.noise(orig[v]*30))

def _grime(D, vp, orig, depth, fav, off):
    """Darkening 'Wear' colour per vertex: hands on arm fronts, heads/backs on the backrest,
    bottoms on the seats, shoes and the floor along the base, plus general blotches."""
    XI, Y0, Y1, ARM_H, LEG_H, Z1 = D["XI"], D["Y0"], D["Y1"], D["ARM_H"], D["LEG_H"], D["SEAT_Z1"]
    S, chair = D["seats"], D["chair"]
    cl = bm.loops.layers.color.get("Wear") or bm.loops.layers.color.new("Wear")
    dirt = (0.58, 0.50, 0.40)
    for v in bm.verts:
        p, c = vp.get(v, 0), orig[v]
        if p == PART_LEGS: g = 0.0
        elif any(f.material_index == STUFFING_SLOT for f in v.link_faces):
            inside = all(f.material_index == STUFFING_SLOT for f in v.link_faces)
            g = 0.25 if inside else 0.75                               # frayed, filthy rim
        else:
            g = 0.10*_smooth(0.3, 0.8, noise.noise(c*3 + off)*0.5 + 0.5)
            g += 0.30*(1 - _smooth(LEG_H, LEG_H + 0.14, c.z))           # floor / shoes
            if PART_CUSHION <= p < PART_CUSHION + 10:
                k = p - PART_CUSHION
                xc = -XI + (k + 0.5)*D["SEAT_W"]
                g += (0.18 + (0.22 if k == fav else 0))*_gauss((c.x - xc)/0.18) \
                     *_gauss((c.y - (Y0 + 0.25))/0.2)*_smooth(Z1 - 0.06, Z1, c.z)
                g += 0.15*_smooth(Y0 + 0.06, Y0, c.y)                   # front lip, legs rub
            elif p in (PART_ARM, PART_ARM + 1, PART_DISC, PART_DISC + 1):
                fr = _clamp((Y1 - c.y)/(Y1 - Y0))
                g += 0.45*fr*fr*_smooth(ARM_H - 0.12, ARM_H, c.z)        # hand grease
            elif p == PART_BACK:
                cs = [0.0] if chair else [-XI + (k + 0.5)*D["SEAT_W"] for k in range(S)]
                g += sum(0.35*_gauss((c.x - x)/0.14)*_gauss((c.z - (Z1 + 0.45))/0.09) for x in cs)
            elif p in (PART_WING, PART_WING + 1):
                g += 0.25*_gauss((c.z - 0.85)/0.12)                     # head leaned on wing
        g = _clamp(g, 0, 0.85)
        col = (1 - g*(1 - dirt[0]), 1 - g*(1 - dirt[1]), 1 - g*(1 - dirt[2]), 1.0)
        for l in v.link_loops: l[cl] = col

def decimate(ob, target):
    """Collapse-decimate the finished object down to about `target` triangles (keeps UVs
    and the Wear colours), then re-smooth. Legs and fabric are reduced together."""
    me = ob.data
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    if tris > target:
        mod = ob.modifiers.new("Decimate", 'DECIMATE')
        mod.ratio = target/tris; mod.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.shade_auto_smooth(angle=math.radians(80))
    print(ob.name, "decimated", tris, "->", sum(len(p.vertices) - 2 for p in ob.data.polygons), "tris")
