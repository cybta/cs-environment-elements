"""House Generator: builds a random multi-room house from a few numbers.

The floor plan comes from house_layout (pure Python); this module holds the settings
and turns a plan into Blender objects. The panel and operators are in house_ui.
"""

import bpy
from mathutils import Vector
from bpy.types import PropertyGroup
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty,
                       StringProperty)

from . import cottage_layout as cl
from . import cottage_paint
from . import fence
from . import house_layout as hl
from ..core import neighborhood_materials as nm
from . import shop_materials as sm
from . import shop_ui
from . import villa_layout as vl
from .house_roof import _build_roof
from .villa_stair import FACES as FENCE_FACES
from .mesh_utils import _solid, glass_fence, sloped_fence, _boxes_mesh, _clip_mesh, _mat_index, _obj, _paint_by_normal  # noqa: F401 (neighborhood uses them)
from ..core.materials import MATERIAL_ENUM_ITEMS, _default_set


# Ground-floor top above the ground (the cursor). Plans put the floor top at z = 0 with
# the outdoor ground under it: one slab down for houses and villas, piles or a plinth
# (0.78 m) down for cottages, so these lift them onto the ground. Shops go up 0.15 m:
# their own street sidewalk is 0.15 m below the floor, so it lands on the ground and the
# half step at each door stays.
HOUSE_LIFT = 0.2
LIFTS = {"COTTAGE": 0.75, "SHOPS": 0.15}
GRAVEL_TOP = 0.04         # the cottage's gravel bed stands proud of the ground


def _type_changed(self, context):
    """Villas are bigger than the default house: bump the area when switching to one.
    A cottage is small, with low rooms and thinner timber walls."""
    t = self.building_type
    if t == "FENCE":
        return
    self.ground_lift = LIFTS.get(t, HOUSE_LIFT)
    shop_ui.apply_construction(self, t == "SHOPS")
    if t == "SHOPS":
        return
    if t == "COTTAGE":
        if not cl.MIN_AREA <= self.total_area <= 140.0:
            self.total_area = 60.0
        self.ceiling_height, self.ext_wall, self.bedrooms, self.bathrooms = 2.5, 0.18, 2, 0
        return
    if abs(self.ceiling_height - 2.5) < 1e-4 and abs(self.ext_wall - 0.18) < 1e-4:    # back from a cottage
        self.ceiling_height, self.ext_wall = 2.7, 0.25
    if t.startswith("VILLA") and self.total_area < vl.MIN_AREA[t[6:]] + 20:
        self.total_area = 240.0 if t == "VILLA_MODERN" else 200.0


# Panel sections, in the order they are listed. Villa has sub-types (villa_style);
# more sections get added here. Both are views onto building_type, so scenes saved
# before sections existed (and the Surroundings generator, which sets building_type)
# stay in step.
SECTIONS = [
    ("VILLA", "Villa", "Fancy new two-storey villas: modern or gable", "HOME", 0),
    ("HOUSE", "House", "A plain house: one rectangular block, any roof", "HOME", 1),
    ("COTTAGE", "Cottage", "An old timber dacha on piles", "HOME", 2),
    ("SHOPS", "Shops", "A row of old high-street shops", "HOME", 3),
    ("FENCE", "Fences", "An old wooden board fence round any outline, with a door and a parking gate",
     "MOD_LATTICE", 4),
]
COTTAGE_STYLES = [("TIMBER", "Old Timber", "Weathered bare timber siding under a gambrel roof, on steel piles"),
                  ("PAINTED", "Painted", "Weathered painted boards under an open gable roof, on a brick plinth")]
VILLA_STYLES = [("MODERN", "Modern", "Flat-roofed box with a carport and a stone bay"),
                ("GABLE", "Gable", "Steep street gable, timber bay, terrace and carport wing")]


def _get_section(self):
    t = self.building_type
    key = "VILLA" if t.startswith("VILLA") else t
    return next(i for k, _, _, _, i in SECTIONS if k == key)


def _set_section(self, value):
    key = SECTIONS[value][0]
    if key == "VILLA":
        if not self.building_type.startswith("VILLA"):
            self.building_type = "VILLA_" + self.villa_last
    elif self.building_type != key:
        self.building_type = key


