"""Turn an outline (mesh edges or a curve: a triangle or any number of points) into an
old wooden board fence, with an optional wicket door and a double parking gate.

The fence follows the outline's points in order; "side n" is the stretch from point n
to point n+1. Boards face outwards (away from the enclosed area, or to the right of an
open run), the street face of every style. Door and gate leaves are their own
objects with the origin on the hinge line, so a game can swing them open about Z.
FenceBuilder (here: the old board fence) walks the sides and places the openings;
fence_modern.ModernBuilder reuses that for the modern style.
"""

import math
import random

import bpy
from mathutils import Matrix, Vector

from . import fence_geom as fg
from . import lod_cards

UP = Vector((0.0, 0.0, 1.0))


# --------------------------------------------------------------------------
# Outline -> ordered point chains
# --------------------------------------------------------------------------

def _chains_from_mesh(me):
    """[(vertex indices, closed)] walking the mesh's edges (only the border if it has faces)."""
    if me.polygons:
        count = {}
        for p in me.polygons:
            for ek in p.edge_keys:
                count[ek] = count.get(ek, 0) + 1
        edges = [(e.index, tuple(e.vertices)) for e in me.edges if count.get(tuple(sorted(e.vertices)), 0) == 1]
    else:
        edges = [(e.index, tuple(e.vertices)) for e in me.edges]
    adj = {}
    for ei, (a, b) in edges:
        adj.setdefault(a, []).append((ei, b, True))
        adj.setdefault(b, []).append((ei, a, False))
    used, chains = set(), []

    def walk(start):
        path, v = [start], start
        while True:
            # follow the edge's own direction first, then the oldest edge
            opts = sorted((not fwd, ei, o) for ei, o, fwd in adj[v] if ei not in used)
            if not opts:
                return path, False
            _, ei, o = opts[0]
            used.add(ei)
            if o == start:
                return path, True
            path.append(o)
            v = o

    for v in sorted(adj, key=lambda v: (len(adj[v]) != 1, v)):    # open ends first
        if any(ei not in used for ei, _, _ in adj[v]):
            path, closed = walk(v)
            if len(path) >= 2:
                chains.append((path, closed))
    return chains


def outline_chains(ob, context=None, sync_edit=True):
    """World-space point chains of an outline object -> [([Vector], closed, [vertex index])]."""
    if ob is None:
        return []
    if ob.type == "MESH":
        me = ob.data
        if ob.mode == "EDIT" and sync_edit:
            ob.update_from_editmode()
        coords = [ob.matrix_world @ v.co for v in me.vertices]
        return [([coords[i] for i in path], closed, path) for path, closed in _chains_from_mesh(me)]
    if ob.type == "CURVE":
        dg = (context or bpy.context).evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            coords = [ob.matrix_world @ v.co for v in me.vertices]
            return [([coords[i] for i in path], closed, path) for path, closed in _chains_from_mesh(me)]
        finally:
            ev.to_mesh_clear()
    return []


def shared_sides(text):
    """'3' / '2, 4' / '2 4' -> sorted side numbers (1-based) to leave out; junk is ignored."""
    out = set()
    for tok in text.replace(",", " ").replace(";", " ").split():
        if tok.isdigit() and int(tok) > 0:
            out.add(int(tok))
    return sorted(out)


def sides(chains):
    """Flat list of sides: (chain no, point a, point b, length, vertex idx a, vertex idx b)."""
    out = []
    for ci, (pts, closed, ids) in enumerate(chains):
        n = len(pts)
        for i in range(n if closed else n - 1):
            a, b = pts[i], pts[(i + 1) % n]
            out.append((ci, a, b, (b - a).xy.length, ids[i], ids[(i + 1) % n]))
    return out


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def _right(d):
    return Vector((d.y, -d.x, 0.0))


