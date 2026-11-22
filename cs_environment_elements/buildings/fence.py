"""Fences section of the generator panel: settings, outline tools and the build operator.

Workflow: "Draw Points" (click 3 or more points on the ground, Enter to finish) or
"Triangle" (a 3-point outline to edit in Edit Mode), then Generate Fence. Any mesh or
curve object can serve as the outline. The door and parking gate each sit on a side
(side n runs from point n to point n+1) at a position along it.
"""

import bpy
import bmesh
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty,
                       StringProperty)
from bpy.types import Operator, PropertyGroup
from bpy_extras import view3d_utils
from mathutils import Vector
from mathutils.geometry import intersect_line_plane

from . import fence_build as fb
from . import fence_paint as fpaint


def _outline_poll(self, ob):
    return ob.type in {"MESH", "CURVE"} and "roomgen_fence" not in ob.users_collection[0] if ob.users_collection \
        else ob.type in {"MESH", "CURVE"}


class FENCEGEN_Settings(PropertyGroup):
    style: EnumProperty(name="Style", default="OLD", items=[
        ("OLD", "Old Wood", "Weathered vertical boards nailed to rails on wooden posts"),
        ("MODERN", "Modern", "Concrete plinth and pillars with horizontal slat panels in black steel frames"),
    ])
    outline: PointerProperty(name="Outline", type=bpy.types.Object, poll=_outline_poll,
                             description="Mesh or curve whose points the fence follows "
                                         "(a closed loop fences an area in, an open chain is a straight run)")
    close_drawn: BoolProperty(name="Close Loop", default=True,
                              description="Join the last drawn point back to the first")
    skip_sides: StringProperty(name="Shared Sides", default="",
                               description="Sides left out because a neighbour's fence or a wall stands there, "
                                           "e.g. '3' or '2, 4' (side n runs from point n to point n+1)")
    shared_posts: BoolProperty(name="Posts at Shared Ends", default=False,
                               description="Put our own posts at the ends of a shared side. Off: the neighbour's "
                                           "fence has posts there already (two would overlap)")
    seed: IntProperty(name="Seed", default=1, min=0, description="Which planks each board uses")
    height: FloatProperty(name="Height (m)", default=1.8, min=0.6, max=3.0, step=10)
    board_width: FloatProperty(name="Board Width (m)", default=0.13, min=0.06, max=0.3, step=1)
    board_thick: FloatProperty(name="Board Thickness (m)", default=0.022, min=0.012, max=0.06, step=0.1)
    gap: FloatProperty(name="Gap (m)", default=0.06, min=0.0, max=0.2, step=0.5,
                       description="Space between boards (0 = closed board wall). The default is about "
                                   "half a board, so the fence looks airy rather than solid")
    uneven: FloatProperty(name="Uneven Tops (m)", default=0.025, min=0.0, max=0.15, step=0.5,
                          description="Each board a little taller or shorter, for an old look")
    clearance: FloatProperty(name="Ground Gap (m)", default=0.05, min=0.0, max=0.3, step=0.5,
                             description="Boards stop this far above the ground")
    post_size: FloatProperty(name="Post Size (m)", default=0.1, min=0.05, max=0.25, step=1)
    post_spacing: FloatProperty(name="Max Post Spacing (m)", default=2.4, min=1.0, max=3.5, step=10)
    rails: IntProperty(name="Rails", default=2, min=2, max=3)
    rail_depth: FloatProperty(name="Rail Depth (m)", default=0.09, min=0.04, max=0.2, step=0.5)
    rail_thick: FloatProperty(name="Rail Thickness (m)", default=0.045, min=0.02, max=0.1, step=0.5)
    flip: BoolProperty(name="Flip Street Side", default=False,
                       description="Turn the fence round: its street face (boards, house number) looks inwards")
    # Old style: paint (see fence_paint). Changing these repaints the selected fence at once.
    paint: BoolProperty(name="Paint", default=True, update=fpaint.on_change,
                        description="Old paint on the boards, rails and posts, peeling off the wood")
    paint_color: FloatVectorProperty(name="Paint Colour", subtype="COLOR_GAMMA", size=3, min=0.0, max=1.0,
                                     default=fpaint.DEFAULT_COLOR, update=fpaint.on_change)
    peel: FloatProperty(name="Peeling", default=0.45, min=0.0, max=1.0, subtype="FACTOR", update=fpaint.on_change,
                        description="How much of the paint has come off: 0 = freshly painted, 1 = bare wood")

    # Modern style
    plinth_h: FloatProperty(name="Plinth (m)", default=0.5, min=0.0, max=1.2, step=5,
                            description="Height of the concrete base wall under the panels")
    pillars: EnumProperty(name="Pillars", default="EVERY", items=[
        ("EVERY", "Every Panel", "A masonry pillar between every two panels"),
        ("ENDS", "Corners & Openings", "Masonry pillars only at corners and openings, slim steel posts between"),
    ])
    pillar_mat: EnumProperty(name="Masonry", default="CONCRETE", items=[
        ("CONCRETE", "Concrete Blocks", "Stacked grey architectural-concrete blocks with shadow joints"),
        ("RENDER", "White Render", "Smooth white rendered pillars and plinth"),
    ])
    pillar_size: FloatProperty(name="Pillar Size (m)", default=0.4, min=0.2, max=0.7, step=5)
    bay: FloatProperty(name="Panel Width (m)", default=3.0, min=1.2, max=4.0, step=10,
                       description="Longest a panel gets between two pillars or posts")
    infill: EnumProperty(name="Slats", default="METAL", items=[
        ("METAL", "Black Metal", "Anthracite aluminium slats"),
        ("CEDAR", "Cedar", "Oiled warm-brown timber slats"),
        ("WEATHERED", "Weathered Timber", "Silver-grey weathered timber slats"),
    ])
    slat_h: FloatProperty(name="Slat Height (m)", default=0.1, min=0.04, max=0.25, step=1)
    slat_gap: FloatProperty(name="Slat Gap (m)", default=0.02, min=0.005, max=0.1, step=0.5)
    mailbox: BoolProperty(name="Mailbox Pillar", default=True,
                          description="A wide concrete pillar beside the door with the house number, "
                                      "a letterbox slot and an intercom")
    mailbox_side: EnumProperty(name="Mailbox Side", default="RIGHT", items=[
        ("LEFT", "Left", "Towards the side's first point"), ("RIGHT", "Right", "Towards the side's last point")])
    house_number: StringProperty(name="Number", default="15")

    door: BoolProperty(name="Door", default=True, description="A wicket door for people")
    door_side: IntProperty(name="Side", default=1, min=1, description="Side n runs from point n to point n+1")
    door_pos: FloatProperty(name="Position", default=0.3, min=0.0, max=1.0, subtype="FACTOR",
                            description="Where along the side (0 = its first point, 1 = its last)")
    door_width: FloatProperty(name="Width (m)", default=1.0, min=0.6, max=1.6, step=5)
    door_hinge: EnumProperty(name="Hinge", items=[("LEFT", "Left", "Hinged on the side nearer the first point"),
                                                  ("RIGHT", "Right", "Hinged on the side nearer the last point")],
                             default="LEFT")

    gate: BoolProperty(name="Parking Gate", default=True, description="A wide gate for a car")
    gate_side: IntProperty(name="Side", default=1, min=1, description="Side n runs from point n to point n+1")
    gate_pos: FloatProperty(name="Position", default=0.65, min=0.0, max=1.0, subtype="FACTOR",
                            description="Where along the side (0 = its first point, 1 = its last)")
    gate_width: FloatProperty(name="Width (m)", default=3.6, min=2.4, max=6.0, step=10)
    gate_leaves: IntProperty(name="Leaves", default=2, min=1, max=2, description="One wide leaf or a pair")