def _get_villa_style(self):
    t = self.building_type
    return 1 if (t if t.startswith("VILLA") else "VILLA_" + self.villa_last) == "VILLA_GABLE" else 0


def _set_villa_style(self, value):
    self.villa_last = VILLA_STYLES[value][0]
    self.building_type = "VILLA_" + self.villa_last


class HOUSEGEN_Settings(PropertyGroup):
    house_name: StringProperty(name="Name", default="House")
    building_type: EnumProperty(
        name="Type",
        description="What to build",
        items=[
            ("HOUSE", "House", "A plain house: one rectangular block, any roof"),
            ("VILLA_MODERN", "Modern Villa", "Flat-roofed two-storey box: a carport cut into the front, a balcony "
             "recessed above it, and a stone-clad bay with tall glazing"),
            ("VILLA_GABLE", "Gable Villa", "A steep gable facing the street: the upper floor sits inside the roof, "
             "with a glazed gable and balcony, a timber-clad bay, a covered terrace and a carport wing"),
            ("COTTAGE", "Old Cottage", "An old dacha (Old Timber or Painted style): weathered siding, a gambrel or open gable roof in "
             "corrugated sheet with bedrooms in the attic, and a covered veranda across the front"),
            ("SHOPS", "Shopping Row", "Old high-street shops side by side: glazed shopfronts with awnings and "
             "signs, and a shared entrance with a stair up to the rooms behind the tall upper windows"),
            ("FENCE", "Fences", "Not a building: the panel shows the fence tools"),
        ],
        default="HOUSE", update=_type_changed,
    )
    section: EnumProperty(name="Building", description="What to build", items=SECTIONS,
                          get=_get_section, set=_set_section)
    villa_style: EnumProperty(name="Villa", items=VILLA_STYLES, get=_get_villa_style, set=_set_villa_style)
    villa_last: StringProperty(default="MODERN")
    shop: PointerProperty(type=shop_ui.SHOPGEN_Settings)
    fence: PointerProperty(type=fence.FENCEGEN_Settings)
    villa_pitch: FloatProperty(name="Roof Pitch (°)", description="Slope of the gable villa's roof",
                               default=42.0, min=30.0, max=45.0, step=100)
    villa_site: BoolProperty(name="Driveway & Paving", description="Driveway, front path and a paved strip "
                             "behind the house", default=True)
    villa_pool: BoolProperty(name="Pool", description="A pool in the back garden", default=False)
    cottage_style: EnumProperty(name="Cottage Style", items=COTTAGE_STYLES, default="TIMBER")
    # Cottage paint (cottage_paint / core.paint): changing these repaints the selected cottage
    cottage_roof: EnumProperty(name="Roof Sheet", items=nm.COTTAGE_ROOF_ITEMS, default="RANDOM",
                               update=cottage_paint.on_change)
    cottage_roof_color: FloatVectorProperty(name="Roof Colour", subtype="COLOR_GAMMA", size=3, min=0.0, max=1.0,
                                            default=nm.COTTAGE_ROOFS[0][2], update=cottage_paint.on_change)
    cottage_roof_peel: FloatProperty(name="Roof Peeling", default=0.3, min=0.0, max=1.0, subtype="FACTOR",
                                     update=cottage_paint.on_change,
                                     description="How much of the roof paint has gone: 0 = fresh, 1 = bare "
                                                 "rusty sheet")
    cottage_paint: EnumProperty(name="Paint", items=nm.COTTAGE_PAINT_ITEMS, default="RANDOM",
                                update=cottage_paint.on_change)
    cottage_paint_color: FloatVectorProperty(name="Paint Colour", subtype="COLOR_GAMMA", size=3, min=0.0, max=1.0,
                                             default=nm.COTTAGE_PAINTS[1][3], update=cottage_paint.on_change)
    cottage_peel: FloatProperty(name="Peeling", default=0.27, min=0.0, max=1.0, subtype="FACTOR",
                                update=cottage_paint.on_change,
                                description="How much of the siding paint has flaked off: 0 = fresh, 1 = bare wood")
    cottage_siding: EnumProperty(name="Siding", items=nm.COTTAGE_SIDING_ITEMS, default="RANDOM")
    cottage_chimney: BoolProperty(name="Chimney", description="A brick stove chimney through the ridge", default=True)
    total_area: FloatProperty(
        name="Total Area (m²)",
        description="Gross floor area of all floors together, measured on wall centrelines",
        default=100.0, min=30.0, soft_max=600.0, max=2000.0, step=500,
    )
    floors: IntProperty(name="Floors", default=1, min=1, max=3)
    bedrooms: IntProperty(name="Bedrooms", default=3, min=0, max=8)
    bathrooms: IntProperty(name="Bathrooms", default=2, min=0, max=6)
    open_plan: BoolProperty(
        name="Open Space",
        description="One open living / kitchen / dining area (off = separate kitchen)",
        default=True,
    )
    seed: IntProperty(name="Seed", description="Change to get a different layout", default=1, min=0)

    ceiling_height: FloatProperty(name="Ceiling Height (m)", default=2.7, min=2.0, max=6.0, step=10)
    slab: FloatProperty(name="Slab Thickness (m)", default=0.2, min=0.05, max=0.6, step=1)
    ext_wall: FloatProperty(name="Outer Walls (m)", default=0.25, min=0.05, max=0.6, step=1)
    int_wall: FloatProperty(name="Inner Walls (m)", default=0.10, min=0.04, max=0.3, step=1)
    ground_lift: FloatProperty(name="Floor Above Ground (m)", default=HOUSE_LIFT, min=0.0, max=3.0, step=5,
                               description="Height of the ground floor above the 3D cursor (the ground). "
                                           "Set when the type changes: 0.75 m for a cottage on piles, 0.15 m "
                                           "for shops (a step up from their sidewalk), 0.2 m otherwise")
    sidewalk: BoolProperty(name="Sidewalk", default=True,
                           description="House: a paved strip round the walls, level with the floor (no step at "
                                       "the door). Cottage: one gravel bed under and round it. Shops: paving "
                                       "behind and beside, level with their street sidewalk. Not for villas: "
                                       "they have their own driveway and paving")
    sidewalk_width: FloatProperty(name="Width (m)", default=0.7, min=0.2, max=3.0, step=5,
                                  description="How far the sidewalk (or gravel) reaches out from the outer walls")

    roof_type: EnumProperty(
        name="Roof",
        items=[
            ("NONE", "None", "No roof or top ceiling — open from above"),
            ("FLAT", "Flat", "Flat roof slab"),
            ("PARAPET", "Flat + Parapet", "Flat roof with a low wall around the edge"),
            ("GABLE", "Gable", "Two slopes meeting at a ridge, triangular gable walls at the ends"),
            ("HIP", "Hip", "Four slopes (a pyramid on a square house)"),
            ("SHED", "Shed", "Single slope (mono-pitch)"),
        ],
        default="GABLE",
    )
    roof_pitch: FloatProperty(name="Pitch (°)", default=30.0, min=3.0, max=60.0, step=100)
    roof_overhang: FloatProperty(name="Overhang (m)", default=0.4, min=0.0, max=2.0, step=5)
    roof_thickness: FloatProperty(name="Roof Thickness (m)", default=0.2, min=0.03, max=0.6, step=1)
    parapet_height: FloatProperty(name="Parapet Height (m)", default=0.9, min=0.1, max=2.0, step=5)
    ridge_dir: EnumProperty(
        name="Ridge",
        description="Which way the ridge (or, for a shed roof, the high wall) runs",
        items=[("LONG", "Along Long Side", ""), ("SHORT", "Along Short Side", "")],
        default="LONG",
    )
    add_inserts: BoolProperty(name="Door Leaves & Glass", default=True)
    add_labels: BoolProperty(name="Room Labels", description="Room name and area written on each floor", default=True)
    add_lights: BoolProperty(name="Ceiling Lights", description="One point light per room", default=True)
    light_power: FloatProperty(name="Watts per m²", default=25.0, min=0.0, soft_max=200.0)

    material_style: EnumProperty(
        name="Materials",
        items=[
            ("NEIGHBORHOOD", "Neighborhood", "The materials of the neighborhood scene: painted facades, "
             "plaster inside, wood floors, tiled bathrooms, clay/slate roofs"),
            ("TEXTURE_SETS", "Texture Sets", "Pick a bundled texture set for walls, floor and ceiling"),
            ("PLAIN", "Plain Colours", "Flat untextured colours"),
        ],
        default="NEIGHBORHOOD",
    )
    facade: EnumProperty(name="Facade", items=nm.FACADE_ITEMS, default="RANDOM")
    roof_color: EnumProperty(name="Roof Tiles", items=nm.ROOF_ITEMS, default="RANDOM")
    bath_tiles: BoolProperty(name="Tiled Bathrooms", description="Tile the floor and walls of bathrooms and WCs "
                             "(and the floor of a separate kitchen)", default=True)
    wall_material: EnumProperty(name="Walls", items=MATERIAL_ENUM_ITEMS, default=_default_set("walls"))
    floor_material: EnumProperty(name="Floor", items=MATERIAL_ENUM_ITEMS, default=_default_set("concrete-wooden"))
    ceiling_material: EnumProperty(name="Ceiling", items=MATERIAL_ENUM_ITEMS, default=_default_set("concrete1"))
    tex_size: FloatProperty(name="Texture Size (m)", default=2.0, min=0.05, soft_max=20.0, step=10)