def _corner_ext(d0, n0, d1, n1, e):
    """How far the run on line offset `e` must extend past the corner point
    (end of the incoming side, start of the outgoing) so the two runs meet."""
    cr = d0.x * d1.y - d0.y * d1.x
    if abs(cr) < 1e-4:
        return 0.0, 0.0
    r = (n1 - n0) * e                                    # d0*t - d1*s = r
    t = (r.x * d1.y - r.y * d1.x) / cr
    s = (r.x * d0.y - r.y * d0.x) / cr
    return t, -s


class FenceBuilder:
    """Old board fence: posts on the line, rails on their outer face, boards outside that."""

    def __init__(self, g, chains, rng):
        self.g, self.chains, self.rng = g, chains, rng
        self.parts = fg.Parts(rng)
        self.leaves = []                      # (name, Parts, matrix)
        self.cards = []                       # LOD stand-ins for each run (see lod_cards)
        self.warnings = []
        self.off_rail = g.post_size / 2 + g.rail_thick / 2
        self.off_board = g.post_size / 2 + g.rail_thick + g.board_thick / 2
        self.skip = {n - 1 for n in shared_sides(g.skip_sides)}   # 0-based side numbers left out

    def materials(self):
        from . import fence_paint
        return [fence_paint.material(), fg.metal_material()]     # planks + paint (see fence_paint)

    def ext_offsets(self):
        """Offsets from the line whose runs get mitred at corners (see ext in _side)."""
        return (self.off_rail, self.off_board)

    MIN_RUN = 0.6           # less fence than this between two openings -> they share a post

    def opening_posts(self, kind):
        """Widths of the posts left and right of an opening (along the side)."""
        gp = self.g.post_size * 1.4
        return gp, gp

    # -- per chain -------------------------------------------------------
    def build(self, openings):
        side_no = 0
        offs = self.ext_offsets()
        for pts, closed, _ in self.chains:
            n = len(pts)
            segs = [(pts[i], pts[(i + 1) % n]) for i in range(n if closed else n - 1)]
            if not segs:
                continue
            dirs = [(b - a).xy.to_3d().normalized() if (b - a).xy.length > 1e-6 else Vector((1, 0, 0))
                    for a, b in segs]
            area = sum(a.x * b.y - b.x * a.y for a, b in segs) / 2 if closed else -1.0
            out = -1.0 if area < 0 else 1.0                  # CW loop: outside is on the left
            if not closed:
                out = 1.0
            if self.g.flip:
                out = -out
            norms = [_right(d) * out for d in dirs]
            m = len(segs)
            zero = tuple(0.0 for _ in offs)
            ext = [[zero, zero] for _ in range(m)]          # [start, end] -> one value per offset
            for i in range(m if closed else m - 1):
                j = (i + 1) % m
                ts = [_corner_ext(dirs[i], norms[i], dirs[j], norms[j], e) for e in offs]
                ext[i][1] = tuple(t for t, _ in ts)
                ext[j][0] = tuple(s for _, s in ts)
            skip = self.skip

            def skipped(i):                                  # side i of this chain left out?
                inside = closed or 0 <= i < m
                return inside and side_no + i % m in skip

            for i, (a, b) in enumerate(segs):
                if side_no + i in skip or (b - a).xy.length <= 0.05:
                    continue
                # Beside a shared side the fence ends square (no mitre round the corner), and
                # the post there is the neighbour's unless shared_posts asks for our own.
                before, after = skipped(i - 1), skipped(i + 1)
                e = [zero if before else ext[i][0], zero if after else ext[i][1]]
                first = (i == 0 and not closed and not before) or (before and self.g.shared_posts)
                self._side(a, b, dirs[i], norms[i], e, openings.get(side_no + i, []),
                           first, not after or self.g.shared_posts)
            side_no += m
        return self

    def _ground(self, a, b, s, L):
        return a.z + (b.z - a.z) * (s / L if L > 1e-6 else 0.0)

    def _frame(self, a, b, d):
        L = (b - a).xy.length
        return L, (lambda s: a.xy.to_3d() + d * s), (lambda s: self._ground(a, b, s, L))

    def place_openings(self, L, opens):
        """-> spans [(kind, centre, width, post left, post right)] and the solid runs between
        them [(from, to, starts at corner, ends at corner, post width at from, at to)];
        runs go from post centre to post centre.

        Openings that would overlap, or leave too little fence between them for a panel,
        are set side by side on one shared post (the wider of the two, so a mailbox pillar
        ends up between the door and the gate); post left = 0 marks the shared one."""
        spans = []                                          # [kind, centre, width, post left, post right]
        for kind, pos, width in sorted(opens, key=lambda o: o[1]):
            wl, wr = self.opening_posts(kind)
            lo, hi = width / 2 + wl + 0.15, L - width / 2 - wr - 0.15
            if hi < lo:
                self.warnings.append(f"side too short for the {kind.lower()} ({L:.1f} m)")
                continue
            c = min(max(pos * L, lo), hi)
            if spans:
                prev = spans[-1]
                prev_end = prev[1] + prev[2] / 2 + prev[4]      # outer face of its right post
                if c - width / 2 - wl < prev_end + self.MIN_RUN:
                    shared = max(prev[4], wl)
                    c = prev[1] + prev[2] / 2 + shared + width / 2
                    if c + width / 2 + wr + 0.15 > L:
                        self.warnings.append(f"no room for the {kind.lower()} beside the other opening")
                        continue
                    prev[4], wl = shared, 0.0
            spans.append([kind, c, width, wl, wr])
        runs, s0, w0 = [], 0.0, None
        for kind, c, width, wl, wr in spans:
            if wl > 0.0:
                c0 = c - width / 2 - wl
                runs.append((s0, c0 + wl / 2, w0 is None, False, w0, wl))
            s0, w0 = c + width / 2 + wr / 2, wr
        runs.append((s0, L, w0 is None, True, w0, None))
        return [tuple(sp) for sp in spans], runs

    def _side(self, a, b, d, n, ext, opens, first_post, last_post=True):
        g = self.g
        L, at, z = self._frame(a, b, d)
        spans, runs = self.place_openings(L, opens)

        if first_post:
            self._post(at(0), z(0), d, g.post_size, g.height)
        if last_post:
            self._post(at(L), z(L), d, g.post_size, g.height)
        for kind, c, width, wl, wr in spans:
            for s, w in ((c - width / 2 - wl / 2, wl), (c + width / 2 + wr / 2, wr)):
                if w > 0.0:                                  # 0 = shared with the opening before
                    self._post(at(s), z(s), d, w, g.height + 0.12)

        for r0, r1, at_start, at_end, w0, w1 in runs:
            bays = max(1, math.ceil((r1 - r0) / g.post_spacing - 1e-6))
            marks = [r0 + (r1 - r0) * k / bays for k in range(bays + 1)]
            for s in marks[1:-1]:
                self._post(at(s), z(s), d, g.post_size, g.height)
            # rails, one length per bay, ends trimmed to meet at corners
            for k in range(bays):
                p, q = marks[k], marks[k + 1]
                if k == 0 and at_start:
                    p -= ext[0][0]
                if k == bays - 1 and at_end:
                    q += ext[1][0]
                for h in self._rail_heights():
                    p0 = at(p) + n * self.off_rail + UP * (z(p) + h)
                    p1 = at(q) + n * self.off_rail + UP * (z(q) + h)
                    self.parts.beam(p0, p1, n, g.rail_depth, g.rail_thick)
            # boards: mitred at corners; beside an opening they run up to its edge,
            # covering the gate post from the street
            b0 = r0 - ext[0][1] if at_start else r0 - w0 / 2 + 0.01
            b1 = r1 + ext[1][1] if at_end else r1 + w1 / 2 - 0.01
            self._boards(at, z, d, n, b0, b1)
            self._card(at, z, n, b0, b1)

        for kind, c, width, wl, wr in spans:
            self._leaves(kind, at, z, d, n, c, width)
            self.leaf_card(at, z, n, c, width)

    def _card(self, at, z, n, s0, s1):
        g = self.g
        p0, p1 = (at(s) + n * self.off_board + UP * (z(s) + g.clearance) for s in (s0, s1))
        lod_cards.record(self.cards, p0, p1, g.height, 0, "upright", g.board_width + g.gap)

    def leaf_card(self, at, z, n, c, width):
        self._card(at, z, n, c - width / 2, c + width / 2)

    def _rail_heights(self):
        g = self.g
        lo, hi = g.clearance + 0.25, g.clearance + g.height - 0.25
        if g.rails == 3:
            return (lo, (lo + hi) / 2, hi)
        return (lo, hi)

    def _post(self, p, gz, d, size, height):
        self.parts.upright(p + UP * gz, d, size, size, height + self.g.clearance)

    def _boards(self, at, z, d, n, b0, b1, parts=None, base_off=None, top=None):
        g = self.g
        parts = parts or self.parts
        span = b1 - b0
        if span < 0.03:
            return
        count = max(1, round((span + g.gap) / (g.board_width + g.gap)))
        w = (span - (count - 1) * g.gap) / count
        for k in range(count):
            s = b0 + w / 2 + k * (w + g.gap)
            h = (top or g.height) + self.rng.uniform(-g.uneven, g.uneven)
            off = self.off_board if base_off is None else base_off
            base = at(s) + n * off + UP * (z(s) + g.clearance)
            parts.upright(base, d, w, g.board_thick, h)

    # -- door / gate leaves ---------------------------------------------
    def _leaves(self, kind, at, z, d, n, c, width):
        g = self.g
        if kind == "DOOR":
            hinge_left = g.door_hinge == "LEFT"
            self._leaf("Door", at, z, d, n, c, width, hinge_left, g.height - 0.05, handle=True)
        elif g.gate_leaves == 1:
            self._leaf("Gate", at, z, d, n, c, width, True, g.height, handle=True)
        else:
            self._leaf("Gate Left", at, z, d, n, c - width / 4, width / 2, True, g.height, handle=True)
            self._leaf("Gate Right", at, z, d, n, c + width / 4, width / 2, False, g.height, handle=False)

    def leaf_frame(self, at, z, d, n, c, width, hinge_at_start, off):
        """Leaf space: x from the hinge to the latch, y left of x, origin on the hinge line at
        ground level, `off` out from the fence line -> (world matrix, +1/-1 = street side is +y/-y)."""
        hs = c - width / 2 if hinge_at_start else c + width / 2
        x = d if hinge_at_start else -d
        sgn = 1.0 if n.dot(UP.cross(x)) > 0 else -1.0
        origin = at(hs) + n * off + UP * z(hs)
        return Matrix.Translation(origin) @ Matrix.Rotation(math.atan2(x.y, x.x), 4, "Z"), sgn

    def _leaf(self, name, at, z, d, n, c, width, hinge_at_start, height, handle):
        g = self.g
        mat, sgn = self.leaf_frame(at, z, d, n, c, width, hinge_at_start, self.off_board)
        p = fg.Parts(self.rng)
        lx = Vector((1, 0, 0))
        ny = Vector((0, sgn, 0))
        w = width - 0.02
        ledge_y = -sgn * (g.board_thick / 2 + g.rail_thick / 2)
        z0, z1 = g.clearance + 0.03, g.clearance + 0.03 + height - 0.04
        lo, hi = z0 + 0.2, z1 - 0.2
        # boards across the leaf
        self._boards(lambda s: lx * s, lambda s: 0.0, lx, ny, 0.01, 0.01 + w, parts=p, base_off=0.0,
                     top=height - 0.04)
        # ledges and the Z brace (rising from the hinge foot to the latch head)
        for h in (lo, hi):
            p.beam(Vector((0.04, ledge_y, h)), Vector((w - 0.02, ledge_y, h)), ny, g.rail_depth, g.rail_thick)
        p.beam(Vector((0.1, ledge_y, lo + g.rail_depth / 2)), Vector((w - 0.12, ledge_y, hi - g.rail_depth / 2)),
               ny, g.rail_depth, g.rail_thick)
        # iron: strap hinges over the ledges, a ring handle + latch at the free edge
        iy = ledge_y - sgn * (g.rail_thick / 2 + 0.003)
        for h in (lo, hi):
            p.box(Vector((0.2, iy, h)), lx, UP, 0.4, 0.04, 0.006, mat=1)
            p.box(Vector((-0.012, ledge_y, h)), UP, lx, 0.12, 0.03, 0.03, mat=1)  # knuckle
        if handle:
            hy = sgn * (g.board_thick / 2 + 0.02)
            hz = g.clearance + min(1.0, height * 0.55)
            p.box(Vector((w - 0.1, hy, hz)), UP, lx, 0.16, 0.025, 0.02, mat=1)
            p.box(Vector((w - 0.08, iy, hz + 0.05)), lx, UP, 0.22, 0.035, 0.008, mat=1)
        self.leaves.append((name, p, mat))


