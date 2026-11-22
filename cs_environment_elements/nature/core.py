"""Creating, regrowing, budgeting, baking and exporting trees."""

import os
from contextlib import contextmanager

import bpy

from ..core import naming
from . import assets, impostor, nodes, species

MODIFIER = "TreeGen"
LOD_COUNT = 3
STRUCTURE_PROPS = ("height", "bole", "canopy", "trunk_radius", "density", "seed",
                   "strands", "fluting", "root_length", "twist", "lean", "lean_dir",
                   "gnarl", "limb_droop", "flare", "flowers")
COPIED_PROPS = ("species", "hero") + STRUCTURE_PROPS + ("leaf_scale", "preview_lod", "tri_min", "tri_max")
SKELETON_ATTRIBUTES = ("radius", "level", "len", "leaf", "rank", "rot", "lscale")

_lock = {"depth": 0}


@contextmanager
def locked():
    """Suspend property update callbacks while several properties are set at once."""
    _lock["depth"] += 1
    try:
        yield
    finally:
        _lock["depth"] -= 1


def is_locked():
    return _lock["depth"] > 0


def is_tree(obj):
    return obj is not None and obj.type == "MESH" and obj.treegen.is_tree


def _params(settings):
    return {name: getattr(settings, name) for name in STRUCTURE_PROPS}


def sync_modifier(obj, lod=None, realize=False, trim=None, leaf_trim=None):
    """Push the tree's settings into its Geometry Nodes modifier.
    lod=None shows the LOD picked in the panel's Preview."""
    s = obj.treegen
    spec = species.SPECIES[s.species]
    group = nodes.ensure_group()
    mod = obj.modifiers.get(MODIFIER)
    if mod is None:
        mod = obj.modifiers.new(MODIFIER, "NODES")
    if mod.node_group != group:
        mod.node_group = group
    cards = assets.card_collections(assets.foliage_key(s.species, s.canopy, s.leaf_scale))
    values = {
        "LOD": int(s.preview_lod) if lod is None else lod,
        "Triangles Min": s.tri_min,
        "Triangles Max": max(s.tri_max, s.tri_min),
        "Budget Trim": s.budget_trim if trim is None else trim,
        "Leaf Trim": s.leaf_trim if leaf_trim is None else leaf_trim,
        "Leaf Scale": s.leaf_scale,
        "Segment Length": spec["segment"] * s.height,
        "Trunk Sides": spec["sides"],
        "Bark V Scale": spec["bark_v"],
        "Bark U Tiles": spec["bark_u"],
        "Card LOD 0": cards[0],
        "Card LOD 1": cards[1],
        "Card LOD 2": cards[2],
        "Bark Material": assets.bark_material(s.species),
        "Realize": realize,
    }
    ids = nodes.socket_ids(group)
    for name, value in values.items():
        mod[ids[name]] = value
    obj.update_tag()


def measure_triangles(obj, depsgraph):
    """(bark, foliage) triangles of the evaluated tree, counting every foliage instance."""
    depsgraph.update()
    mesh = obj.evaluated_get(depsgraph).data
    bark = len(mesh.loops) - 2 * len(mesh.polygons)
    foliage = 0
    for inst in depsgraph.object_instances:
        if inst.is_instance and inst.parent is not None and inst.parent.original == obj:
            data = inst.object.data
            foliage += len(data.loops) - 2 * len(data.polygons)
    return bark, foliage


def _search(measure, low, high, start, bounds, guess):
    """Find x in `bounds` whose measure(x) = (bark, foliage) totals inside low..high.
    The total must not fall as x rises. `guess(x, bark, foliage, target)` proposes the next
    x; once the answer is bracketed the search bisects. Returns the best (x, bark, foliage),
    preferring a total under `high` to one over it."""
    below, above = bounds                # largest x known too small, smallest x known too big
    best = None
    x = start
    for step in range(14):
        bark, foliage = measure(x)
        total = bark + foliage
        miss = 0 if low <= total <= high else (low - total if total < low else 4 * (total - high))
        if best is None or miss < best[0]:
            best = (miss, x, bark, foliage)
        if miss == 0:
            break
        if total < low:
            below = max(below, x)
        else:
            above = min(above, x)
        if above / below < 1.002 or (total < low and bark == 0 and step > 0):
            break                        # resolution limits reached; cannot get closer
        x = guess(x, bark, foliage, low * 1.04 if total < low else high * 0.96)
        bracketed = below > bounds[0] and above < bounds[1]
        if not below < x < above or (bracketed and step >= 3):
            x = (below * above) ** 0.5
    return best[1:]