def _settings(context):
    return context.scene.house_gen.fence


def _outline(context):
    g = _settings(context)
    ob = context.active_object
    if ob is not None and ob.type in {"MESH", "CURVE"} and not ob.get("roomgen_fence_part") \
            and (ob == g.outline or g.outline is None):
        return ob
    return g.outline


def _new_outline(context, points, closed, name="Fence Outline"):
    me = bpy.data.meshes.new(name)
    n = len(points)
    edges = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed and n > 2 else [])
    me.from_pydata([tuple(p) for p in points], edges, [])
    ob = bpy.data.objects.new(name, me)
    ob.display_type = "WIRE"
    ob.show_in_front = True
    context.collection.objects.link(ob)
    return ob


def _select_only(context, ob):
    for o in context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    context.view_layer.objects.active = ob


# --------------------------------------------------------------------------
# Operators
# --------------------------------------------------------------------------

class FENCEGEN_OT_triangle(Operator):
    bl_idname = "fence_gen.triangle"
    bl_label = "Triangle Outline"
    bl_description = "Add a 3-point fence outline at the 3D cursor; edit it in Edit Mode (subdivide or extrude to add points)"
    bl_options = {"REGISTER", "UNDO"}

    size: FloatProperty(name="Size (m)", default=12.0, min=2.0)

    def execute(self, context):
        c = context.scene.cursor.location
        r = self.size / 2
        pts = [c + Vector((-r, -r * 0.58, 0)), c + Vector((r, -r * 0.58, 0)), c + Vector((0, r * 1.15, 0))]
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        ob = _new_outline(context, pts, True)
        _select_only(context, ob)
        _settings(context).outline = ob
        return {"FINISHED"}


