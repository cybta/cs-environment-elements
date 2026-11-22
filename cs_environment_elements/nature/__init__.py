"""Nature section (formerly the TreeGen add-on): procedural trees and rocks.

Python grows a branch skeleton per species; one shared Geometry Nodes group
turns it into bark tubes and instanced foliage cards at one of three game
LODs, keeping LOD 0 inside a triangle budget. Export writes LOD 0-2 as FBX, plus a
LOD 3 impostor (two crossed planes with a texture rendered from the tree).
The Rock Generator panel makes boulders, jagged shards and layered slabs with LOD 0-2.
"""

from . import rock_ui, ui


def register():
    ui.register()
    rock_ui.register()


def unregister():
    rock_ui.unregister()
    ui.unregister()
