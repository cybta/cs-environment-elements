"""Settings and panel section for the Shopping Row building type (house.py's Type dropdown)."""

from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import PropertyGroup

from . import shop_layout as sl

# Construction values a shopping row switches to (and back from): tall storeys, solid walls
CONSTRUCTION = dict(ceiling_height=3.2, slab=0.25, ext_wall=0.3, int_wall=0.15)


class SHOPGEN_Settings(PropertyGroup):
    count: IntProperty(name="Shops", description="How many shops stand side by side", default=4, min=1, max=12)
    width: FloatProperty(name="Shop Width (m)", description="Street frontage of one shop", default=5.0,
                         min=3.5, max=12.0, step=10)
    vary: BoolProperty(name="Vary Widths", description="Each shop a little wider or narrower (from the seed)",
                       default=True)
    depth: FloatProperty(name="Depth (m)", description="From the street to the back wall", default=10.0,
                         min=6.0, max=20.0, step=10)
    entrance: EnumProperty(
        name="Entrance",
        description="Where the shared entrance and stair up to the upper floor go",
        items=[("LEFT", "Left End", "Entrance bay at the left end of the row"),
               ("MIDDLE", "Middle", "Entrance bay between the middle shops"),
               ("RIGHT", "Right End", "Entrance bay at the right end of the row")],
        default="MIDDLE",
    )
    side_windows: BoolProperty(name="Side Windows", description="The shops at the two ends wrap their display "
                               "windows round the corner, with tall windows upstairs (a panoramic view); "
                               "turn off when the row stands against other buildings", default=True)
    stockrooms: BoolProperty(name="Stockrooms", description="A stockroom behind each shop, with the back door",
                             default=True)
    awnings: BoolProperty(name="Awnings", description="A canvas awning over each shopfront, plain or striped",
                          default=True)
    signs: BoolProperty(name="Signs", description="Each shop's name in gilt letters on its fascia", default=True)
    flower_boxes: BoolProperty(name="Flower Boxes", description="Planted boxes under some upper windows",
                               default=True)
    planters: BoolProperty(name="Planters", description="Pots by the doors on the sidewalk", default=True)
    sidewalk: BoolProperty(name="Sidewalk", description="A paved sidewalk with a kerb along the front",
                           default=True)
    fittings: BoolProperty(name="Shop Fittings", description="A shelving unit and a counter in each shop",
                           default=True)


def apply_construction(s, entering):
    """Switching Type to or from a shopping row swaps the construction defaults."""
    if entering:
        for k, v in CONSTRUCTION.items():
            setattr(s, k, v)
    elif all(abs(getattr(s, k) - v) < 1e-4 for k, v in CONSTRUCTION.items()):
        s.ceiling_height, s.slab, s.ext_wall, s.int_wall = 2.7, 0.2, 0.25, 0.1


def make_plan(s):
    g = s.shop
    return sl.make_shop_plan(count=g.count, width=g.width, depth=g.depth, vary=g.vary, entrance=g.entrance,
                             stockrooms=g.stockrooms, side_windows=g.side_windows, seed=s.seed, ceiling_h=s.ceiling_height, slab=s.slab,
                             t_ext=s.ext_wall, t_int=s.int_wall)


def draw(layout, s):
    g = s.shop
    col = layout.column(align=True)
    col.prop(g, "count")
    col.prop(g, "width")
    col.prop(g, "depth")
    layout.prop(g, "vary")
    layout.prop(g, "entrance")
    frontage = g.count * g.width + sl.ENT_W
    layout.label(text=f"≈ {frontage:.0f} m of street front, 2 floors", icon="INFO")
    if s.ceiling_height < sl.MIN_H:
        layout.label(text=f"Shops want {sl.MIN_H:.1f} m ceilings or more", icon="ERROR")


def draw_details(layout, s):
    g = s.shop
    layout.label(text="Shopping Row")
    grid = layout.grid_flow(columns=2, align=True)
    for p in ("side_windows", "stockrooms", "awnings", "signs", "flower_boxes", "planters", "sidewalk", "fittings"):
        grid.prop(g, p, toggle=True)
