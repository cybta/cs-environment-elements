"""Small scene helpers shared by every section."""

import bpy


def _delete_collection(coll):
    """Remove a collection, its children and their objects (and orphaned meshes/lights)."""
    for child in list(coll.children):
        _delete_collection(child)
    for ob in list(coll.objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if isinstance(data, bpy.types.Mesh) and data.users == 0:
            bpy.data.meshes.remove(data)
        elif isinstance(data, bpy.types.Light) and data.users == 0:
            bpy.data.lights.remove(data)
    bpy.data.collections.remove(coll)
