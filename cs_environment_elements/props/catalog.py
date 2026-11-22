"""Outdoor props, by kind and style. Old = the user's old playground set (assets/playground).
Copies are named <name>-1, <name>-2... (thing-style-variant).
"""

from ..core.library import KEEP, Item

_PG = "playground/playground_"
_POLE = "poles/electric_pole_old.blend"          # tools/props/build_electric_pole.py
_RUBBLE = "rubble/gravel_rubble.blend"
_BIN = "bins/wheelie_bin.blend"
_GARDEN = "garden/garden_set.blend"
_YARD = "garden/yard_furniture.blend"
_LAUNDRY = "garden/clothesline.blend"
_WOODSHED = "garden/woodshed.blend"


_LAMP = Item("pole_old_lamp_kit", "Street Lamp", _POLE, ["ElectricPoleOldLampKit"], mount=KEEP,
             name="lamp-old-street")       # 2 hook insulators + lamp, fits every old pole


def _pole(key, label, obj):
    return Item(key, label, _POLE, [obj], mount=KEEP, name="pole-old-electric-" + key.split("_", 2)[2],
                extra=_LAMP)

KINDS = [
    ("PLAYGROUND", "Playground", "OUTLINER_OB_FORCE_FIELD", {
        "OLD": [Item("old_swing", "Swing Set", _PG + "swing_set.blend", name="playground-old-swing"),
                Item("old_slide", "Slide", _PG + "slide.blend", name="playground-old-slide"),
                Item("old_seesaw", "Seesaw", _PG + "seesaw.blend", name="playground-old-seesaw"),
                Item("old_merry", "Merry-Go-Round", _PG + "merry_go_round.blend",
                     name="playground-old-merry-go-round"),
                Item("old_bench", "Bench", _PG + "bench_bin.blend", ["PlaygroundBench"],
                     name="bench-old-playground"),
                Item("old_bin", "Bin", _PG + "bench_bin.blend", ["PlaygroundBin"], name="bin-old-playground"),
                Item("old_sandbox", "Sandbox", _PG + "sandbox.blend", name="playground-old-sandbox",
                     note="2.4 m of sand edged with 20 cm logs")],     # tools/props/build_sandbox.py
        "NEW": [],
    }),
    ("POLES", "Electric Poles", "LIGHT", {
        "OLD": [_pole("pole_old_3arm", "3 Crossarms", "ElectricPoleOld3Arm"),
                _pole("pole_old_2arm_double", "2 Double Crossarms", "ElectricPoleOld2ArmDouble"),
                _pole("pole_old_2arm", "2 Crossarms", "ElectricPoleOld2Arm"),
                _pole("pole_old_1arm", "1 Crossarm", "ElectricPoleOld1Arm")],
        "NEW": [],
    }),
    ("GARDEN", "Garden & Yard", "MOD_FLUIDSIM", {                 # tools/props/build_garden_set.py
        "ANY": [Item("garden_shovel", "Shovel", _GARDEN, ["GardenShovel"], name="shovel-old",
                     note="Standing upright on its point, 1.1 m"),
                Item("garden_fork", "Digging Fork", _GARDEN, ["GardenFork"], name="fork-old",
                     note="Standing upright on its tines, 1.1 m"),
                Item("garden_hose", "Hose", _GARDEN, ["GardenHose"], name="hose-old"),
                Item("wheelbarrow", "Wheelbarrow", _GARDEN, ["Wheelbarrow"], name="wheelbarrow-old",
                     note="Wheel to the front (-Y)"),
                Item("watering_can", "Watering Can", _GARDEN, ["WateringCan"], name="watering-can-old",
                     note="Spout to the front (-Y)"),
                Item("wooden_crate", "Wooden Crate", _GARDEN, ["WoodenCrate"], name="crate-old"),
                Item("concrete_block", "Concrete Block", _GARDEN, ["ConcreteBlock"], name="block-concrete")],
    }),
    ("YARD", "Yard Furniture", "OUTLINER_OB_GREASEPENCIL", {      # tools/props/build_yard_furniture.py
        "OLD": [Item("yard_table_old", "Slat Table on Blocks", _YARD, ["YardTableOld"], name="table-old-yard",
                     note="Pallet slats on a rusty square-tube frame, 1 x 0.6 m"),
                Item("yard_bench_old", "Plank Bench", _YARD, ["YardBenchOld"], name="bench-old-yard",
                     note="1.5 m, front to -Y"),
                Item("yard_stool_old", "Round Stool", _YARD, ["YardStoolOld"], name="stool-old-yard"),
                Item("clothesline_laundry", "Clothesline with Laundry", _LAUNDRY, ["ClotheslineLaundry"],
                     name="clothesline-old-laundry", note="Posts 4.6 m apart, ropes along X"),
                Item("clothesline_empty", "Clothesline (Empty)", _LAUNDRY, ["ClotheslineEmpty"],
                     name="clothesline-old"),
                Item("laundry_basket", "Laundry Basket", _LAUNDRY, ["LaundryBasket"], name="basket-laundry-old"),
                Item("wash_tub", "Wash Tub", _LAUNDRY, ["WashTub"], name="tub-wash-old"),   # build_clothesline.py
                Item("woodshed_old", "Firewood Shed", _WOODSHED, ["WoodshedOld"], name="woodshed-old",
                     note="3 x 1 m, open front to -Y, full of split logs")],
        "NEW": [Item("woodshed_new", "Firewood Shed", _WOODSHED, ["WoodshedNew"], name="woodshed-new",
                     note="3 x 1 m fresh pine, open front to -Y, full of split logs")],   # build_woodshed.py
    }),
    ("BINS", "Bins", "TRASH", {                                   # tools/props/build_wheelie_bin.py
        "ANY": [Item("wheelie_bin_green", "Wheelie Bin, Green", _BIN, ["WheelieBinGreen"], mount=KEEP,
                     name="bin-wheelie-green", note="240 L; the lid opens about its local X"),
                Item("wheelie_bin_black", "Wheelie Bin, Black", _BIN, ["WheelieBinBlack"], mount=KEEP,
                     name="bin-wheelie-black", note="240 L; the lid opens about its local X")],
    }),
    ("RUBBLE", "Gravel & Rubble", "OUTLINER_OB_POINTCLOUD", {      # tools/props/build_gravel_rubble.py
        "ANY": [Item("gravel_pile_large", "Gravel Pile, Large", _RUBBLE, ["GravelPileLarge"], mount=KEEP,
                     name="gravel-pile-large", note="About 2.9 x 1.9 m, 0.5 m high"),
                Item("gravel_pile_small", "Gravel Pile, Small", _RUBBLE, ["GravelPileSmall"], mount=KEEP,
                     name="gravel-pile-small", note="About 1.5 x 1 m, 0.25 m high"),
                Item("gravel_spill", "Gravel Spill", _RUBBLE, ["GravelSpill"], mount=KEEP,
                     name="gravel-spill", note="A low spread of gravel, about 2.2 x 1.5 m")],
    }),
]