# --------------------------------------------------------------------------
# Mesh helpers
# --------------------------------------------------------------------------

def _floor_mesh(name, box, offset, floor_mat, ceil_mat):
    """Room floor slab: the floor on top, the ceiling of the room below underneath."""
    me = _boxes_mesh(name, [box], offset)
    return _paint_by_normal(me, floor_mat, ceil_mat, ceil_mat)


WET_WALLS = ("bathroom", "wc")
WET_FLOORS = ("bathroom", "wc", "kitchen")


def _paint_walls(me, offset, plan, floor, mats):
    """Facade on the outside of the shell, plaster inside, tiles in wet rooms.

    A wall face is outside when it looks at open air: past the footprint, or
    into a carport / terrace / balcony. `floor.accents` are facade zones that
    take another material (a villa's stone or timber bay).
    """
    i_in = _mat_index(me, mats["wall_in"])
    i_out = _mat_index(me, mats["wall_out"])
    i_wet = _mat_index(me, mats["wall_wet"])
    indoor = [r for r in floor.rooms if r.kind not in hl.OUTDOOR]
    wet = [r for r in floor.rooms if r.kind in WET_WALLS] if i_wet != i_in else []
    zones = [(x0, y0, x1, y1, _mat_index(me, mats[role])) for x0, y0, x1, y1, role in floor.accents if role in mats]
    for p in me.polygons:
        c, n = p.center - offset, p.normal
        if abs(n.z) > 0.5:
            p.material_index = i_in
            continue
        px, py = c.x + n.x * 0.05, c.y + n.y * 0.05     # step off the face into what it looks at
        if not any(r.x0 <= px <= r.x1 and r.y0 <= py <= r.y1 for r in indoor):
            p.material_index = next((i for x0, y0, x1, y1, i in zones if x0 <= c.x <= x1 and y0 <= c.y <= y1), i_out)
        elif any(r.x0 + 0.02 <= px <= r.x1 - 0.02 and r.y0 + 0.02 <= py <= r.y1 - 0.02 for r in wet):
            # (strictly inside: the jamb of a door or window in a bathroom wall faces along the
            # wall line, which is the room's edge, and must stay plaster)
            p.material_index = i_wet
        else:
            p.material_index = i_in
    return me


