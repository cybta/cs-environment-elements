"""Shared by every section: materials and bundled textures (materials, neighborhood_materials,
assets/), scene helpers (scene_utils), the bundled-model library (library) with its
panel builder (asset_ui), and the sidebar tab with its section switch (ui)."""

from . import asset_ui, ui


def register():
    ui.register()
    asset_ui.register()


def unregister():
    asset_ui.unregister()
    ui.unregister()