# --------------------------------------------------------------------------
# Objects
# --------------------------------------------------------------------------

def _delete_coll(coll):
    from ..core.scene_utils import _delete_collection
    _delete_collection(coll)


def build(context, g, outline, chains, name=None):
    """(Re)build the fence for `outline` in its own collection -> (collection, warnings).
    The outline's previous fence is replaced. `name` defaults to '<outline> Fence'."""
    from .fence_modern import ModernBuilder

    rng = random.Random(g.seed)
    side_list = sides(chains)
    openings = {}
    if g.door:
        openings.setdefault(g.door_side - 1, []).append(("DOOR", g.door_pos, g.door_width))
    if g.gate:
        openings.setdefault(g.gate_side - 1, []).append(("GATE", g.gate_pos, g.gate_width))
    warnings = []
    shared = shared_sides(g.skip_sides)
    for key, label in ((g.door_side, "door"), (g.gate_side, "gate")):
        if getattr(g, label) and key > len(side_list):
            warnings.append(f"no side {key} for the {label} (outline has {len(side_list)})")
        elif getattr(g, label) and key in shared:
            warnings.append(f"the {label} is on side {key}, which is shared (left out)")
    if any(k > len(side_list) for k in shared):
        warnings.append(f"no side {max(shared)} to leave out (outline has {len(side_list)})")

    cls = ModernBuilder if g.style == "MODERN" else FenceBuilder
    fb = cls(g, chains, rng).build(openings)
    warnings += fb.warnings

    name = name or f"{outline.name} Fence"
    for old in [c for c in bpy.data.collections
                if c.get("roomgen_fence") == outline.name or (c.name == name and c.get("roomgen_fence"))]:
        _delete_coll(old)
    coll = bpy.data.collections.new(name)
    coll["roomgen_fence"] = outline.name
    context.scene.collection.children.link(coll)

    mats = fb.materials()
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    coll.objects.link(root)

    def obj(label, parts, matrix=None):
        me = parts.mesh(f"{name}_{label}")
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(f"{name}_{label}", me)
        coll.objects.link(ob)
        ob.parent = root
        if matrix is not None:
            ob.matrix_world = matrix
        return ob

    obj("Fence", fb.parts)
    lod_cards.store(root, fb.cards, mats)
    for label, parts, matrix in fb.leaves:
        leaf = obj(label, parts, matrix)
        leaf["hinge"] = "Z"                      # swing about local Z to open
    if cls is FenceBuilder:                      # old wood: its paint, on every mesh (LODs get it too)
        from . import fence_paint
        fence_paint.apply(root, fence_paint.rgba(g))
    return coll, warnings
