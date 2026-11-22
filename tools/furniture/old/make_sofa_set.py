"""Builds the 1, 2 and 3 seat sofas with build_sofa.py and saves:
  ../sofa_1_seater.blend, ../sofa_2_seater.blend, ../sofa_3_seater.blend
  ../old_sofa_set.blend  (all three in a row, with light + camera)
  ../render/old_sofa_set_render.png
Headless:  blender -b --python make_sofa_set.py   (RENDER=0 env var skips the render)
"""
import os, math, bpy
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, "build_sofa.py")

def build(seats):
    g = {"__file__": BUILD, "__name__": "__sofa__", "SEATS": seats}
    exec(open(BUILD).read(), g)
    return bpy.data.objects[{1: "OldArmchairWingback", 2: "OldSofa2Seater", 3: "OldSofa3Seater"}[seats]]

def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

for seats in (1, 2, 3):
    empty_scene(); build(seats)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, f"sofa_{seats}_seater.blend"))

empty_scene()
for seats, x in ((1, -2.35), (3, -0.35), (2, 2.0)):      # armchair | 3 seater | 2 seater
    build(seats).location.x = x

sc = bpy.context.scene
floor = bpy.data.meshes.new("Floor"); floor.from_pydata(
    [(-6, -4, 0), (6, -4, 0), (6, 4, 0), (-6, 4, 0)], [], [(0, 1, 2, 3)])
fl = bpy.data.objects.new("PreviewFloor", floor); sc.collection.objects.link(fl)
fm = bpy.data.materials.new("PreviewFloorMat"); fm.use_nodes = True
next(n for n in fm.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (0.35, 0.33, 0.31, 1)
floor.materials.append(fm)
sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", 'SUN'))
sun.data.energy = 3.5; sun.rotation_euler = (math.radians(50), 0, math.radians(-35))
sc.collection.objects.link(sun)
world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
next(n for n in world.node_tree.nodes if n.type == "BACKGROUND").inputs["Strength"].default_value = 0.6
cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
cam.location = (0.6, -7.4, 2.6); sc.collection.objects.link(cam); sc.camera = cam
tgt = bpy.data.objects.new("CamTarget", None); tgt.location = (0, 0, 0.45); sc.collection.objects.link(tgt)
c = cam.constraints.new('TRACK_TO'); c.target = tgt; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
cam.data.lens = 35
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "old_sofa_set.blend"))

if os.environ.get("RENDER", "1") != "0":
    try: sc.render.engine = 'CYCLES'
    except TypeError: pass
    sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    sc.render.filepath = os.path.join(ROOT, "render", "old_sofa_set_render.png")
    bpy.ops.render.render(write_still=True)
print("SOFA SET DONE")
