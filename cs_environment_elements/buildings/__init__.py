"""Buildings section (formerly the House Generator add-on): houses, villas, old cottages,
shopping rows and fences, the Surroundings generator, and generic LOD1-3 for all of them."""

from . import cottage_paint, fence, house, house_ui, lod_ui, neighborhood


def register():
    fence.register()           # before house: its settings hang off house_gen
    house.register()
    cottage_paint.register()
    house_ui.register()
    lod_ui.register()          # after house_ui: its panel sits under the generator panel
    neighborhood.register()


def unregister():
    neighborhood.unregister()
    lod_ui.unregister()
    house_ui.unregister()
    cottage_paint.unregister()
    house.unregister()
    fence.unregister()