def _draw_preview(op, context):
    import gpu
    from gpu_extras.batch import batch_for_shader
    pts = list(op.points)
    if op.hover is not None:
        pts.append(op.hover)
    if not pts:
        return
    if len(pts) > 2 and _settings(context).close_drawn:
        pts.append(pts[0])
    sh = gpu.shader.from_builtin("UNIFORM_COLOR")
    gpu.state.line_width_set(2.0)
    gpu.state.point_size_set(8.0)
    sh.bind()
    sh.uniform_float("color", (1.0, 0.75, 0.2, 1.0))
    batch_for_shader(sh, "LINE_STRIP", {"pos": [tuple(p) for p in pts]}).draw(sh)
    batch_for_shader(sh, "POINTS", {"pos": [tuple(p) for p in op.points]}).draw(sh)
    gpu.state.line_width_set(1.0)
    gpu.state.point_size_set(1.0)


class FENCEGEN_OT_draw(Operator):
    bl_idname = "fence_gen.draw"
    bl_label = "Draw Points"
    bl_description = ("Click points on the ground (at the 3D cursor's height) to outline the fence. "
                      "Enter/Space or right-click: finish and build · Backspace: undo point · Esc: cancel")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def _hit(self, context, event):
        region, rv3d = context.region, context.region_data
        co = (event.mouse_region_x, event.mouse_region_y)
        o = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
        v = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
        z = context.scene.cursor.location.z
        return intersect_line_plane(o, o + v * 1000.0, Vector((0, 0, z)), Vector((0, 0, 1)))

    def invoke(self, context, event):
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        self.points, self.hover = [], None
        self._handle = bpy.types.SpaceView3D.draw_handler_add(_draw_preview, (self, context), "WINDOW", "POST_VIEW")
        context.window_manager.modal_handler_add(self)
        self._status(context)
        return {"RUNNING_MODAL"}

    def _status(self, context):
        context.area.header_text_set(f"Fence: {len(self.points)} point(s) · click to add · Backspace undo · "
                                     "Enter/Space/right-click finish · Esc cancel")
        context.area.tag_redraw()

    def _end(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._handle, "WINDOW")
        context.area.header_text_set(None)
        context.area.tag_redraw()

    def modal(self, context, event):
        if event.type in {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM"} \
                or (event.type.startswith("NUMPAD") and event.value == "PRESS"):
            return {"PASS_THROUGH"}
        if event.type == "MOUSEMOVE":
            self.hover = self._hit(context, event)
            context.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS":
            p = self._hit(context, event)
            if p is not None and (not self.points or (p - self.points[-1]).length > 0.05):
                self.points.append(p)
            self._status(context)
            return {"RUNNING_MODAL"}
        if event.type == "BACK_SPACE" and event.value == "PRESS":
            if self.points:
                self.points.pop()
            self._status(context)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            self._end(context)
            return {"CANCELLED"}
        if event.type in {"RET", "NUMPAD_ENTER", "SPACE", "RIGHTMOUSE"} and event.value == "PRESS":
            self._end(context)
            if len(self.points) < 2:
                self.report({"WARNING"}, "A fence needs at least 2 points")
                return {"CANCELLED"}
            g = _settings(context)
            ob = _new_outline(context, self.points, g.close_drawn)
            _select_only(context, ob)
            g.outline = ob
            bpy.ops.fence_gen.generate()
            return {"FINISHED"}
        return {"RUNNING_MODAL"}


class FENCEGEN_OT_pick_side(Operator):
    bl_idname = "fence_gen.pick_side"
    bl_label = "Use Selected Edge"
    bl_description = ("In Edit Mode on the outline, select one edge (or its two points): put the opening "
                      "there, or (Shared) add / remove that side from the shared sides")
    bl_options = {"REGISTER", "UNDO"}

    target: EnumProperty(items=[("DOOR", "Door", ""), ("GATE", "Gate", ""), ("SKIP", "Shared", "")])

    def execute(self, context):
        ob = _outline(context)
        if ob is None or ob.type != "MESH" or ob.mode != "EDIT":
            self.report({"WARNING"}, "Tab into Edit Mode on the outline and select an edge")
            return {"CANCELLED"}
        bm = bmesh.from_edit_mesh(ob.data)
        sel = {v.index for v in bm.verts if v.select}
        if len(sel) < 2:
            self.report({"WARNING"}, "Select an edge (two neighbouring points)")
            return {"CANCELLED"}
        for i, side in enumerate(fb.sides(fb.outline_chains(ob, context))):
            if side[4] in sel and side[5] in sel:
                g = _settings(context)
                if self.target == "SKIP":                   # toggle this side in the shared list
                    now = set(fb.shared_sides(g.skip_sides)) ^ {i + 1}
                    g.skip_sides = ", ".join(str(k) for k in sorted(now))
                    self.report({"INFO"}, f"Side {i + 1} {'shared' if i + 1 in now else 'fenced again'}")
                    return {"FINISHED"}
                setattr(g, "door_side" if self.target == "DOOR" else "gate_side", i + 1)
                setattr(g, "door_pos" if self.target == "DOOR" else "gate_pos", 0.5)
                self.report({"INFO"}, f"{self.target.title()} on side {i + 1}")
                return {"FINISHED"}
        self.report({"WARNING"}, "The selected points are not one side of the outline")
        return {"CANCELLED"}


class FENCEGEN_OT_generate(Operator):
    bl_idname = "fence_gen.generate"
    bl_label = "Generate Fence"
    bl_description = ("Build the fence along the outline, named fence-<style>-<n>; an outline that already "
                      "has a fence gets it rebuilt (same name)")
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        g = _settings(context)
        ob = _outline(context)
        if ob is None:
            self.report({"WARNING"}, "Draw points or add a triangle outline first")
            return {"CANCELLED"}
        g.outline = ob
        chains = fb.outline_chains(ob, context)
        if not chains:
            self.report({"WARNING"}, f"'{ob.name}' has no edges to follow")
            return {"CANCELLED"}
        from ..core import naming
        prefix = naming.slug("fence", "modern" if g.style == "MODERN" else "old")
        old = next((c for c in bpy.data.collections if c.get("roomgen_fence") == ob.name), None)
        name = naming.keep_or_next(old.name, prefix) if old else naming.next_name(prefix)
        coll, warnings = fb.build(context, g, ob, chains, name=name)
        for o in coll.objects:
            o["roomgen_fence_part"] = True
        from . import lod_ui
        lod_ui.after_build(context, next((o for o in coll.objects if o.type == "EMPTY" and o.parent is None), None))
        total = sum(s[3] for s in fb.sides(chains))
        msg = f"{coll.name}: {total:.1f} m, {len(fb.sides(chains))} side(s)"
        self.report({"WARNING"} if warnings else {"INFO"}, msg + (" — " + "; ".join(warnings) if warnings else ""))
        return {"FINISHED"}


class FENCEGEN_OT_randomize(Operator):
    bl_idname = "fence_gen.randomize"
    bl_label = "New Planks"
    bl_description = "Pick a new seed (other planks on every board) and rebuild"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        import random
        _settings(context).seed = random.randint(0, 99999)
        return bpy.ops.fence_gen.generate()


# --------------------------------------------------------------------------
# Panel section (drawn by the generator panel when Section = Fences)
# --------------------------------------------------------------------------

def draw(layout, context):
    g = _settings(context)
    layout.row(align=True).prop(g, "style", expand=True)
    box = layout.box()
    box.label(text="Outline", icon="CURVE_PATH")
    row = box.row(align=True)
    row.operator("fence_gen.draw", icon="GREASEPENCIL")
    row.operator("fence_gen.triangle", text="Triangle", icon="MESH_DATA")
    box.prop(g, "close_drawn")
    box.prop(g, "outline")
    ob = _outline(context)
    side_list = []
    if ob is not None:
        try:
            side_list = fb.sides(fb.outline_chains(ob, context, sync_edit=False))
        except Exception:          # mid-edit topology the walker can't read: just show nothing
            side_list = []
        if ob.mode != "EDIT":
            box.label(text="Edit Mode: subdivide/extrude to add points", icon="INFO")
        col = box.column(align=True)
        shared = set(fb.shared_sides(g.skip_sides))
        for i, s in enumerate(side_list[:16]):
            tag = "  (shared)" if i + 1 in shared else ""
            col.label(text=f"Side {i + 1}:  point {s[4] + 1} → {s[5] + 1},  {s[3]:.1f} m{tag}",
                      icon="UNLINKED" if tag else "NONE")
        if len(side_list) > 16:
            col.label(text=f"... {len(side_list) - 16} more")
    row = box.row(align=True)
    row.prop(g, "skip_sides")
    row.operator("fence_gen.pick_side", text="", icon="RESTRICT_SELECT_OFF").target = "SKIP"
    if g.skip_sides.strip():
        box.prop(g, "shared_posts")

    box = layout.box()
    if g.style == "MODERN":
        box.label(text="Plinth, Pillars & Panels")
        c = box.column(align=True)
        for p in ("height", "plinth_h", "pillar_size", "bay"):
            c.prop(g, p)
        box.prop(g, "pillars", text="")
        box.prop(g, "pillar_mat", text="")
        box.prop(g, "infill")
        c = box.column(align=True)
        c.prop(g, "slat_h")
        c.prop(g, "slat_gap")
    else:
        box.label(text="Boards & Posts")
        c = box.column(align=True)
        for p in ("height", "board_width", "board_thick", "gap", "uneven", "clearance"):
            c.prop(g, p)
        c = box.column(align=True)
        for p in ("post_size", "post_spacing", "rails", "rail_depth", "rail_thick"):
            c.prop(g, p)
    box.prop(g, "flip")
    if g.style == "OLD":
        fpaint.draw(layout, g)

    for key, label in (("door", "DOOR"), ("gate", "GATE")):
        box = layout.box()
        box.prop(g, key)
        if not getattr(g, key):
            continue
        c = box.column(align=True)
        row = c.row(align=True)
        row.prop(g, f"{key}_side")
        row.operator("fence_gen.pick_side", text="", icon="RESTRICT_SELECT_OFF").target = label
        c.prop(g, f"{key}_pos")
        c.prop(g, f"{key}_width")
        if key == "door":
            box.row().prop(g, "door_hinge", expand=True)
            if g.style == "MODERN":
                box.prop(g, "mailbox")
                if g.mailbox:
                    r = box.row(align=True)
                    r.prop(g, "mailbox_side", expand=True)
                    r.prop(g, "house_number", text="")
        else:
            box.prop(g, "gate_leaves")
        n = getattr(g, f"{key}_side")
        if side_list and n > len(side_list):
            box.label(text=f"The outline has only {len(side_list)} side(s)", icon="ERROR")
    if g.door and g.gate and g.door_side == g.gate_side and abs(g.door_pos - g.gate_pos) < 0.15:
        layout.label(text="Door and gate close: they share a pillar", icon="INFO")

    row = layout.row(align=True)
    row.prop(g, "seed")
    row.operator("fence_gen.randomize", text="", icon="FILE_REFRESH")
    layout.separator()
    big = layout.row()
    big.scale_y = 1.6
    big.operator("fence_gen.generate", icon="MOD_LATTICE")


classes = (
    FENCEGEN_Settings,
    FENCEGEN_OT_triangle,
    FENCEGEN_OT_draw,
    FENCEGEN_OT_pick_side,
    FENCEGEN_OT_generate,
    FENCEGEN_OT_randomize,
    fpaint.FENCEGEN_OT_random_paint,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
