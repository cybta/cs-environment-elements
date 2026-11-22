"""Modern fence (after the user's references in Desktop/old furniture/fences): a low
concrete plinth, masonry pillars (stacked architectural-concrete blocks or white render),
infill panels of horizontal slats in a black steel frame (black metal, oiled cedar or
weathered timber), slatted door and gate leaves to match, and an optional mailbox
pillar by the door with the house number, a letterbox slot and an intercom.

Side walking, openings, leaf frames and the objects come from fence_build.FenceBuilder.
The panels sit on the fence line; the street face is n (outwards).
"""

import math

from mathutils import Vector

from . import fence_geom as fg
from . import lod_cards
from ..core import neighborhood_materials as nm
from .fence_build import UP, FenceBuilder

MAILBOX_W = 0.9          # the wide pillar with the number and letterbox
STEEL = 0.08             # slim steel post between panels ("Pillars: Corners & Openings")
FRAME = 0.04             # panel frame: square tube
FRAME_D = 0.06
SINK = 0.15              # plinth and pillars go this far into the ground

# Materials: architectural concrete with tie holes (cool light grey), white render,
# and a near-black for the shadow joints between blocks and the letterbox slot.
nm.RECIPES.setdefault("C_fence_concrete", dict(tex="concrete_wall_008", scale=0.5, base=(0.62, 0.62, 0.62),
                                               rough=0.85, hsv=(0.5, 0.15, 1.45)))
nm.RECIPES.setdefault("C_fence_render", dict(tex="white_stucco", scale=0.5, base=(0.9, 0.9, 0.88),
                                             rough=0.92, hsv=(0.5, 0.25, 1.25)))
nm._SPECIAL.setdefault("C_fence_shadow", lambda n: nm._new(n, (0.012, 0.012, 0.012), 0.9)[0])

M_MASON, M_STEEL, M_SLAT, M_DARK = 0, 1, 2, 3


