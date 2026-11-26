"""Far LODs baked to ONE material: fewer draw calls for buildings seen from a distance.

A cottage's LOD2 / LOD3 still carry every material of the house (~10: lap paint, trim, roof, logs, brick,
plinth, lining, window...) and a game draws each one separately: ~10 draw calls per house at any distance.
bake_far gives each of those meshes its own UV map (smart project, uniform texel size), bakes the base colour
of all its materials into one image (Cycles, emission pass: the paint shaders' colour and peel, rust, the
tinted textures, exactly as Blender shows them, no lighting), then swaps the materials for one plain material
with that image. What is lost is what a distant house can't show anyway: normal maps and roughness detail.

Destructive (the LOD meshes change): run it on a copy in memory, e.g. at export (export_old_neighborhood.py),
so the bake always follows the colours tuned in the .blend. lod.build puts the many-material LODs back.
"""

import math
import os

import bpy

SIZES = {2: 1024, 3: 512}          # px: LOD2 shows from ~80 m (~4 cm a texel on a cottage), LOD3 from ~180 m
BAKE_UV = "BakeUV"
ROUGHNESS = 0.85


def _out_and_bsdf(mat):
    nt = mat.node_tree
    out = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output), None)
    if out is None or not out.inputs["Surface"].links:
        return out, None
    sh = out.inputs["Surface"].links[0].from_node
    return out, sh if "Base Color" in sh.inputs else None


def _emit_base_colour(mats):
    """Wire each material's base colour straight to its output as emission -> what to undo."""
    undo = []
    for mat in mats:
        if mat is None or not mat.use_nodes:
            continue
        nt = mat.node_tree
        out, bsdf = _out_and_bsdf(mat)
        if out is None:
            continue
        old = out.inputs["Surface"].links[0].from_socket if out.inputs["Surface"].links else None
        emit = nt.nodes.new("ShaderNodeEmission")
        emit.inputs["Strength"].default_value = 1.0
        if bsdf is not None:
            bc = bsdf.inputs["Base Color"]
            if bc.links:
                nt.links.new(bc.links[0].from_socket, emit.inputs["Color"])
            else:
                emit.inputs["Color"].default_value = bc.default_value
        else:
            emit.inputs["Color"].default_value = tuple(mat.diffuse_color)
        nt.links.new(emit.outputs[0], out.inputs["Surface"])
        target = nt.nodes.new("ShaderNodeTexImage")      # the bake writes into the active image node
        undo.append((mat, out, old, emit, target))
    return undo


def _undo(undo):
    for mat, out, old, emit, target in undo:
        nt = mat.node_tree
        nt.nodes.remove(emit)
        nt.nodes.remove(target)
        if old is not None:
            nt.links.new(old, out.inputs["Surface"])


def _unwrap(ob):
    me = ob.data
    uv = me.uv_layers.get(BAKE_UV) or me.uv_layers.new(name=BAKE_UV)
    render = next((u for u in me.uv_layers if u.active_render), None)
    me.uv_layers.active = uv                             # the bake target and smart project use the active one...
    if render is not None and render != uv:
        render.active_render = True                      # ...the materials keep reading their own (render) UVs
    _only(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.004, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def _only(ob):
    """Make ob the one selected, active object (bake and edit mode work on the view layer's selection)."""
    vl = bpy.context.view_layer
    for o in vl.objects:
        if o.select_get():
            o.select_set(False)
    ob.select_set(True)
    vl.objects.active = ob


def _far_material(name, img):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = ROUGHNESS
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def _setup_scene(scene):
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 4                             # emission only: a few samples just anti-alias the texels
    scene.render.bake.margin = 4
    scene.render.bake.use_clear = True
    scene.render.bake.target = "IMAGE_TEXTURES"


def bake_far(root, out_dir, levels=(2, 3)):
    """Bake the root's LOD meshes of these levels to one image + one material each -> number baked.
    Images are saved as JPEG in out_dir (the glTF exporter then embeds them as JPEG)."""
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    _setup_scene(scene)
    done = 0
    for ob in [o for o in root.children_recursive if o.type == "MESH" and o.get("lod", 0) in levels]:
        me = ob.data
        size = SIZES.get(ob["lod"], 512)
        if not me.polygons or len(me.materials) < 2:
            continue
        ob.hide_viewport = False
        ob.hide_render = False
        ob.hide_set(False)
        _unwrap(ob)
        img = bpy.data.images.new(f"{ob.name}_bake", size, size, alpha=False)
        undo = _emit_base_colour(list(me.materials))
        for mat, _out, _old, _emit, target in undo:
            target.image = img
            mat.node_tree.nodes.active = target
        _only(ob)
        bpy.ops.object.bake(type="EMIT")
        _undo(undo)
        path = os.path.join(out_dir, f"{ob.name}_bake.jpg")
        img.filepath_raw = path
        img.file_format = "JPEG"
        scene.render.image_settings.quality = 90
        img.save()
        img.source = "FILE"
        img.filepath = path
        img.reload()
        # one material, one UV map, no paint data: the paint is in the picture now
        for u in [u for u in me.uv_layers if u.name != BAKE_UV]:
            me.uv_layers.remove(u)
        for c in list(me.color_attributes):
            me.color_attributes.remove(c)
        me.materials.clear()
        me.materials.append(_far_material(f"{ob.name}_far", img))
        me.polygons.foreach_set("material_index", [0] * len(me.polygons))
        me.update()
        done += 1
    return done
