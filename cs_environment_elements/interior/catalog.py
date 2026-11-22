"""Furniture pieces, by kind and style.

Old = the worn set from the user's "old furniture" folder (assets/old).
New = the modern set from carpentry simulator/ref/3D Models/furniture (assets/new).
Add a piece: drop its .blend (and textures, in that style's textures/) into the folder
and add an Item below. `objects` names the file's top-level objects to use when the
file holds more than the piece. `name` is what copies are called: <name>-1, <name>-2...
(thing-style-variant).
"""

from ..core.library import KEEP, Item

KINDS = [
    ("SOFA", "Sofa", "OUTLINER_OB_POINTCLOUD", {
        "OLD": [Item("old_armchair", "Wingback Armchair", "old/sofa_1_seater.blend", name="armchair-old-wingback"),
                Item("old_sofa_2", "Sofa, 2 Seater", "old/sofa_2_seater.blend", name="sofa-old-2seat"),
                Item("old_sofa_3", "Sofa, 3 Seater", "old/sofa_3_seater.blend", name="sofa-old-3seat")],
        "NEW": [Item("new_couch", "Couch", "new/couch.blend", name="sofa-new-couch")],
    }),
    ("CHAIR", "Chair", "OUTLINER_OB_ARMATURE", {
        "OLD": [Item("old_bentwood_chair", "Bentwood Chair", "old/old_bentwood_chair.blend",
                     name="chair-old-bentwood"),
                Item("old_bar_stool", "Bentwood Bar Stool", "old/old_bentwood_bar_stool.blend",
                     name="stool-old-bentwood")],
        "NEW": [Item("new_chair", "Chair", "new/chair.blend", name="chair-new")],
    }),
    ("TABLE", "Table", "MESH_PLANE", {
        "OLD": [Item("old_bentwood_table", "Bentwood Table", "old/old_bentwood_table.blend",
                     name="table-old-bentwood")],
        "NEW": [Item("new_table", "Dining Table", "new/table.blend", name="table-new-dining"),
                Item("new_coffee_table", "Coffee Table", "new/coffee-table.blend", name="table-new-coffee")],
    }),
    ("BED", "Bed", "MESH_CUBE", {
        "OLD": [],
        "NEW": [Item("new_bed", "Bed (with pillows and throw)", "new/bed.blend", name="bed-new"),
                Item("new_mattress_single", "Mattress, Single 90x200", "new/mattress-single.blend",
                     name="mattress-new-single"),
                Item("new_mattress_double", "Mattress, Double 140x200", "new/mattress-double.blend",
                     name="mattress-new-double"),
                Item("new_mattress_queen", "Mattress, Queen 160x200", "new/mattress-queen.blend",
                     name="mattress-new-queen"),
                Item("new_mattress_king", "Mattress, King 180x200", "new/mattress-king.blend",
                     name="mattress-new-king"),
                Item("new_pillow", "Pillow", "new/pillow.blend", name="pillow-new")],
    }),
    ("KITCHEN", "Kitchen", "OUTLINER_OB_GREASEPENCIL", {
        "OLD": [Item("old_fridge", "Fridge (50s)", "old/fridge_50s.blend", name="fridge-old-50s"),
                Item("old_gas_stove", "Gas Stove (80s)", "old/gas_stove_80s.blend", name="stove-old-gas-80s")],
        "NEW": [Item("new_kitchen_sink", "Kitchen Sink + Tap", "new/kitchen-sink.blend", mount=KEEP,
                     note="Cursor = worktop surface (the basin sits into it)", name="sink-new-kitchen")],
    }),
    ("BATHROOM", "Bathroom", "MOD_FLUIDSIM", {
        "OLD": [],
        "NEW": [Item("new_toilet", "Toilet", "new/toilet.blend", name="toilet-new"),
                Item("new_sink", "Wash Basin + Tap", "new/sink.blend", mount=KEEP,
                     note="Cursor = basin rim on the wall", name="sink-new-basin"),
                Item("new_shower", "Shower Head", "new/douche.blend", mount=KEEP,
                     note="Cursor = wall fixing point", name="shower-new-head")],
    }),
    ("HEATING", "Heating", "LIGHT_SUN", {
        "OLD": [],
        "NEW": [Item("new_radiator", "Radiator", "new/radiator.blend", mount=KEEP,
                     note="Cursor = the model's wall fixing point", name="radiator-new")],
    }),
    ("LIGHTING", "Lighting", "LIGHT_POINT", {
        "OLD": [Item("old_pendant_lamp", "Pendant Lamp (80s)", "old/pendant_lamp_80s.blend", mount=KEEP,
                     note="Cursor = ceiling (the lamp hangs below it)", name="lamp-old-pendant-80s")],
        "NEW": [],
    }),
    ("WORKSHOP", "Workshop", "TOOL_SETTINGS", {
        "ANY": [Item("workbench", "Workbench", "new/workbench.blend", name="workbench"),
                Item("desk_workshop", "Workshop Desk", "new/desk-workshop.blend", name="desk-workshop")],
    }),
]
