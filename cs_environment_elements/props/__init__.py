"""Props section: outdoor props. For now the old playground set (swing set, slide, seesaw,
merry-go-round, bench, bin), listed in catalog.py; World > parks places the same models.
Street lamps, benches, poles etc. come next."""

import os

from ..core.asset_ui import Catalog
from . import catalog

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

CATALOG = Catalog("PROPS", "Props", "cs_props", ASSET_DIR, "Props", catalog.KINDS)


def register():
    CATALOG.register()


def unregister():
    CATALOG.unregister()
