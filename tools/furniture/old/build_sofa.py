"""Old upholstered sofas: 1, 2 or 3 seats.

SEATS = 2 or 3: rolled-arm camelback sofa (ref/sofa, plaid one), tight back,
          one seat cushion per seat, short tapered wood legs. 'PlaidFabric'.
SEATS = 1: wingback armchair (ref/sofa, green one): tall arched back, flared
          wings, rolled arms, loose seat cushion, splayed tapered legs. 'GreenVelvet'.

AGED = True (default) runs sofa_age_lib.age_sofa(): sagging, lumpy, dented, torn and
grimy, with worn fabric textures ('PlaidFabricWorn' / 'GreenVelvetWorn'), then decimates to
about 10k / 12k / 14k tris. AGED = False gives the original clean sofa (about 2.5-3k tris).

Origin: floor, centre of the footprint. Front faces -Y. Material slots: 0 fabric,
1 OldWornWood (legs), 2 ExposedStuffing (tears, aged only). Run in Blender (Text Editor > Open > Run Script), or set SEATS
before exec() as make_sofa_set.py does. Rebuilds 'OldSofa3Seater' / 'OldSofa2Seater' /
'OldArmchairWingback'.
"""
import os, math
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "bentwood_lib.py")).read())
exec(open(os.path.join(HERE, "sofa_lib.py")).read())
exec(open(os.path.join(HERE, "sofa_age_lib.py")).read())

SEATS = globals().get("SEATS", 3)
AGED = globals().get("AGED", True)       # False: the clean, factory-new sofa
FABRIC, WOOD = 0, 1
CHAIR = SEATS == 1

# ---------------- dimensions (metres) ----------------
if CHAIR:
    SEAT_W, ARM_W, OVER, ARM_H, LEG_H = 0.56, 0.14, 0.04, 0.66, 0.14
    Y0, Y1 = -0.43, 0.40                  # arm front / back
    BACK_Y0, BACK_Y1, BACK_ZB = 0.20, 0.40, 0.16
    BACK_END, BACK_PEAK = 1.03, 1.10
    SEAT_Z0, SEAT_Z1 = 0.40, 0.53
else:
    SEAT_W, ARM_W, OVER, ARM_H, LEG_H = 0.60, 0.17, 0.05, 0.64, 0.10
    Y0, Y1 = -0.45, 0.42
    BACK_Y0, BACK_Y1, BACK_ZB = 0.22, 0.42, 0.12
    BACK_END, BACK_PEAK = 0.76, 0.88 + 0.02*(SEATS - 2)
    SEAT_Z0, SEAT_Z1 = 0.36, 0.47
XI = SEATS*SEAT_W/2                       # inner face of each arm
LEAN = 0.15                               # backrest leans back (y per metre of z)
lean = lambda y, z: y + LEAN*max(z - SEAT_Z0, 0)

begin()
part_layer()                              # create before any face exists
def paint(faces, slot, part=PART_LEGS):
    for f in faces: f.material_index = slot
    return tag(faces, part)

# ---------------- base / seat deck ----------------
paint(box((-XI - 0.01, Y0 + 0.02, LEG_H), (XI + 0.01, BACK_Y1 - 0.02, SEAT_Z0 + 0.005),
          bevel=0.03, segs=2), FABRIC, PART_DECK)

# ---------------- seat cushions ----------------
for i in range(SEATS):
    x0, x1 = -XI + i*SEAT_W + 0.003, -XI + (i + 1)*SEAT_W - 0.003
    paint(sweep(rrect(x0, Y0 - 0.01, x1, BACK_Y0 + 0.06, 0.05), SEAT_Z0, SEAT_Z1, 0.025, 0.045,
                lambda a, b, w: (a, b, w)), FABRIC, PART_CUSHION + i)

# ---------------- rolled arms ----------------
arm = rolled_arm_outline(ARM_W, ARM_H, LEG_H, OVER)
for s in (1, -1):
    to_w = lambda a, b, w, s=s: (s*(XI + a), w, b)
    paint(sweep(arm, Y0, Y1, 0.03, 0.02, to_w), FABRIC, PART_ARM + (s < 0))
    # piped scroll disc on the front of the roll
    r = (ARM_W + OVER)/2
    paint(sweep(arc(r, ARM_H - r, r*0.86, 0, 337.5, 15), Y0 - 0.014, Y0 + 0.01, 0.008, 0, to_w),
          FABRIC, PART_DISC + (s < 0))

