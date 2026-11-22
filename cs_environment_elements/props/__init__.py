"""Props section: outdoor props, listed in catalog.py: the old playground set (swing set,
slide, seesaw, merry-go-round, bench, bin; World > parks places the same models) and old
wooden electric poles (built by tools/props/build_electric_pole.py)."""

import os

from ..core.asset_ui import Catalog
from . import catalog

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

CATALOG = Catalog("PROPS", "Props", "cs_props", ASSET_DIR, "Props", catalog.KINDS)


def register():
    CATALOG.register()


def unregister():
    CATALOG.unregister()
