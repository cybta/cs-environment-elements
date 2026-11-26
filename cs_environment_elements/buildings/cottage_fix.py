"""Repairs for cottages built before a generator fix, done in place (paint, names and everything else kept).

Porch posts: cottages built before cottage.JOIST_SET_BACK have the veranda deck's edge and the rim joists flush
with the posts' outer faces. Flush faces share a plane, so the renderer can't tell which is in front: the deck and
rim flicker through the foot of every post (z-fighting, Blender's viewport and the game alike). set_back_veranda
moves those deck / rim faces JOIST_SET_BACK behind the posts, only where they still meet a post face, and rebuilds
the cottage's LODs from the fixed parts (lod.build takes the paint from the root, so hand-tuned colours stay).
"""

import bpy
from bpy.props import BoolProperty
from bpy.types import Operator
from mathutils import Vector

from . import lod
from .cottage import JOIST_SET_BACK
from .paint_edit import root_of


def _box(ob):
    pts = [ob.matrix_local @ v.co for v in ob.data.vertices]
    return Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])


def set_back_veranda(root, rebuild_lods=True):
    """Move the veranda deck's and rim joists' outer faces off the posts' faces -> True if anything moved."""
    kids = {k.name[len(root.name) + 1:]: k for k in root.children if k.type == "MESH" and not k.get("lod", 0)}
    posts = kids.get("VerandaPosts")
    if posts is None:
        return False
    plo, phi = _box(posts)
    moved = False
    for part in (kids.get("VerandaJoists"), kids.get("VerandaDeck")):
        if part is None:
            continue
        lo, hi = _box(part)
        # (axis, the part's face, which way is in, the posts' face): the two sides (x) and the front (-y)
        moves = [(ax, val, d) for ax, val, d, pv in ((0, lo.x, 1, plo.x), (0, hi.x, -1, phi.x), (1, lo.y, 1, plo.y))
                 if abs(val - pv) < 1e-4]
        if not moves:
            continue
        to_local = part.matrix_local.inverted()
        for v in part.data.vertices:
            p = part.matrix_local @ v.co
            for ax, val, d in moves:
                if abs(p[ax] - val) < 1e-5:
                    p[ax] += d * JOIST_SET_BACK
            v.co = to_local @ p
        part.data.update()
        moved = True
    if moved and rebuild_lods and any(o.get("lod", 0) > 0 for o in root.children_recursive):
        lod.build(root)
    return moved


def cottage_roots(context, everything):
    obs = context.scene.objects if everything else context.selected_objects
    roots = {root_of(o) for o in obs}
    return [r for r in roots if r is not None and any(k.name.endswith("_VerandaPosts") for k in r.children)]


class CSENV_OT_fix_porch(Operator):
    bl_idname = "csenv.fix_porch"
    bl_label = "Fix Porch Posts"
    bl_description = ("Set the veranda deck edge and rim joists 1 cm behind the posts where they are flush "
                      "(they flicker through the posts), then rebuild those cottages' LODs. Paint is kept")
    bl_options = {"REGISTER", "UNDO"}

    everything: BoolProperty(name="All", default=False, description="Every cottage in the scene")

    def execute(self, context):
        roots = cottage_roots(context, self.everything)
        if not roots:
            self.report({"WARNING"}, "Select a cottage (or use All)")
            return {"CANCELLED"}
        done = sum(set_back_veranda(r) for r in roots)
        self.report({"INFO"}, f"{done} of {len(roots)} cottage(s) fixed" + ("" if done else " (all fine already)"))
        return {"FINISHED"}


classes = (CSENV_OT_fix_porch,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