def _pick_materials(s):
    """{role: material} for the chosen material style."""
    from ..core.materials import _material, _material_for

    villa = s.building_type.startswith("VILLA")
    if s.material_style == "NEIGHBORHOOD":
        if s.building_type == "COTTAGE":
            if s.cottage_style == "PAINTED":
                m = nm.painted_cottage_palette(s.cottage_roof, s.cottage_paint, s.cottage_siding, s.seed, s.bath_tiles)
            else:
                m = nm.cottage_palette(s.cottage_roof, s.seed, s.bath_tiles)
        elif villa:
            m = nm.villa_palette(s.building_type[6:], s.facade, s.roof_color, s.seed, s.bath_tiles)
        elif s.building_type == "SHOPS":
            m = nm.house_palette(sm.facade_key(s.facade, s.seed), "RED", s.seed, s.bath_tiles)
        else:
            m = nm.house_palette(s.facade, s.roof_color, s.seed, s.bath_tiles)
    else:
        if s.material_style == "TEXTURE_SETS":
            k = s.tex_size
            wall = _material_for(s.wall_material, k, (0.85, 0.83, 0.80), "HouseWall")
            floor = _material_for(s.floor_material, k, (0.45, 0.32, 0.22), "HouseFloor")
            ceil = _material_for(s.ceiling_material, k, (0.85, 0.83, 0.80), "HouseCeiling")
        else:
            wall = _material("RoomGen_Wall", (0.85, 0.83, 0.80))
            floor = _material("RoomGen_Floor", (0.45, 0.32, 0.22))
            ceil = _material("RoomGen_Ceiling", (0.85, 0.83, 0.80))
        roof = _material("RoomGen_Roof", (0.32, 0.16, 0.12))
        m = {
            "wall_in": wall, "wall_out": wall, "wall_wet": wall,
            "floor": floor, "floor_wet": floor, "ceiling": ceil,
            "roof": roof, "roof_flat": ceil, "soffit": roof,
            "door": _material("RoomGen_HouseDoor", (0.55, 0.38, 0.24)),
            "glass": _material("RoomGen_Glass", (0.8, 0.9, 1.0), glass=True),
            "stair": _material("RoomGen_Stair", (0.62, 0.48, 0.34)),
            "rail": _material("RoomGen_Rail", (0.15, 0.15, 0.15)),
        }
        if villa:
            stone = s.building_type == "VILLA_MODERN"
            wood = _material("RoomGen_VillaTimber", (0.5, 0.33, 0.2))
            m.update({
                "accent": _material("RoomGen_VillaStone", (0.6, 0.55, 0.48)) if stone else wood,
                "recess": _material("RoomGen_VillaRecess", (0.6, 0.6, 0.62)),
                "trim": _material("RoomGen_VillaTrim", (0.05, 0.05, 0.06)),
                "soffit_wood": wood,
                "paving": _material("RoomGen_VillaPaving", (0.62, 0.6, 0.57)),
                "drive": _material("RoomGen_VillaDrive", (0.72, 0.68, 0.6)),
                "water": _material("RoomGen_VillaWater", (0.1, 0.35, 0.55)),
            })
        if s.building_type == "COTTAGE":
            m.update({
                "trim": _material("RoomGen_CottageTrim", (0.8, 0.78, 0.72)),
                "timber": _material("RoomGen_CottageTimber", (0.4, 0.34, 0.27)),
                "post": _material("RoomGen_CottageTimber", (0.4, 0.34, 0.27)),
                "pile": _material("RoomGen_CottagePile", (0.09, 0.07, 0.06)),
                "chimney": _material("RoomGen_CottageBrick", (0.45, 0.2, 0.13)),
                "chimney_cap": _material("RoomGen_CottageCap", (0.45, 0.43, 0.4)),
            })
            if s.cottage_style == "PAINTED":
                paint = _material("RoomGen_CottagePaint", (0.55, 0.62, 0.5))
                m.update({"wall_out": paint, "wall_gable": paint, "corner": m["trim"], "veranda_post": m["trim"],
                          "baluster": m["trim"], "veranda_rail": m["trim"], "bargeboard": m["trim"]})
    if s.building_type == "SHOPS":
        sm.shop_roles(m, s.material_style == "NEIGHBORHOOD")
    m["label"] = _material("RoomGen_Label", (0.05, 0.05, 0.05))
    return m


