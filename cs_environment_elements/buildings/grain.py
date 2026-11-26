"""Wood grain along each piece: the cottage's wooden parts (trim, veranda beams, joists, posts, rails, deck)
get metre UVs that ignore which way a piece runs, so a horizontal rail or a window head showed its grain
across it. align() turns each face's UVs a quarter turn where needed so the grain follows the face's longest
side. Done on the mesh (UVs), so the game gets it too; LODs are built from these meshes afterwards.
"""

import numpy as np

GRAIN_V = {"C_cottage_trim", "C_cottage_wood_v"}     # materials turned 90 degrees: grain along V
GRAIN_U = {"C_cottage_wood"}                          # grain along U
LONGER = 1.05                                         # turn only when clearly longer the other way


def align(root):
    """Turn the UVs of every wooden face under `root` so its grain runs along the face's longest side."""
    turned = 0
    for ob in [root] + list(root.children_recursive):
        if ob.type != "MESH" or ob.data is None or not ob.data.uv_layers or not ob.data.polygons:
            continue
        me = ob.data
        names = np.array([m.name if m else "" for m in me.materials] or [""])
        if not any(n in GRAIN_V or n in GRAIN_U for n in names):
            continue
        n = len(me.polygons)
        mi = np.empty(n, np.int32)
        me.polygons.foreach_get("material_index", mi)
        start = np.empty(n, np.int32)
        me.polygons.foreach_get("loop_start", start)
        tot = np.empty(n, np.int32)
        me.polygons.foreach_get("loop_total", tot)
        if np.any(np.diff(start) < 0):          # loops not in face order: leave this mesh
            continue
        layer = me.uv_layers.active.data
        uv = np.empty(len(me.loops) * 2, np.float32)
        layer.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        ext_u = np.maximum.reduceat(uv[:, 0], start) - np.minimum.reduceat(uv[:, 0], start)
        ext_v = np.maximum.reduceat(uv[:, 1], start) - np.minimum.reduceat(uv[:, 1], start)
        mat = names[np.minimum(mi, len(names) - 1)]
        turn = (np.isin(mat, list(GRAIN_V)) & (ext_u > ext_v * LONGER)) | \
               (np.isin(mat, list(GRAIN_U)) & (ext_v > ext_u * LONGER))
        if not turn.any():
            continue
        per_loop = np.repeat(turn, tot)
        uv[per_loop] = np.stack([uv[per_loop, 1], -uv[per_loop, 0]], -1)     # (u, v) -> (v, -u)
        layer.foreach_set("uv", uv.ravel())
        me.update()
        turned += int(turn.sum())
    return turned
