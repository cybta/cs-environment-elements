"""LOD 3: a crossed-plane impostor for the furthest distance.

The complete LOD 0 tree is rendered with an orthographic camera from evenly spaced
directions round the trunk, one per plane, into the cells of one texture with alpha. The
mesh is that many upright quads crossing on the trunk axis. Two planes (4 triangles, seen
from 4 sides) for ordinary trees, four planes (8 triangles, 8 sides) for hero trees.
"""

import math

import os

import bpy
import numpy as np

from . import assets

MARGIN = 1.02           # the planes are this much larger than the tree, so nothing touches the edge


def triangles(planes):
    return 2 * planes


def _grid(planes):
    """(columns, rows) of the texture's cells: 2 x 1 for two planes, 2 x 2 for four."""
    columns = 2 if planes > 1 else 1
    return columns, math.ceil(planes / columns)


def _extents(mesh, angles):
    """(half width of each plane, bottom, top). Plane i lies along the horizontal direction
    at angles[i] and is centred on the trunk."""
    co = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    halves = [max(float(np.abs(co[:, 0] * math.cos(a) + co[:, 1] * math.sin(a)).max()), 0.05) * MARGIN
              for a in angles]
    bottom = max(float(co[:, 2].min()), 0.0)            # roots under the ground are not drawn
    top = bottom + max(float(co[:, 2].max()) - bottom, 0.05) * MARGIN
    return halves, bottom, top


def _bleed(rgba, passes=32):
    """Spread the colours at the outline under the transparent pixels, so texture filtering
    and mip-maps in the game do not pull a dark fringe in from the background."""
    height, width = rgba.shape[:2]
    known = rgba[..., 3] > 0.5
    rgb = rgba[..., :3] * known[..., None]
    for _ in range(passes):
        if known.all() or not known.any():
            break
        colour = np.pad(rgb * known[..., None], ((1, 1), (1, 1), (0, 0)))
        weight = np.pad(known.astype(np.float32), 1)
        total = np.zeros_like(rgb)
        count = np.zeros((height, width), np.float32)
        for dy in range(3):
            for dx in range(3):
                total += colour[dy:dy + height, dx:dx + width]
                count += weight[dy:dy + height, dx:dx + width]
        grow = ~known & (count > 0)
        rgb[grow] = total[grow] / count[grow][:, None]
        known |= grow
    rgba[..., :3] = rgb


def _render_views(source, angles, extents, size):
    """Render `source` (a mesh) facing each plane. Returns one (size, size, 4) array per
    plane, rows bottom to top, each stretched to fill its square cell."""
    halves, bottom, top = extents
    height = top - bottom
    distance = 2.0 * max(halves) + 10.0

    scene = bpy.data.scenes.new("TreeGen_Impostor")
    tree = bpy.data.objects.new("TreeGen_Impostor_Source", source)
    camera_data = bpy.data.cameras.new("TreeGen_Impostor_Camera")
    camera = bpy.data.objects.new("TreeGen_Impostor_Camera", camera_data)
    world = bpy.data.worlds.new("TreeGen_Impostor_World")
    path = os.path.join(bpy.app.tempdir, "treegen_impostor.png")
    views = []
    try:
        scene.collection.objects.link(tree)
        scene.collection.objects.link(camera)
        scene.camera = camera
        camera_data.type = "ORTHO"
        camera_data.clip_start, camera_data.clip_end = 0.1, 2.0 * distance
        # Even white light from every side and no sun: the texture holds the tree's own
        # colours, and the game's lighting does the rest.
        world.use_nodes = True
        background = world.node_tree.nodes["Background"]
        background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        background.inputs["Strength"].default_value = 1.0
        scene.world = world

        render = scene.render
        try:
            render.engine = "BLENDER_EEVEE_NEXT"
        except TypeError:                               # Blender 5: it is called EEVEE again
            render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = 32
        render.film_transparent = True
        render.resolution_x = render.resolution_y = size
        render.resolution_percentage = 100
        render.image_settings.file_format = "PNG"
        render.image_settings.color_mode = "RGBA"
        render.image_settings.color_depth = "8"
        render.filepath = path
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "None"

        middle = 0.5 * (bottom + top)
        for angle, half in zip(angles, halves):
            # Angle 0 looks along +Y at the plane lying along X; the camera turns with the plane.
            width = 2.0 * half
            camera.location = (math.sin(angle) * distance, -math.cos(angle) * distance, middle)
            camera.rotation_euler = (math.pi / 2, 0.0, angle)
            # Non-square pixels stretch the tree's width x height onto the square cell.
            render.pixel_aspect_x = max(width / height, 1.0)
            render.pixel_aspect_y = max(height / width, 1.0)
            camera_data.ortho_scale = max(width, height)
            bpy.ops.render.render(write_still=True, scene=scene.name)
            image = bpy.data.images.load(path, check_existing=False)
            pixels = np.empty(size * size * 4, np.float32)
            image.pixels.foreach_get(pixels)
            bpy.data.images.remove(image)
            view = pixels.reshape(size, size, 4)
            _bleed(view)
            views.append(view)
    finally:
        bpy.data.scenes.remove(scene)
        bpy.data.objects.remove(tree)
        bpy.data.objects.remove(camera)
        bpy.data.cameras.remove(camera_data)
        bpy.data.worlds.remove(world)
        if os.path.exists(path):
            os.remove(path)
    return views