def _label(name, text, coll, parent, location, size):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = text
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    ob = bpy.data.objects.new(name, cu)
    coll.objects.link(ob)
    ob.parent = parent
    ob.location = location
    return ob


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def _build(context, s, report, name=None, site=False):
    """Build the building `s` describes at the cursor, as collection + root empty `name`
    (default: s.house_name, which the Surroundings and World builders set). A building of
    this add-on already called `name` is replaced.

    `site` (the panel's buttons): the root sits on the ground, the building is lifted by
    s.ground_lift and gets the sidewalk. Without it (Surroundings, World, which set the
    building on their own ground) the ground-floor top stays at the root, as before."""
    from ..core.scene_utils import _delete_collection

    villa = s.building_type.startswith("VILLA")
    cottage = s.building_type == "COTTAGE"
    shops = s.building_type == "SHOPS"
    if shops:
        plan = shop_ui.make_plan(s)
    elif cottage:
        plan = cl.make_cottage_plan(
            area=s.total_area, bedrooms=s.bedrooms, bathrooms=s.bathrooms, seed=s.seed,
            ceiling_h=s.ceiling_height, slab=s.slab, t_ext=s.ext_wall, t_int=s.int_wall,
            roof="GABLE" if s.cottage_style == "PAINTED" else "GAMBREL",
        )
    elif villa:
        plan = vl.make_villa_plan(
            style=s.building_type[6:], area=s.total_area, bedrooms=s.bedrooms, bathrooms=s.bathrooms,
            seed=s.seed, ceiling_h=s.ceiling_height, slab=s.slab, t_ext=s.ext_wall, t_int=s.int_wall,
            pitch=s.villa_pitch,
        )
    else:
        plan = hl.make_plan(
            area=s.total_area, floors=s.floors, bedrooms=s.bedrooms, bathrooms=s.bathrooms,
            open_plan=s.open_plan, seed=s.seed, ceiling_h=s.ceiling_height, slab=s.slab,
            t_ext=s.ext_wall, t_int=s.int_wall,
        )

    name = (name or s.house_name).strip() or "House"
    old = bpy.data.collections.get(name)
    if old:
        if not old.get("roomgen"):
            report({"ERROR"}, f"A collection named '{name}' already exists and wasn't made by this addon — pick another name")
            return None
        _delete_collection(old)

    coll = bpy.data.collections.new(name)
    coll["roomgen"] = True
    context.scene.collection.children.link(coll)
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "PLAIN_AXES"
    root.location = context.scene.cursor.location.copy()
    coll.objects.link(root)
    root["house_seed"] = s.seed
    root["building_type"] = s.building_type
    if s.building_type == "COTTAGE":
        root["cottage_style"] = s.cottage_style

    mats = _pick_materials(s)
    root["facade"] = mats["wall_out"].name
    root["roof_material"] = mats["roof"].name

    # House centred on its origin
    center = Vector((-plan.W / 2, -plan.D / 2, 0.0))
    H = plan.ceiling_h
    te = plan.t_ext

    for f in plan.floors:
        fc = bpy.data.collections.new(f"{name}_{f.label}")
        fc["roomgen"] = True
        coll.children.link(fc)
        off = center + Vector((0, 0, f.base_z))
        p = f"{name}_{f.label}"

        # A roof that comes down into this storey (the gable villa's attic) trims everything in it
        planes = [(Vector(co) + off, Vector(no)) for co, no in plan.clip.get(f.index, ())]

        def trimmed(me, planes=planes):
            return _clip_mesh(me, planes) if planes else me

        walls = _paint_walls(trimmed(_boxes_mesh(f"{p}_Walls", f.walls, off)), off, plan, f, mats)
        _obj(f"{p}_Walls", walls, fc, root, uv_z=f.base_z)     # wall tiles start at this storey's floor

        for r in f.rooms:
            label = f"{p}_{r.name.replace(' / ', '_').replace(' ', '_')}"
            outdoor = r.kind in hl.OUTDOOR
            top = 0.0
            if outdoor:
                # Open-air slab, out to the facade line. A carport sits down at ground level.
                # It stops 4 mm short of the facade line and reaches 6 mm below the slab, so none of
                # its faces lies in the same plane as a wall face (which would flicker).
                top = -plan.slab + 0.05 if r.kind == "carport" else -0.02
                ex = te / 2 - 0.004
                box = (r.x0 - (ex if r.x0 < 1e-4 else 0), r.y0 - (ex if r.y0 < 1e-4 else 0),
                       -plan.slab - (0.1 if r.kind == "carport" else 0.006),
                       r.x1 + (ex if r.x1 > plan.W - 1e-4 else 0), r.y1 + (ex if r.y1 > plan.D - 1e-4 else 0), top)
                role = "paving" if r.kind == "carport" else "deck"
                me = _floor_mesh(f"{label}_Floor", box, off, mats.get(role, mats.get("paving", mats["floor"])), mats["ceiling"])
                _obj(f"{label}_Floor", me, fc, root)["room"] = r.name
            elif not (r.kind == "stair" and f.index > 0):     # stairwell is a hole upstairs
                box = (r.x0, r.y0, -plan.slab, r.x1, r.y1, 0.0)
                fm = mats["floor_wet"] if r.kind in WET_FLOORS else mats["floor"]
                ob = _obj(f"{label}_Floor", _floor_mesh(f"{label}_Floor", box, off, fm, mats["ceiling"]), fc, root)
                ob["room"] = r.name
                ob["area_m2"] = round(r.area, 2)
            cx, cy = r.center
            if getattr(r, "quiet", False):     # a piece of a room cut round a stairwell
                continue
            if s.add_labels:
                size = max(0.18, min(0.4, (min(r.x1 - r.x0, r.y1 - r.y0)) / 9))
                lb = _label(f"{label}_Label", f"{r.name}\n{r.area:.1f} m²", fc, root,
                            off + Vector((cx, cy, top + 0.01)), size)
                lb.data.materials.append(mats["label"])
            if s.add_lights and s.light_power > 0 and (not outdoor or r.kind == "carport"):
                ld = bpy.data.lights.new(f"{label}_Light", "POINT")
                ld.energy = max(20.0, s.light_power * r.area)
                ld.shadow_soft_size = 0.15
                lo = bpy.data.objects.new(f"{label}_Light", ld)
                fc.objects.link(lo)
                lo.parent = root
                lo.location = off + Vector((cx, cy, (f.light_h or H) - min(0.3, H * 0.12)))

        if f.stair:
            _obj(f"{p}_Stairs", _boxes_mesh(f"{p}_Stairs", f.stair, off), fc, root, [mats["stair"]])
        if f.rails:    # a glass fence round the stairwell, not a solid wall
            glass, posts = glass_fence(f.rails)
            _obj(f"{p}_StairGlass", _boxes_mesh(f"{p}_StairGlass", glass, off), fc, root, [mats["glass"]])
            _obj(f"{p}_Railing", _boxes_mesh(f"{p}_Railing", posts, off), fc, root, [mats.get("trim", mats["rail"])])
        if f.fence:    # the villa stair's glass fence
            for role, mat in (("glass", mats.get("stair_glass", mats["glass"])), ("post", mats.get("stair_post", mats["trim"]))):
                parts = [pts for rl, pts in f.fence if rl == role]
                verts = [v for pts in parts for v in pts]
                faces = [[i * 8 + k for k in face] for i in range(len(parts)) for face in FENCE_FACES]
                me = _solid(f"{p}_StairFence_{role}", [Vector(v) + off for v in verts], faces)
                _obj(f"{p}_StairFence_{role.title()}", me, fc, root, [mat])
        if f.srails:   # and along the stair flights
            glass, rail = sloped_fence(f"{p}_StairFence", f.srails, off)
            _obj(f"{p}_StairFenceGlass", glass, fc, root, [mats["glass"]])
            _obj(f"{p}_StairFenceRail", rail, fc, root, [mats.get("trim", mats["rail"])])

        if s.add_inserts:
            leaves, inner, panes = [], [], []
            for o in f.openings:
                if not o.leaf or o.kind == "ARCH":
                    continue
                if o.kind in ("DOOR", "ENTRANCE"):
                    b = hl.opening_box(o, min(0.045, o.thickness * 0.8))
                    # a palette may give inside doors their own material ("door_in")
                    (inner if o.kind == "DOOR" and "door_in" in mats else leaves).append(
                        (b[0], b[1], b[2], b[3], b[4], b[5] - 0.005))
                else:
                    panes.append(hl.opening_box(o, 0.006))
            if leaves:
                _obj(f"{p}_Doors", _boxes_mesh(f"{p}_Doors", leaves, off), fc, root, [mats["door"]])
            if inner:
                _obj(f"{p}_InnerDoors", _boxes_mesh(f"{p}_InnerDoors", inner, off), fc, root, [mats["door_in"]])
            if panes:
                _obj(f"{p}_Glass", trimmed(_boxes_mesh(f"{p}_Glass", panes, off)), fc, root, [mats["glass"]])

    if villa:
        from . import villa as villa_exterior   # it needs this module's helpers
        villa_exterior.build_exterior(s, plan, mats, coll, root, name, center)
    elif cottage:
        from . import cottage as cottage_exterior
        cottage_exterior.build_exterior(s, plan, mats, coll, root, name, center)
        if s.material_style == "NEIGHBORHOOD":         # siding and roof paint (cottage_paint)
            cottage_paint.apply(root, s)
    elif shops:
        from . import shop as shop_exterior
        shop_exterior.build_exterior(s, plan, mats, coll, root, name, center)
    elif s.roof_type != "NONE":
        top = plan.floors[-1].base_z + H
        # Top ceiling slab (the whole roof when flat; the attic floor otherwise)
        box = (-te / 2, -te / 2, top, plan.W + te / 2, plan.D + te / 2, top + plan.slab)
        flat = s.roof_type in ("FLAT", "PARAPET")
        slab_name = f"{name}_Roof" if flat else f"{name}_TopCeiling"
        slab = _paint_by_normal(_boxes_mesh(slab_name, [box], center),
                                mats["roof_flat"] if flat else mats["ceiling"], mats["ceiling"], mats["wall_out"])
        _obj(slab_name, slab, coll, root)
        _build_roof(s, plan, top + plan.slab, coll, root, mats, name)

    if site:
        _onto_ground(s, plan, coll, root, name, center, villa)

    from . import lod_ui
    lod_ui.after_build(context, root)
    return plan


