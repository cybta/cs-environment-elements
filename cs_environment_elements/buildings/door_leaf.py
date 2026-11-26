"""Door leaves dressed with a picture of a whole door (houses and villas; cottages keep
their boards). Each leaf's two big faces get the full image, upright and read the right
way round from either side; its thin edges take a sliver of the image's left border.
"""

from mathutils import Vector

from ..core import neighborhood_materials as nm
from .mesh_utils import _boxes_mesh

INNER = "C_door_white"
MAIN = {"HOUSE": "C_door_house", "VILLA_MODERN": "C_door_villa_modern", "VILLA_GABLE": "C_door_villa_gable"}


def add_roles(m, building_type):
    """White inside doors for houses and villas, and the type's own front door ("door_main").
    The Mediterranean villa's arched front door ("door_arched") and its shutters ("shutter") are
    pictures fitted to each leaf too."""
    if building_type != "HOUSE" and not building_type.startswith("VILLA"):
        return
    m["door_in"] = nm.ensure(INNER)
    if building_type in MAIN:
        m["door_main"] = nm.ensure(MAIN[building_type])
    if building_type == "VILLA_MEDITERRANEAN":
        m["door_arched"] = nm.ensure("C_door_villa_med")
        m["shutter"] = nm.ensure("C_shutter_villa_med")


def leaves_mesh(name, boxes, offset):
    """Boxes as door leaves, with UVs fitting the door picture to each leaf."""
    return fit_uvs(_boxes_mesh(name, boxes, offset))


def fit_uvs(me):
    """Each big face of the mesh gets the whole picture (any outline: an arched door's face is
    fitted by its bounding box), read the right way round from its own side."""
    uv = me.uv_layers.active or me.uv_layers.new(name="UVMap")
    up = Vector((0, 0, 1))
    for poly in me.polygons:
        n = poly.normal
        pts = [me.vertices[i].co for i in poly.vertices]
        zs = [p.z for p in pts]
        z0, z1 = min(zs), max(zs)
        if abs(n.z) > 0.5:                     # top / bottom edge
            coords = [(0.01, 0.5)] * len(pts)
        else:
            right = up.cross(n)                # the viewer's right, looking at this face
            us = [p.dot(right) for p in pts]
            u0, u1 = min(us), max(us)
            big = (u1 - u0) > 0.2              # a face of the leaf, not its thin side
            coords = [((u - u0) / (u1 - u0) if big else 0.01, (p.z - z0) / max(z1 - z0, 1e-6))
                      for u, p in zip(us, pts)]
        for li, co in zip(poly.loop_indices, coords):
            uv.data[li].uv = co
    return me
