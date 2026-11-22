"""Bundled model library: append a piece from one of the add-on's .blend files once,
then place linked copies of it (shared meshes) wherever the user asks.

Each source file is appended into its own child of the hidden "CS_Library" collection
(kept in the .blend by a fake user, never shown), tagged with its path, so later copies
- even after saving and reopening - reuse the same meshes. Textures are relinked by file
name against every image bundled with the add-on, so the models' old //textures/... or
absolute paths don't matter.
"""

import os

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import naming

PKG_DIR = os.path.dirname(os.path.dirname(__file__))
LIB_NAME = "CS_Library"
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tga", ".tif", ".tiff", ".exr", ".hdr"}
_SKIP_PREFIX = ("Preview", "CamTarget")
_image_index = None

# Mounts: FLOOR puts the piece's bottom-centre on the cursor; KEEP puts the model's own
# origin there (wall, ceiling and counter pieces are modelled round their fixing point).
FLOOR, KEEP = "FLOOR", "KEEP"


class Item:
    """One placeable piece: `file` is relative to its section's assets folder; `objects`
    limits it to those top-level objects of the file (None = all of them). Copies are named
    '<name>-<n>' (thing-style-variant, e.g. 'sofa-old-3seat'; default: the key)."""

    def __init__(self, key, label, file, objects=None, mount=FLOOR, note="", name=None):
        self.key, self.label, self.file = key, label, file
        self.objects, self.mount, self.note = objects, mount, note
        self.name = naming.slug(name or key)


# --------------------------------------------------------------------------
# Textures
# --------------------------------------------------------------------------

def _images():
    global _image_index
    if _image_index is None:
        _image_index = {}
        for root, _dirs, files in os.walk(PKG_DIR):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in _IMAGE_EXT:
                    _image_index.setdefault(fn.lower(), os.path.join(root, fn))
    return _image_index


def relink_images(images=None):
    """Point every missing (unpacked) image at the bundled file of the same name."""
    found = 0
    for img in images if images is not None else bpy.data.images:
        if img.source != "FILE" or img.packed_file or img.library:
            continue
        if os.path.exists(bpy.path.abspath(img.filepath)):
            continue
        path = _images().get(os.path.basename(img.filepath.replace("\\", "/")).lower())
        if path:
            img.filepath = path
            img.reload()
            found += 1
    return found


# --------------------------------------------------------------------------
# Sources (appended once)
# --------------------------------------------------------------------------

def library():
    lib = bpy.data.collections.get(LIB_NAME)
    if lib is None:
        lib = bpy.data.collections.new(LIB_NAME)
        lib.use_fake_user = True
    return lib


def _wanted(ob):
    if ob.type in {"CAMERA", "LIGHT", "LIGHT_PROBE", "SPEAKER"} or ob.name.startswith(_SKIP_PREFIX):
        return False
    return not (ob.type == "EMPTY" and not ob.children and ob.instance_type == "NONE")


def source(path, objects=None):
    """Top-level objects of `path` (appended on first use), restricted to `objects`."""
    key = os.path.relpath(path, PKG_DIR).replace("\\", "/")
    lib = library()
    coll = next((c for c in lib.children if c.get("cs_src") == key), None)
    if coll is None:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        before = set(bpy.data.images)
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            names = list(src.objects)
            dst.objects = list(names)              # Blender swaps this list's names for objects
        coll = bpy.data.collections.new("CSLib_" + os.path.splitext(os.path.basename(path))[0])
        coll["cs_src"] = key
        lib.children.link(coll)
        for name, ob in zip(names, dst.objects):
            if ob is None:
                continue
            if _wanted(ob):
                coll.objects.link(ob)
                ob["cs_name"] = name               # its name in the file (appending may add .001)
            else:
                bpy.data.objects.remove(ob)
        relink_images([i for i in bpy.data.images if i not in before])
    tops = [o for o in coll.objects if o.parent is None or o.parent.name not in coll.objects]
    if objects:
        tops = [o for o in tops if o.get("cs_name", o.name) in objects]
    return tops


# --------------------------------------------------------------------------
# Placing copies
# --------------------------------------------------------------------------

def _tree(ob):
    return [ob] + list(ob.children_recursive)


def _bounds(tops):
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for top in tops:
        for ob in _tree(top):
            if ob.type != "MESH" or not ob.data.vertices:
                continue
            co = np.empty(len(ob.data.vertices) * 3)
            ob.data.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3) @ np.array(ob.matrix_world)[:3, :3].T + np.array(ob.matrix_world.translation)
            lo, hi = np.minimum(lo, co.min(0)), np.maximum(hi, co.max(0))
    return (Vector(lo), Vector(hi)) if np.isfinite(lo).all() else (Vector(), Vector())


def _copy(src, coll, parent, basis):
    ob = src.copy()                       # shares the mesh and materials
    coll.objects.link(ob)
    ob.hide_viewport = ob.hide_render = False
    ob.hide_set(False)
    ob.parent = parent
    if basis is None:                     # a child: keep its place under its parent
        ob.matrix_parent_inverse = src.matrix_parent_inverse.copy()
        ob.matrix_basis = src.matrix_basis.copy()
    else:
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.matrix_basis = basis
    for child in src.children:
        if child.name in src.users_collection[0].objects:
            _copy(child, coll, ob, None)
    return ob


def place(item, folder, coll, location, rotation=0.0):
    """Place one copy of `item` (from `folder`) at `location`; returns its top object.
    Several top-level objects get a parent empty named after the piece. `coll` must be
    in the scene (see target_collection): floor pieces are measured once placed.

    Library objects sit outside the scene, so their stored world matrices can be stale;
    copies are built from each object's own (basis / parent-inverse) transforms instead."""
    tops = source(os.path.join(folder, item.file), item.objects)
    if not tops:
        raise LookupError(f"{item.file}: none of {item.objects} found")
    location = Vector(location)
    at = Matrix.Translation(location) @ Matrix.Rotation(rotation, 4, "Z")
    name = naming.next_name(item.name)
    if len(tops) == 1:
        root = _copy(tops[0], coll, None, at @ tops[0].matrix_basis)
    else:
        root = bpy.data.objects.new(name, None)
        root.empty_display_type, root.empty_display_size = "PLAIN_AXES", 0.25
        coll.objects.link(root)
        root.matrix_world = at
        for top in tops:
            _copy(top, coll, root, top.matrix_basis.copy())
    if item.mount == FLOOR:              # bottom-centre onto the cursor
        bpy.context.view_layer.update()
        lo, hi = _bounds([root])
        root.location += Vector((location.x - (lo.x + hi.x) / 2, location.y - (lo.y + hi.y) / 2,
                                 location.z - lo.z))
    root.name = name
    for ob in root.children_recursive:           # parts: <name>_<part's name in the file>
        base = f"{name}_{(ob.get('cs_name') or ob.name).replace('.', '-')}"
        part, k = base, 1
        while part in bpy.data.objects and bpy.data.objects[part] != ob:
            k += 1
            part = f"{base}-{k}"
        ob.name = part
    root["cs_asset"] = item.key
    return root


def bounds(root):
    """World-space (min, max) corners of a placed piece and everything under it."""
    return _bounds([root])


def target_collection(context, name):
    """The scene collection placed pieces go into (made on first use)."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in context.scene.collection.children and coll not in context.scene.collection.children_recursive:
        context.scene.collection.children.link(coll)
    return coll