TRIM_BOUNDS = (0.0001, 100.0)
LEAF_TRIM_BOUNDS = (0.001, 1.0)


def solve_budget(obj, context):
    """Measure the real LOD 0 triangle count and correct the node group's estimate until it
    sits inside the tree's Min..Max budget, then count LOD 1 and 2. The bark takes the
    correction; foliage is only cut when the bark is at its minimum and still over."""
    s = obj.treegen
    low, high = s.tri_min, max(s.tri_max, s.tri_min)
    depsgraph = context.evaluated_depsgraph_get()

    def measure_bark(trim):
        sync_modifier(obj, lod=0, trim=trim, leaf_trim=1.0)
        return measure_triangles(obj, depsgraph)

    trim, bark, foliage = _search(
        measure_bark, low, high, 1.0, TRIM_BOUNDS,
        lambda x, bark, foliage, target: x * max(target - foliage, 1.0) / max(bark, 1))
    leaf_trim = 1.0
    if bark + foliage > high:
        def measure_foliage(leaf_trim):
            sync_modifier(obj, lod=0, trim=trim, leaf_trim=leaf_trim)
            return measure_triangles(obj, depsgraph)

        leaf_trim, bark, foliage = _search(
            measure_foliage, low, high, 1.0, LEAF_TRIM_BOUNDS,
            lambda x, bark, foliage, target: x * max(target - bark, 1.0) / max(foliage, 1))
    counts = [bark + foliage]
    for lod in range(1, LOD_COUNT):
        sync_modifier(obj, lod=lod, trim=trim, leaf_trim=leaf_trim)
        counts.append(sum(measure_triangles(obj, depsgraph)))
    s.budget_trim, s.leaf_trim = trim, leaf_trim
    s.tri_count, s.tri_lod1, s.tri_lod2 = counts
    sync_modifier(obj)


def name_prefix(species_key):
    """'PINE' -> 'tree-pine', 'MAPLE_AUTUMN' -> 'tree-maple-autumn', 'BUSH' -> 'bush-flowering'."""
    spec = species.SPECIES[species_key]
    if spec.get("bush"):
        return naming.slug("bush", spec["label"].split()[0])
    return naming.slug("tree", species_key)


def regrow(obj, context):
    """Rebuild the skeleton from the tree's settings, keeping the object and modifier."""
    s = obj.treegen
    naming.rename_if_auto(obj, name_prefix(s.species))     # species changed: tree-oak-1 -> tree-pine-n
    old = obj.data
    obj.data = species.build_mesh(obj.name, s.species, _params(s))
    if old is not None and old.users == 0:
        bpy.data.meshes.remove(old)
    solve_budget(obj, context)


def create_tree(context, values, location):
    name = naming.next_name(name_prefix(values["species"]))
    params = {key: values[key] for key in STRUCTURE_PROPS}
    obj = bpy.data.objects.new(name, species.build_mesh(name, values["species"], params))
    context.collection.objects.link(obj)
    obj.location = location
    with locked():
        for key, value in values.items():
            setattr(obj.treegen, key, value)
        obj.treegen.is_tree = True
    solve_budget(obj, context)
    return obj


# ----------------------------------------------------------------------------
# Game LOD meshes
# ----------------------------------------------------------------------------
def _drop_empty_material_slots(mesh):
    """Realizing instances can leave an empty slot behind. Blender renumbers the faces on pop."""
    for index in reversed(range(len(mesh.materials))):
        if mesh.materials[index] is None:
            mesh.materials.pop(index=index)


def lod_meshes(obj, context, base_name):
    """Three ordinary meshes (foliage made real), named <base_name>_LOD0..2, in the tree's local space."""
    depsgraph = context.evaluated_depsgraph_get()
    meshes = []
    try:
        for lod in range(LOD_COUNT):
            sync_modifier(obj, lod=lod, realize=True)
            depsgraph.update()
            mesh = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)
            mesh.name = "%s_LOD%d" % (base_name, lod)
            for name in SKELETON_ATTRIBUTES:
                attribute = mesh.attributes.get(name)
                if attribute is not None:
                    mesh.attributes.remove(attribute)
            _drop_empty_material_slots(mesh)
            meshes.append(mesh)
    finally:
        sync_modifier(obj)
    return meshes


def export_name(obj):
    """'tree-pine-1' stays as is; anything else unsafe for file / engine asset names -> '_'."""
    return naming.safe(obj.name)


