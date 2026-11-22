"""World section: the whole game map (terrain, river, lake, roads, districts, parks,
nature), built from the buildings, nature and props sections."""

from . import world


def register():
    world.register()


def unregister():
    world.unregister()