def _onto_ground(s, plan, coll, root, name, center, villa):
    """Lift everything built so far by s.ground_lift (the root stays on the ground), then
    lay what goes round it on the ground:
    - house: a sidewalk ring with its top level with the ground floor, so the door has no step;
    - cottage: one gravel bed under the whole house and veranda, reaching past the steps;
    - shops: their street sidewalk and kerb are in front already (shop_extras), so a ring
      behind and beside, level with that sidewalk."""
    t, lift = s.building_type, s.ground_lift
    root["ground_lift"] = lift
    if lift:
        parts = set(root.children) | {o for o in coll.all_objects if o.parent is None and o != root}
        for ob in parts:
            ob.location.z += lift
    if not s.sidewalk or villa:
        return
    from ..core.materials import _material
    neighborhood = s.material_style == "NEIGHBORHOOD"
    w, te = s.sidewalk_width, plan.t_ext
    x0, y0, x1, y1 = -te / 2, -te / 2, plan.W + te / 2, plan.D + te / 2      # outer wall faces
    z0 = -0.1
    if t == "COTTAGE":
        from . import cottage as ct
        rise = ct.DECK_TOP + plan.slab + ct.SILL_H + ct.PILE_H          # veranda deck to the ground
        steps_run = (max(2, round(rise / 0.18)) - 1) * 0.28
        front = y0 - plan.cottage["veranda"] - max(w, steps_run + 0.3)
        mat = nm.ensure("C_world_gravel") if neighborhood else _material("RoomGen_Gravel", (0.36, 0.29, 0.21))
        label = f"{name}_Gravel"
        _obj(label, _boxes_mesh(label, [(x0 - w, front, z0, x1 + w, y1 + w, GRAVEL_TOP)], center),
             coll, root, [mat])
        return
    if t == "SHOPS":
        from .shop_extras import WALK_Z
        top = lift + WALK_Z                       # level with the shops' own street sidewalk
    else:
        top = lift                                # level with the ground floor
    boxes = [(x0 - w, y1, z0, x1 + w, y1 + w, top),           # back
             (x0 - w, y0, z0, x0, y1, top),                   # left
             (x1, y0, z0, x1 + w, y1, top)]                   # right
    if t != "SHOPS":
        boxes.append((x0 - w, y0 - w, z0, x1 + w, y0, top))  # front
    mat = nm.ensure("C_sidewalk") if neighborhood else _material("RoomGen_Sidewalk", (0.62, 0.6, 0.57))
    label = f"{name}_{'SidewalkRing' if t == 'SHOPS' else 'Sidewalk'}"   # shops have a "_Sidewalk" already
    _obj(label, _boxes_mesh(label, boxes, center), coll, root, [mat])


classes = (
    shop_ui.SHOPGEN_Settings,      # before HOUSEGEN_Settings, which points at it
    HOUSEGEN_Settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.house_gen = bpy.props.PointerProperty(type=HOUSEGEN_Settings)


def unregister():
    del bpy.types.Scene.house_gen
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