def has_impostor(obj):
    """Trees get a LOD 3 impostor; bushes are not drawn that far away."""
    return not species.SPECIES[obj.treegen.species].get("bush")


def impostor_planes(obj):
    """Crossed planes in the tree's LOD 3: hero trees are worth twice the views."""
    return 4 if obj.treegen.hero else 2


def _impostor(obj, context, lod0, name):
    """(mesh, image) of the tree's LOD 3, rendered from its LOD 0 mesh."""
    return impostor.build(lod0, name + "_LOD3", int(context.scene.treegen.impostor_size),
                          impostor_planes(obj))


def bake_lods(obj, context):
    """Put the LOD meshes in the scene, in a row behind the tree, for inspection."""
    collection = bpy.data.collections.new(obj.name + "_LODs")
    context.scene.collection.children.link(collection)
    baked = []
    name = export_name(obj)
    meshes = lod_meshes(obj, context, name)
    if has_impostor(obj):
        mesh, image = _impostor(obj, context, meshes[0], name)
        image.pack()                    # keep it in the .blend
        meshes.append(mesh)
    for lod, mesh in enumerate(meshes):
        new = bpy.data.objects.new(mesh.name, mesh)
        collection.objects.link(new)
        new.matrix_world = obj.matrix_world.copy()
        new.location.y += (lod + 1) * obj.treegen.canopy * 1.15
        baked.append(new)
    return baked


def _write_fbx(context, objects, path):
    for obj in context.view_layer.objects:
        obj.select_set(False)
    for obj in objects:
        obj.select_set(True)
    context.view_layer.objects.active = objects[0]
    bpy.ops.export_scene.fbx(
        filepath=path, use_selection=True, object_types={"MESH"},
        use_mesh_modifiers=False, mesh_smooth_type="FACE",
        apply_scale_options="FBX_SCALE_ALL", path_mode="STRIP")


@contextmanager
def _exported_textures(folder, species_keys):
    """Save the leaf textures next to the FBX files and, while the FBX files are written,
    point the images at those copies so each FBX material references its texture by file name."""
    saved = []
    images = []
    for key in sorted(species_keys):
        images += [image for image in assets.texture_images(key) if image not in images]
    for image in images:
        stem = os.path.splitext(image.name)[0]
        path = os.path.join(folder, bpy.path.clean_name(stem) + ".png")
        image.save(filepath=path)
        saved.append((image, image.filepath_raw, path))
    try:
        for image, _, path in saved:
            image.filepath_raw = path
        yield [path for _, _, path in saved]
    finally:
        for image, original, _ in saved:
            image.filepath_raw = original


def export_trees(context, trees, folder, per_lod_files):
    """Write each tree's LODs as FBX (centred at the origin), plus the leaf textures and
    each tree's LOD 3 impostor texture."""
    os.makedirs(folder, exist_ok=True)
    selected = list(context.selected_objects)
    active = context.view_layer.objects.active
    collection = bpy.data.collections.new("TreeGen_Export")
    context.scene.collection.children.link(collection)
    written = []
    impostors = []
    try:
        with _exported_textures(folder, {assets.foliage_key(obj.treegen.species, obj.treegen.canopy,
                                                            obj.treegen.leaf_scale) for obj in trees}) as textures:
            written += textures
            for obj in trees:
                name = export_name(obj)
                objects = []
                meshes = lod_meshes(obj, context, name)
                if has_impostor(obj):
                    mesh, image = _impostor(obj, context, meshes[0], name)
                    impostors.append((mesh.materials[0], image))
                    path = os.path.join(folder, mesh.name + ".png")
                    impostor.save(image, path)
                    written.append(path)
                    meshes.append(mesh)
                for mesh in meshes:
                    new = bpy.data.objects.new(mesh.name, mesh)
                    collection.objects.link(new)
                    objects.append(new)
                if per_lod_files:
                    for new in objects:
                        path = os.path.join(folder, new.name + ".fbx")
                        _write_fbx(context, [new], path)
                        written.append(path)
                else:
                    path = os.path.join(folder, name + ".fbx")
                    _write_fbx(context, objects, path)
                    written.append(path)
    finally:
        for new in list(collection.objects):
            mesh = new.data
            bpy.data.objects.remove(new)
            bpy.data.meshes.remove(mesh)
        bpy.data.collections.remove(collection)
        for material, image in impostors:
            bpy.data.materials.remove(material)
            bpy.data.images.remove(image)
        context.view_layer.update()
        for obj in list(context.view_layer.objects):
            if obj is not None:
                obj.select_set(obj in selected)
        context.view_layer.objects.active = active
    return written
