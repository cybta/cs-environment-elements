"""Outdoor props, by kind and style. Old = the user's old playground set (assets/playground).
Copies are named <name>-1, <name>-2... (thing-style-variant).

The World builder places the same playground files itself (world/world_parks.py).
"""

from ..core.library import Item

_PG = "playground/playground_"

KINDS = [
    ("PLAYGROUND", "Playground", "OUTLINER_OB_FORCE_FIELD", {
        "OLD": [Item("old_swing", "Swing Set", _PG + "swing_set.blend", name="playground-old-swing"),
                Item("old_slide", "Slide", _PG + "slide.blend", name="playground-old-slide"),
                Item("old_seesaw", "Seesaw", _PG + "seesaw.blend", name="playground-old-seesaw"),
                Item("old_merry", "Merry-Go-Round", _PG + "merry_go_round.blend",
                     name="playground-old-merry-go-round"),
                Item("old_bench", "Bench", _PG + "bench_bin.blend", ["PlaygroundBench"],
                     name="bench-old-playground"),
                Item("old_bin", "Bin", _PG + "bench_bin.blend", ["PlaygroundBin"], name="bin-old-playground")],
        "NEW": [],
    }),
]
