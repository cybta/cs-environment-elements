"""Interior section: furniture in Old and New styles (sofa, chair, table, bed, kitchen,
bathroom, heating, lighting) plus the workshop pieces. Pieces are listed in catalog.py
and placed from the bundled .blend files in assets/old and assets/new."""

import os

from ..core.asset_ui import Catalog
from . import catalog

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

CATALOG = Catalog("INTERIOR", "Furniture", "cs_interior", ASSET_DIR, "Furniture", catalog.KINDS)


def register():
    CATALOG.register()


def unregister():
    CATALOG.unregister()