def _material(name, image):
    mat, nodes, links, bsdf = assets._new_material(name)
    mat.use_backface_culling = False
    if hasattr(mat, "blend_method"):
        mat.blend_method = "CLIP"
        mat.alpha_threshold = 0.5
    bsdf.inputs["Roughness"].default_value = 0.9
    uv = nodes.new("ShaderNodeAttribute")
    uv.attribute_name = "UVMap"
    uv.location = (-900, 200)
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.location = (-700, 200)
    links.new(uv.outputs["Vector"], tex.inputs["Vector"])
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
    return mat


def _cross_mesh(name, angles, extents):
    halves, bottom, top = extents
    columns, rows = _grid(len(angles))
    verts, uvs, faces = [], [], []
    for index, (angle, half) in enumerate(zip(angles, halves)):
        x, y = math.cos(angle) * half, math.sin(angle) * half
        u, v = (index % columns) / columns, (index // columns) / rows
        base = len(verts)
        verts += [(-x, -y, bottom), (x, y, bottom), (x, y, top), (-x, -y, top)]
        uvs += [(u, v), (u + 1.0 / columns, v), (u + 1.0 / columns, v + 1.0 / rows), (u, v + 1.0 / rows)]
        faces += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    loop_verts = np.zeros(len(mesh.loops), np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    mesh.uv_layers.new(name="UVMap").data.foreach_set("uv", np.array(uvs, np.float32)[loop_verts].ravel())
    mesh.update()
    return mesh


def build(source, name, size, planes=2):
    """The impostor of `source` (the tree's LOD 0 mesh): a mesh called `name` with its own
    material, and the image that material uses (cells of size x size pixels, see _grid)."""
    angles = [index * math.pi / planes for index in range(planes)]
    extents = _extents(source, angles)
    views = _render_views(source, angles, extents, size)
    columns, rows = _grid(planes)
    views += [np.zeros((size, size, 4), np.float32)] * (columns * rows - planes)
    atlas = np.concatenate([np.concatenate(views[row * columns:(row + 1) * columns], axis=1)
                            for row in range(rows)], axis=0)
    image = bpy.data.images.new(name, columns * size, rows * size, alpha=True)
    image.pixels.foreach_set(atlas.ravel())
    mesh = _cross_mesh(name, angles, extents)
    mesh.materials.append(_material("TreeGen_Impostor_" + name, image))
    return mesh, image


def save(image, path):
    """Write the impostor texture as a PNG; its material then refers to that file."""
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
