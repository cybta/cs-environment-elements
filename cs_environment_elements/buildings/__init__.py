"""Buildings section (formerly the House Generator add-on): houses, villas, old cottages,
shopping rows, fences and quays, the Surroundings generator, and generic LOD1-3 for all of them."""

from . import cottage_fix, cottage_paint, fence, house, house_ui, lod_ui, neighborhood, paint_edit, quay


def register():
    fence.register()           # before house: its settings hang off house_gen
    quay.register()            # (same)
    house.register()
    cottage_paint.register()
    house_ui.register()
    lod_ui.register()          # after house_ui: its panel sits under the generator panel
    neighborhood.register()
    paint_edit.register()      # "Selected Paint": edit one cottage's / fence's paint after it is built
    cottage_fix.register()     # repairs for cottages built before a generator fix (its button: Selected Paint)


def unregister():
    cottage_fix.unregister()
    paint_edit.unregister()
    neighborhood.unregister()
    lod_ui.unregister()
    house_ui.unregister()
    cottage_paint.unregister()
    house.unregister()
    quay.unregister()
    fence.unregister()