class ModernBuilder(FenceBuilder):
    def __init__(self, g, chains, rng):
        super().__init__(g, chains, rng)
        self.P = g.pillar_size
        self.PT = min(max(self.P * 0.6, 0.18), 0.3)       # plinth thickness
        self.concrete = g.pillar_mat == "CONCRETE"

    def materials(self):
        slat = {"METAL": "C_villa_trim", "CEDAR": None, "WEATHERED": None}[self.g.infill]
        slat_mat = nm.ensure(slat) if slat else fg.wood_material(
            fg.MAT_CEDAR if self.g.infill == "CEDAR" else fg.MAT_WOOD)
        mason = "C_fence_concrete" if self.concrete else "C_fence_render"
        return [nm.ensure(mason), nm.ensure("C_villa_trim"), slat_mat, nm.ensure("C_fence_shadow")]

    def ext_offsets(self):
        return ()                                          # every corner has a pillar over the joint

    def opening_posts(self, kind):
        P = self.P
        if kind == "DOOR" and self.g.mailbox:
            return (MAILBOX_W, P) if self.g.mailbox_side == "LEFT" else (P, MAILBOX_W)
        return P, P

    # -- one side ---------------------------------------------------------
    def _side(self, a, b, d, n, ext, opens, first_post, last_post=True):
        g, P = self.g, self.P
        L, at, z = self._frame(a, b, d)
        spans, runs = self.place_openings(L, opens)
        H = g.height

        def top_at(s):          # pillars clear the panels on both sides, even on a slope
            return max(z(min(max(s + k, 0.0), L)) for k in (-g.bay, 0.0, g.bay)) + H + 0.06

        if first_post:
            self._pillar(at, z, d, n, 0.0, P, top_at(0.0))
        if last_post:
            self._pillar(at, z, d, n, L, P, top_at(L))
        toward = 1.0 if g.mailbox_side == "LEFT" else -1.0   # from the mailbox pillar to the door
        for kind, c, width, wl, wr in spans:
            for s, w in ((c - width / 2 - wl / 2, wl), (c + width / 2 + wr / 2, wr)):
                if w <= 0.0:                                  # shared with the opening before
                    continue
                self._pillar(at, z, d, n, s, w, top_at(s))
                if w == MAILBOX_W:                            # may sit between the door and the gate
                    self._mailbox(at, z, d, n, s, top_at(s), toward)

        for r0, r1, at_start, at_end, w0, w1 in runs:
            bays = max(1, math.ceil((r1 - r0) / g.bay - 1e-6))
            marks = [r0 + (r1 - r0) * k / bays for k in range(bays + 1)]
            mid_w = P if g.pillars == "EVERY" else STEEL
            widths = [P if at_start else w0] + [mid_w] * (bays - 1) + [P if at_end else w1]
            for s in marks[1:-1]:
                if g.pillars == "EVERY":
                    self._pillar(at, z, d, n, s, P, top_at(s))
                else:
                    self.parts.upright(at(s) + UP * (z(s) - SINK), d, STEEL, STEEL,
                                       top_at(s) - 0.06 - z(s) + SINK, mat=M_STEEL, uv="metric")
            for k in range(bays):
                s0, s1 = marks[k], marks[k + 1]
                zb = max(z(s0), z(s1))                   # each bay stands level, stepping down a slope
                self._plinth(at, z, n, s0, s1, zb + g.plinth_h)
                x0, x1 = s0 + widths[k] / 2, s1 - widths[k + 1] / 2
                if x1 - x0 > 0.15:
                    self._panel(self.parts, at(0), d, x0, x1, zb + g.plinth_h, zb + H)
                    self._slat_card(at(x0) + UP * (zb + g.plinth_h), at(x1) + UP * (zb + g.plinth_h),
                                    H - g.plinth_h)

        for kind, c, width, wl, wr in spans:
            self._leaves(kind, at, z, d, n, c, width)

    # -- masonry ------------------------------------------------------------
    def _blocks(self, base, d, w, depth, z0, z1, mat=M_MASON):
        """A pillar of stacked concrete blocks with dark shadow joints (or one rendered box)."""
        if not self.concrete:
            self.parts.upright(base + UP * z0, d, w, depth, z1 - z0, mat=mat, uv="metric")
            return
        count = max(2, round((z1 - z0 - SINK) / 0.62))
        gap = 0.012
        h = (z1 - z0 - (count - 1) * gap) / count
        for k in range(count):
            lo = z0 + k * (h + gap)
            self.parts.upright(base + UP * lo, d, w, depth, h, mat=mat, uv="metric")
        self.parts.upright(base + UP * z0, d, w - 0.03, depth - 0.03, z1 - z0 - 0.01, mat=M_DARK, uv="metric")

    def _pillar(self, at, z, d, n, s, w, top):
        self._blocks(at(s), d, w, self.P, z(s) - SINK, top)

    def _plinth(self, at, z, n, s0, s1, top):
        """Plinth from pillar centre to pillar centre: level on top, following the ground below,
        in ~1.2 m concrete blocks (one piece when rendered)."""
        pieces = max(1, round((s1 - s0) / 1.2)) if self.concrete else 1
        gap = 0.012 if pieces > 1 else 0.0
        step = (s1 - s0 - (pieces - 1) * gap) / pieces
        h = self.PT / 2
        for k in range(pieces):
            p0 = s0 + k * (step + gap)
            self._slab(at, z, n, p0, p0 + step, h, top)
        if pieces > 1:
            self._slab(at, z, n, s0, s1, h - 0.015, top - 0.01, mat=M_DARK)

    def _slab(self, at, z, n, s0, s1, h, top, mat=M_MASON):
        ring = [at(s0) + n * h, at(s1) + n * h, at(s1) - n * h, at(s0) - n * h]
        zs = [z(s0), z(s1), z(s1), z(s0)]
        area = sum(ring[i].x * ring[i - 3].y - ring[i - 3].x * ring[i].y for i in range(4))
        if area < 0:                                       # keep the ring counter-clockwise
            ring.reverse()
            zs.reverse()
        self.parts.prism([p.xy for p in ring], [q - SINK for q in zs], [top] * 4, mat)

    def _mailbox(self, at, z, d, n, s, top, toward):
        """House number high on the street face, letterbox slot below it, intercom by the door."""
        from .shop_extras import text_part

        g = self.g
        read = UP.cross(n)                                 # left-to-right for someone in the street
        face = at(s) + n * (self.P / 2)
        door = d * toward                                  # from the pillar towards the door
        side = 1.0 if read.dot(door) < 0 else -1.0         # number on the side away from the door
        zg = z(s)
        t = text_part(g.house_number or " ", 0.32, MAILBOX_W * 0.4)
        if t:
            verts, faces = t
            c = face + read * side * (MAILBOX_W / 2 - 0.22) + UP * (top - 0.36)
            self.parts.raw([c + read * vs + n * (vd - 0.006) + UP * vz for vs, vd, vz in verts], faces, M_STEEL)
        slot = face + read * side * 0.05 + UP * (zg + 1.0)
        self.parts.box(slot, read, UP, 0.32, 0.035, 0.01, mat=M_DARK, uv="metric")
        self.parts.box(slot + UP * 0.03 - n * 0.001, read, UP, 0.36, 0.012, 0.012, mat=M_STEEL, uv="metric")
        ic = face + door * (MAILBOX_W / 2 - 0.14) + UP * (zg + 1.35)
        self.parts.box(ic, UP, read, 0.16, 0.09, 0.025, mat=M_STEEL, uv="metric")
        self.parts.box(ic + n * 0.013 + UP * 0.03, UP, read, 0.04, 0.05, 0.002, mat=M_DARK, uv="metric")

    # -- slatted panels and leaves ------------------------------------------
    def _panel(self, parts, base, dv, x0, x1, z0, z1, hinge=False):
        """Steel frame from x0 to x1 along dv (from `base`), z0..z1, filled with level slats."""
        g = self.g
        P = lambda x, zz: base + dv * x + UP * zz         # noqa: E731
        for x in (x0 + FRAME / 2, x1 - FRAME / 2):
            parts.box(P(x, (z0 + z1) / 2), UP, dv, z1 - z0, FRAME, FRAME_D, mat=M_STEEL, uv="metric")
        for zz in (z0 + FRAME / 2, z1 - FRAME / 2):
            parts.box(P((x0 + x1) / 2, zz), dv, UP, x1 - x0 - 2 * FRAME, FRAME, FRAME_D, mat=M_STEEL, uv="metric")
        sx0, sx1 = x0 + FRAME, x1 - FRAME
        a0, a1 = z0 + FRAME, z1 - FRAME
        sh, gap = g.slat_h, g.slat_gap
        count = max(1, int((a1 - a0 - gap) // (sh + gap)))
        gap2 = (a1 - a0 - count * sh) / (count + 1)
        uv = "metric" if g.infill == "METAL" else "plank"
        thick = 0.02 if g.infill == "METAL" else 0.024
        for k in range(count):
            zc = a0 + gap2 + sh / 2 + k * (sh + gap2)
            parts.box(P((sx0 + sx1) / 2, zc), dv, UP, sx1 - sx0, sh, thick, mat=M_SLAT, uv=uv)

    def _slat_card(self, p0, p1, height):
        g = self.g
        kind = "metric" if g.infill == "METAL" else "level"
        lod_cards.record(self.cards, p0, p1, height, M_SLAT, kind, g.slat_h + g.slat_gap)

    def leaf_card(self, at, z, n, c, width):
        zc = z(c) + 0.05
        self._slat_card(at(c - width / 2) + UP * zc, at(c + width / 2) + UP * zc, self.g.height - 0.05)

    def _leaf(self, name, at, z, d, n, c, width, hinge_at_start, height, handle):
        mat, sgn = self.leaf_frame(at, z, d, n, c, width, hinge_at_start, 0.0)
        p = fg.Parts(self.rng)
        lx = Vector((1, 0, 0))
        ny = Vector((0, sgn, 0))
        w = width - 0.02
        z0, z1 = 0.05, self.g.height
        self._panel(p, Vector((0, 0, 0)), lx, 0.01, 0.01 + w, z0, z1)
        for h in (z0 + 0.25, z1 - 0.25):                   # hinge barrels on the hinge edge
            p.box(Vector((-0.012, 0, h)), UP, lx, 0.14, 0.03, 0.03, mat=M_STEEL, uv="metric")
        if handle:
            hz = 1.0
            for side in (1.0, -1.0):                        # lever handle + plate on both faces
                y = side * (FRAME_D / 2 + 0.005)
                p.box(Vector((w - 0.04, y, hz)), UP, lx, 0.22, 0.04, 0.01, mat=M_STEEL, uv="metric")
                p.box(Vector((w - 0.1, y + side * 0.045, hz + 0.05)), lx, UP, 0.14, 0.02, 0.02, mat=M_STEEL,
                      uv="metric")
                p.box(Vector((w - 0.04, y + side * 0.025, hz + 0.05)), ny, UP, 0.05, 0.02, 0.02, mat=M_STEEL,
                      uv="metric")
        self.leaves.append((name, p, mat))
