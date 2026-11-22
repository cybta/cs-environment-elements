"""80s cream metal pendant lamp: wide cone shade with rolled rim, dome cap and stem,
globe bulb, bent-wire hoop under the bulb, plain straight cord and ceiling canopy.

The ORIGIN IS THE CEILING POINT (top of the canopy); the lamp hangs down -Z.
Run in Blender (Text Editor > Open > Run Script). Rebuilds 'PendantLamp80s'.
"""
import os, math
import bpy
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())

CORD_LEN = 0.60          # metres of visible cord; change to fit the ceiling height
PREVIEW_LIGHT = True     # Blender point light at the bulb (Godot: add an OmniLight/SpotLight there)
CREAM, BULB = 0, 1       # material slots

begin()
def part(slot, fn, *a, **k):
    before = set(bm.faces); fn(*a, **k)
    for f in set(bm.faces) - before: f.material_index = slot

def arc(r, z_c, a0, a1, n):
    return [(r*math.cos(a), z_c + r*math.sin(a)) for a in
            (a0 + (a1 - a0)*i/n for i in range(n + 1))]

# ---- vertical layout (all negative, origin = ceiling) ----
CAN_H, CAN_R = 0.025, 0.045
STEM_TOP = -(CAN_H + CORD_LEN); STEM_H, STEM_R = 0.075, 0.012
DOME_R = 0.048
DOME_Z = STEM_TOP - STEM_H - DOME_R + 0.003       # dome centre = top of the shade
SHADE_R0, SHADE_R1, SHADE_H, T = 0.044, 0.21, 0.12, 0.003
RIM_Z = DOME_Z - SHADE_H
BULB_R = 0.04; BULB_Z = RIM_Z + 0.015   # dips just below the rim

# ceiling canopy (closed cup)
part(CREAM, lathe, [(0, 0), (CAN_R, 0), (CAN_R, -CAN_H + 0.004), (CAN_R - 0.004, -CAN_H), (0, -CAN_H)], segs=24)
# cord: canopy -> stem
part(CREAM, tube, [Vector((0, 0, -CAN_H + 0.003)), Vector((0, 0, STEM_TOP - 0.003))], 0.0035, sides=6)
# stem with a rounded top
part(CREAM, lathe, [(0, STEM_TOP), (STEM_R - 0.003, STEM_TOP), (STEM_R, STEM_TOP - 0.003),
                    (STEM_R, STEM_TOP - STEM_H), (0, STEM_TOP - STEM_H)], segs=16)
# dome cap: quarter sphere down to the shade top
dome = [(0, DOME_Z + DOME_R)] + arc(DOME_R, DOME_Z, math.pi/2, 0, 8)[1:] + [(0, DOME_Z)]
part(CREAM, lathe, dome, segs=32)

# shade: thin cone with a rolled rim (closed profile: outer face, bead, inner face)
slope = SHADE_H/(SHADE_R1 - SHADE_R0)
z_out = lambda r: RIM_Z + (SHADE_R1 - r)*slope              # outer cone surface
z_in = lambda r: z_out(r) + T*math.sqrt(1 + slope*slope)    # inner surface, wall T thick
BEAD = 0.0035
shade = [(SHADE_R0, z_out(SHADE_R0)), (SHADE_R1, RIM_Z)]
shade += [(SHADE_R1 + BEAD*math.cos(a), RIM_Z - BEAD + BEAD*math.sin(a)) for a in
          (math.radians(d) for d in (60, 0, -60, -120, -180))]          # rolled bead
shade += [(SHADE_R1 - BEAD, z_in(SHADE_R1 - BEAD)), (SHADE_R0, z_in(SHADE_R0)), (SHADE_R0, z_out(SHADE_R0))]
part(CREAM, lathe, shade, segs=48)

# bulb socket + globe bulb
part(CREAM, lathe, [(0, DOME_Z), (0.017, DOME_Z), (0.017, BULB_Z + BULB_R*0.8), (0, BULB_Z + BULB_R*0.8)], segs=16)
part(BULB, lathe, [(0, BULB_Z + BULB_R)] + arc(BULB_R, BULB_Z, math.pi/2, -math.pi/2, 12)[1:-1]
     + [(0, BULB_Z - BULB_R)], segs=24)

# bent-wire hoop: straight legs up into the shade, semicircle under the bulb
HOOP_R, WIRE = 0.08, 0.0022
hoop_c = RIM_Z + 0.035
z_attach = RIM_Z + (SHADE_R1 - HOOP_R)*slope - T     # inner shade surface at r = HOOP_R
path = [Vector((-HOOP_R, 0, z_attach))]
path += [Vector((HOOP_R*math.cos(a), 0, hoop_c + HOOP_R*math.sin(a)))
         for a in (math.pi + math.pi*i/16 for i in range(17))]
path += [Vector((HOOP_R, 0, z_attach))]
part(CREAM, tube, path, WIRE, sides=6)

ob = finish("PendantLamp80s", location=(0, 0, 0), material=["CreamEnamel", "BulbGlow"])

if PREVIEW_LIGHT:
    lt = bpy.data.objects.get("PendantLamp80s_Light")
    if lt: bpy.data.objects.remove(lt, do_unlink=True)
    ld = bpy.data.lights.new("PendantLamp80s_Light", 'POINT')
    ld.energy = 25; ld.color = (1.0, 0.85, 0.65); ld.shadow_soft_size = BULB_R*0.8
    lt = bpy.data.objects.new("PendantLamp80s_Light", ld); bpy.context.collection.objects.link(lt)
    # just under the bulb: inside it, the closed glass mesh would shadow the light
    lt.parent = ob; lt.location = (0, 0, BULB_Z - BULB_R - 0.006)
