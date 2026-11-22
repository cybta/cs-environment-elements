"""CS Environment Elements: one add-on for the carpentry-simulator world.

Sections (one sidebar tab, "CS Env", switched at the top of it):
    nature     trees, bushes, rocks                     (was the TreeGen add-on)
    buildings  houses, villas, cottages, shops, fences, LODs  (was House Generator)
    props      outdoor props: playground, benches, lamps, poles
    interior   furniture, old and new
core holds what they share: materials, bundled textures, the tab and section switch.
"""

bl_info = {
    "name": "CS Environment Elements",
    "author": "Cybta",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar (N) > CS Env",
    "description": "Trees, rocks, houses, villas, cottages, shops, fences, quays, props "
                   "and furniture, with game LODs",
    "category": "Add Mesh",
}

import bpy

from . import core, nature, buildings, props, interior

# Registered in this order (core first: its panel heads the tab), unregistered in reverse.
SECTIONS = (core, nature, buildings, props, interior)

# The add-ons this one replaces. They register the same settings and operators,
# so running both would make them fight over them.
_REPLACED = {"room_generator": "House Generator", "treegen": "TreeGen"}


def register():
    clash = [label for key, label in _REPLACED.items() if key in bpy.context.preferences.addons]
    if clash:
        raise RuntimeError("CS Environment Elements replaces " + " and ".join(clash)
                           + ": disable those add-ons first, then enable this one.")
    for section in SECTIONS:
        section.register()


def unregister():
    for section in reversed(SECTIONS):
        section.unregister()
