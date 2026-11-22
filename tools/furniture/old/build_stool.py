"""Round bentwood bar stool matching the chair and table.
Run in Blender (Text Editor > Open > Run Script). Rebuilds the object 'OldBentwoodBarStool'."""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())

begin()

SEAT_Z, SEAT_R = 0.76, 0.18          # seat top, outer radius of the seat ring
RIM_T, RIM_H = 0.016, 0.038
RIM_Z0 = SEAT_Z - RIM_H
PANEL_TOP, PANEL_BOT = SEAT_Z - 0.008, SEAT_Z - 0.022
LEG_R = 0.018

# seat ring + seat panel (panel tucked 4 mm into the ring, slight dish)
lathe(ring_profile(SEAT_R - RIM_T, SEAT_R, RIM_Z0, SEAT_Z), segs=40)
pr = SEAT_R - RIM_T + 0.004
lathe([(0, PANEL_TOP - 0.004), (pr*0.5, PANEL_TOP - 0.003), (pr, PANEL_TOP), (pr, PANEL_BOT), (0, PANEL_BOT)], segs=40)

# legs: tops press against the ring's inner face, feet splay out
LEG_TOP_R = SEAT_R - RIM_T - LEG_R + 0.001
legs = []
for i in range(4):
    a = math.radians(45 + 90*i); d = Vector((math.cos(a), math.sin(a), 0))
    pts = [d*0.235, d*0.195 + Vector((0, 0, 0.37)), d*LEG_TOP_R + Vector((0, 0, PANEL_BOT + 0.001))]
    path = catmull(pts, seg=8)
    tube(path, lambda t: LEG_R*(0.82 + 0.18*min(1, t*1.4)), sides=8)
    legs.append(path)

# foot ring: hoop wrapped round the outside of the legs
FOOT_Z, FOOT_TR = 0.29, 0.011
leg_r_at = at_z(legs[0], FOOT_Z).xy.length
hoop_r = leg_r_at + LEG_R*0.92 + FOOT_TR - 0.002
hoop = [Vector((hoop_r*math.cos(2*math.pi*k/36), hoop_r*math.sin(2*math.pi*k/36), FOOT_Z)) for k in range(36)]
tube(hoop, FOOT_TR, sides=8, closed=True)

# arches between legs rising to the underside of the seat ring (same motif as chair/table)
ARCH_R = 0.009
ARCH_LOW, APEX = 0.50, RIM_Z0 - ARCH_R + 0.0015
for i in range(4):
    p0, p1 = at_z(legs[i], ARCH_LOW), at_z(legs[(i+1) % 4], ARCH_LOW)
    a0 = math.atan2(p0.y, p0.x); a1 = math.atan2(p1.y, p1.x)
    if a1 < a0: a1 += 2*math.pi
    r0 = p0.xy.length; rm = SEAT_R - RIM_T/2
    pts = []
    N = 12
    for k in range(N+1):
        t = k/N; s = math.sin(math.pi*t)
        ang = a0 + (a1-a0)*t; r = r0 + (rm - r0)*s**0.5
        pts.append(Vector((r*math.cos(ang), r*math.sin(ang), ARCH_LOW + (APEX - ARCH_LOW)*s**0.75)))
    tube(pts, ARCH_R, sides=8)

finish("OldBentwoodBarStool", location=(0, 0, 0))