# ---------------- backrest ----------------
XM = XI + (ARM_W if CHAIR else 0.12)      # back ends: chair = full width, sofa = inside arms
RC = 0.09 if CHAIR else 0.07              # rounded top corners
def top(x):
    if CHAIR: return BACK_PEAK - (BACK_PEAK - BACK_END)*(x/XM)**2
    t = min(abs(x)/(XM - RC), 1.0)        # camelback: flat crown easing down to the arms
    return BACK_END - RC*0.3 + (BACK_PEAK - BACK_END + RC*0.3)*(1 - (3*t*t - 2*t**3))
ztop = top(XM - RC)
back = [(-XM, BACK_ZB), (XM, BACK_ZB)] + arc(XM - RC, ztop - RC, RC, 0, 90, 4)[:-1]
n = 20 if CHAIR else 28
back += [(XM - RC - (2*(XM - RC))*k/n, top(XM - RC - (2*(XM - RC))*k/n)) for k in range(n + 1)]
back += arc(-XM + RC, ztop - RC, RC, 90, 180, 4)[1:]
paint(sweep(back, BACK_Y0, BACK_Y1, 0.06, 0.03, lambda a, b, w: (a, lean(w, b), b)), FABRIC, PART_BACK)

# ---------------- wings (armchair) ----------------
if CHAIR:
    wing = [(0.38, 0.56), (0.10, 0.58), (-0.12, 0.60), (-0.19, 0.66), (-0.21, 0.74),
            (-0.20, 0.82), (-0.15, 0.89), (-0.07, 0.94), (0.04, 0.975), (0.16, 0.99),
            (0.28, 0.985), (0.38, 0.95)]
    wing = [(y, z if z < 0.6 else 0.6 + (z - 0.6)*1.13) for y, z in wing]   # up to ~1.05
    FLARE = 0.12
    for s in (1, -1):
        to_w = lambda a, b, w, s=s: (s*(w + FLARE*(0.38 - a)), lean(a, b), b)
        paint(sweep(wing, XM - 0.10, XM, 0.035, 0.03, to_w), FABRIC, PART_WING + (s < 0))

# ---------------- legs ----------------
LX, LY = XI + ARM_W*0.55, (0.34 if CHAIR else 0.36)
for sx in (1, -1):
    for sy in (-1, 1):
        if CHAIR:
            tapered_leg((sx*LX, sy*LY, LEG_H + 0.006), LEG_H + 0.006, 0.024, 0.013,
                        splay=(sx*0.015, 0.035 if sy > 0 else -0.02), slot=WOOD)
        else:
            tapered_leg((sx*LX, sy*LY, LEG_H + 0.006), LEG_H + 0.006, 0.026, 0.017,
                        splay=(sx*0.01, sy*0.01), slot=WOOD)
if SEATS == 3:                            # centre support legs under a long frame
    for sy in (-1, 1):
        tapered_leg((0, sy*LY, LEG_H + 0.006), LEG_H + 0.006, 0.026, 0.017, slot=WOOD)

NAME = {1: "OldArmchairWingback", 2: "OldSofa2Seater", 3: "OldSofa3Seater"}[SEATS]
if AGED:
    age_sofa(dict(seats=SEATS, chair=CHAIR, XI=XI, Y0=Y0, Y1=Y1, ARM_W=ARM_W, ARM_H=ARM_H,
                  LEG_H=LEG_H, SEAT_W=SEAT_W, SEAT_Z0=SEAT_Z0, SEAT_Z1=SEAT_Z1,
                  back_top=BACK_PEAK), seed=SEATS*7 + 3)
    fabric = "GreenVelvetWorn" if CHAIR else "PlaidFabricWorn"
    mats = [fabric, "OldWornWood", "ExposedStuffing"]
else:
    mats = ["GreenVelvet" if CHAIR else "PlaidFabric", "OldWornWood"]
bm.faces.layers.int.remove(part_layer())
ob = finish(NAME, location=(0, 0, 0), material=mats)
if AGED:
    ob.data.color_attributes.render_color_index = ob.data.color_attributes.active_color_index = 0
    decimate(ob, 8000 + 2000*SEATS)      # ~10k / 12k / 14k tris for 1 / 2 / 3 seats
