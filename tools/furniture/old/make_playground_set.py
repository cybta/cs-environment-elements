"""Builds the old playground pieces and saves:
  ../playground_slide.blend, ../playground_bench_bin.blend, ../playground_merry_go_round.blend,
  ../playground_seesaw.blend, ../playground_swing_set.blend
  ../old_playground_set.blend  (everything laid out, with sand ground, sun and camera)
  ../render/old_playground_set_render.png
Headless:  blender -b --python make_playground_set.py   (RENDER=0 env var skips the render)
"""
import os, math, bpy
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PIECES = [  # script, saved file, root objects, set position (x, y, rot z degrees)
    ("build_slide.py", "playground_slide.blend", ["PlaygroundSlide"], (3.4, -0.6, 0)),
    ("build_park_bench.py", "playground_bench_bin.blend", ["PlaygroundBench", "PlaygroundBin"], (-0.4, -3.2, 0)),
    ("build_merry_go_round.py", "playground_merry_go_round.blend", ["MerryGoRoundBase"], (0.0, 0.0, 20)),
    ("build_seesaw.py", "playground_seesaw.blend", ["SeesawBase"], (0.4, 3.2, 0)),
    ("build_swing_set.py", "playground_swing_set.blend", ["SwingSet"], (-4.2, 1.0, 90)),
]

def build(script):
    p = os.path.join(HERE, script)
    exec(open(p).read(), {"__file__": p, "__name__": "__playground__"})

def empty_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

for script, fname, _, _ in PIECES:
    empty_scene(); build(script)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, fname))

empty_scene()
for script, _, roots, (x, y, rz) in PIECES:
    build(script)
    for r in roots:
        ob = bpy.data.objects[r]
        ob.location.x += x; ob.location.y += y; ob.rotation_euler.z = math.radians(rz)

sc = bpy.context.scene
ground = bpy.data.meshes.new("Ground"); ground.from_pydata(
    [(-9, -7, 0), (9, -7, 0), (9, 7, 0), (-9, 7, 0)], [], [(0, 1, 2, 3)])
gr = bpy.data.objects.new("PreviewGround", ground); sc.collection.objects.link(gr)
gm = bpy.data.materials.new("PreviewSand"); gm.use_nodes = True
b = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
b.inputs["Base Color"].default_value = (0.36, 0.27, 0.18, 1); b.inputs["Roughness"].default_value = 0.95
ground.materials.append(gm)
sun = bpy.data.objects.new("PreviewSun", bpy.data.lights.new("PreviewSun", 'SUN'))
sun.data.energy = 3.5; sun.data.angle = math.radians(3)
sun.rotation_euler = (math.radians(48), 0, math.radians(-40)); sc.collection.objects.link(sun)
world = bpy.data.worlds.new("PreviewWorld"); sc.world = world; world.use_nodes = True
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs["Color"].default_value = (0.55, 0.62, 0.72, 1); bg.inputs["Strength"].default_value = 0.7
cam = bpy.data.objects.new("PreviewCamera", bpy.data.cameras.new("PreviewCamera"))
cam.location = (6.5, -9.5, 4.6); sc.collection.objects.link(cam); sc.camera = cam
tgt = bpy.data.objects.new("CamTarget", None); tgt.location = (-0.3, 0, 0.7); sc.collection.objects.link(tgt)
c = cam.constraints.new('TRACK_TO'); c.target = tgt; c.track_axis = 'TRACK_NEGATIVE_Z'; c.up_axis = 'UP_Y'
cam.data.lens = 30
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "old_playground_set.blend"))

if os.environ.get("RENDER", "1") != "0":
    try: sc.render.engine = 'CYCLES'
    except TypeError: pass
    sc.cycles.samples = 48; sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    sc.render.filepath = os.path.join(ROOT, "render", "old_playground_set_render.png")
    bpy.ops.render.render(write_still=True)
print("PLAYGROUND SET DONE")
