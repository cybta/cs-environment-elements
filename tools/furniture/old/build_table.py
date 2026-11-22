"""Round bentwood cafe table (Thonet era) matching the chair.
Run in Blender (Text Editor > Open > Run Script). Rebuilds the object 'OldBentwoodTable'."""
import os, math
from mathutils import Vector
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())

begin()

TOP_Z, TOP_T, TOP_R = 0.74, 0.022, 0.35
UNDER = TOP_Z - TOP_T                       # underside of the top
AP_RO, AP_RI, AP_Z0 = 0.300, 0.284, 0.655   # apron ring under the top
LEG_R = 0.020

# top with a rounded edge
e = 0.006
lathe([(0, TOP_Z), (TOP_R - e, TOP_Z), (TOP_R - e*0.3, TOP_Z - e*0.3), (TOP_R, TOP_Z - e),
       (TOP_R, UNDER + e), (TOP_R - e*0.3, UNDER + e*0.3), (TOP_R - e, UNDER), (0, UNDER)])

# apron ring, pressed 1 mm into the underside of the top
lathe(ring_profile(AP_RI, AP_RO, AP_Z0, UNDER + 0.001))

# legs: tops touch the apron's inner face, feet splay out
LEG_TOP_R = AP_RI - LEG_R + 0.001
legs = []
for i in range(4):
    a = math.radians(45 + 90*i); d = Vector((math.cos(a), math.sin(a), 0))
    pts = [d*0.315, d*0.283 + Vector((0, 0, 0.36)), d*LEG_TOP_R + Vector((0, 0, UNDER + 0.001))]
    path = catmull(pts, seg=8)
    tube(path, lambda t: LEG_R*(0.8 + 0.2*min(1, t*1.4)), sides=8)
    legs.append(path)

# arches between legs, following the apron circle in plan, crowns touching its underside
ARCH_R = 0.011
ARCH_LOW, APEX = 0.43, AP_Z0 - ARCH_R + 0.0015
for i in range(4):
    p0, p1 = at_z(legs[i], ARCH_LOW), at_z(legs[(i+1) % 4], ARCH_LOW)
    a0 = math.atan2(p0.y, p0.x); a1 = math.atan2(p1.y, p1.x)
    if a1 < a0: a1 += 2*math.pi
    r0 = p0.xy.length; rm = (AP_RO + AP_RI)/2
    pts = []
    N = 14
    for k in range(N+1):
        t = k/N; s = math.sin(math.pi*t)
        ang = a0 + (a1-a0)*t; r = r0 + (rm - r0)*s**0.5
        pts.append(Vector((r*math.cos(ang), r*math.sin(ang), ARCH_LOW + (APEX - ARCH_LOW)*s**0.75)))
    tube(pts, ARCH_R, sides=8)

finish("OldBentwoodTable", location=(0, 0, 0))
