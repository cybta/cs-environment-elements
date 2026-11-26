"""Roof materials by face: tiles / shingles on top, the soffit underneath, and the edges (eave
fascias, gable verges) dressed in the roof's edge strip (neighborhood_materials.ROOF_EDGES), so
an edge shows one neat row of tabs instead of a sliver of the roof map.

The strip's UVs: U in metres along the edge (as everywhere else, so the material's scale holds),
V from 0 at the edge's foot to 1 at its top - the strip's full height, wherever the edge sits.
"""

from mathutils import Vector

from .mesh_utils import _mat_index

EDGE = 0.5          # faces steeper than this (|normal.z| below it) are edges


def paint(me, mats):
    """Give a roof mesh its materials. Call before the object is made (that makes the UVs)."""
    i_roof, i_soffit = _mat_index(me, mats["roof"]), _mat_index(me, mats["soffit"])
    i_edge = _mat_index(me, mats["roof_edge"]) if mats.get("roof_edge") else i_roof
    for p in me.polygons:
        if p.normal.z < -0.3:
            p.material_index = i_soffit
        elif abs(p.normal.z) < EDGE:
            p.material_index = i_edge
        else:
            p.material_index = i_roof
    return me


def edge_uvs(me, mats):
    """Lay the strip's UVs on the edge faces. Call after the object is made."""
    edge = mats.get("roof_edge")
    if edge is None or not me.uv_layers:
        return
    idx = next((i for i, m in enumerate(me.materials) if m == edge), None)
    if idx is None:
        return
    uv = me.uv_layers.active.data
    up = Vector((0.0, 0.0, 1.0))
    for p in me.polygons:
        if p.material_index != idx:
            continue
        t = up.cross(p.normal)
        if t.length < 1e-6:
            continue
        t.normalize()
        cos = [me.vertices[me.loops[li].vertex_index].co for li in p.loop_indices]
        for li, co in zip(p.loop_indices, cos):
            # the foot of the edge: a corner with another straight above it (the roof's top skin is
            # its underside lifted straight up)
            foot = any((o.xy - co.xy).length < 1e-4 and o.z > co.z + 1e-4 for o in cos)
            uv[li].uv = (co.dot(t), 0.0 if foot else 1.0)
