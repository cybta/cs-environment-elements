# Bentwood furniture set: build scripts

Thonet-era bentwood café furniture and fittings for the 1980s coffee shop. The shared
materials are created by `ensure_material()` in `bentwood_lib.py`:

- `OldWornWood`: the furniture wood, using the textures in `../textures`.
- `CreamEnamel`: 80s cream-painted metal for lamps and fittings.
- `BulbGlow`: a warm emissive bulb, which exports as glTF emission.

| Script | What it does |
|---|---|
| `bentwood_lib.py` | Shared helpers: bent tubes (capped or looped), lathe/turned parts, grain-aligned UVs, the shared material, and `finish()` (weld, normals, smoothing, triangle report). |
| `build_table.py` | Builds `OldBentwoodTable`: round 70 cm top, apron ring, 4 legs, 4 arches. About 3.3k tris. |
| `build_stool.py` | Builds `OldBentwoodBarStool`: round 36 cm seat at 76 cm, foot ring, 4 arches. About 3.3k tris. |
| `build_chair.py` | Original chair generator. The shipped chair was hand-edited and optimised afterwards, so running this gives the older, heavier version. See the note at the top of the script. |
| `build_pendant_lamp.py` | Builds `PendantLamp80s`: 80s cream metal cone shade (42 cm), dome cap, globe bulb, wire hoop, straight cord and ceiling canopy. About 2.5k tris. Its origin is the ceiling point, and you set the drop with `CORD_LEN`. It also adds a preview point light (`PendantLamp80s_Light`) just under the bulb. |
| `build_gas_stove.py` | Builds `GasStove80s`: freestanding 60 x 60 x 85 cm cream-enamel gas cooker with 4 burners, cast-iron pan supports, 5 knobs, an oven door with dark glass and a bar handle, a drawer and a recessed plinth. About 4.3k tris, uses 5 material slots (`CreamEnamel`, `BlackEnamel`, `CastIron`, `Aluminium`, `OvenGlass`). |
| `build_fridge.py` | Builds `Fridge50s`: 1950s rounded-top fridge, 74 x 70 x 148 cm, aged cream enamel. It has a pillow-edged door hinged on the left, a chrome lever handle on a round boss, a chrome badge with a blue strip and a gold half-round emblem (no brand lettering), pinstripes, a raised panel bead, bottom grille lines, a black gasket and 4 feet. About 2.5k tris, 5 material slots. |
| `sofa_lib.py` | Upholstery helpers for the sofas: `sweep()` (a 2D outline extruded with rounded, stuffed edges), rolled-arm outline, tapered legs, and the `PlaidFabric` (generated `textures/fabric_plaid_512.png`) and `GreenVelvet` materials. |
| `build_sofa.py` | Set `SEATS` to 1, 2 or 3. 2 and 3 build `OldSofa2Seater` / `OldSofa3Seater`: a rolled-arm camelback sofa in plaid, 1.64 / 2.24 m wide, about 2.6k / 3.1k tris. 1 builds `OldArmchairWingback`: a green velvet wingback armchair, 0.97 m wide and 1.10 m tall, about 2.5k tris. Slots: 0 fabric, 1 `OldWornWood` legs. |
| `sofa_age_lib.py` | Makes the sofas old and very used (on by default, `AGED = False` in `build_sofa.py` turns it off). It densifies the upholstery, then sags the seat cushions (one favourite seat much deeper), squashes and slides them, dents the backrest, crushes and splays the arms, droops the base, adds lumpy stuffing, cuts torn patches showing old foam (slot 2 `ExposedStuffing`), paints a `Wear` grime colour attribute (hands, heads, seats, floor kicks), and decimates to about 10k / 12k / 14k tris for 1 / 2 / 3 seats. It is seeded, so rebuilds match. |
| `make_worn_fabric_textures.py` | Generates the tileable 1k worn upholstery maps: `fabric_plaid_worn_*` (faded, stained, pilled gingham), `velvet_green_worn_*` (crushed, bald velvet) and `stuffing_foam_*`. Headless: `blender -b --factory-startup --python make_worn_fabric_textures.py`. The worn materials multiply the texture by the `Wear` colour, which exports as glTF `COLOR_0`; in Godot, keep *Vertex Color > Use as Albedo* on. |
| `make_sofa_set.py` | Runs `build_sofa.py` for all three and saves `sofa_1_seater.blend`, `sofa_2_seater.blend`, `sofa_3_seater.blend`, `old_sofa_set.blend` and `render/old_sofa_set_render.png`. Headless: `blender -b --python make_sofa_set.py`. |
| `playground_lib.py` | Playground helpers (load after `bentwood_lib.py`): `bent()` welded pipes with rounded bends, `chain()` interlocking links, `sheet()` swept profiles (slide chute), `part()` for moving child parts, `center_footprint()`. Worn textured materials: `PaintRed/Blue/Green/Yellow` and `DarkSteel` (paint peeling to rust), `PeeledWoodRed/Blue/Green/Yellow` (paint peeling to grey wood: carousel deck, seesaw seats), `GalvSteel` (rust-spotted galvanised chute), plus plain `Rubber`. `paint()` gives each part a random UV offset so the wear never repeats. |
| `make_peeled_textures.py` | Generates the tileable 1k maps those materials use (`textures/peeled_*`, `textures/galv_worn_*`): diffuse, roughness, OpenGL normal, and metallic for the galvanised steel. Change `PAINTS`, the seeds or the 0.70 peel quantile (about 30 % of the paint gone), then rerun: `blender -b --factory-startup --python make_peeled_textures.py`. |
| `build_slide.py` | Builds `PlaygroundSlide` (ref/playground): yellow pipe A-frame with hoop handrails, 5-rung ladder, 2.9 m galvanised chute with edge rails. 3.8 m long, 2.05 m tall, about 2.2k tris. |
| `build_park_bench.py` | Builds `PlaygroundBench` (1.6 m, wood slats on dark steel arches, about 1.4k tris) and `PlaygroundBin` (slatted wood bin with a galvanised liner and a black band, about 1.3k tris). |
| `build_merry_go_round.py` | Builds `MerryGoRoundBase` (static pedestal) and child `MerryGoRound` (1.9 m, 4 coloured quarters, 4 seats, about 3.6k tris). Spin the child about its local Z. |
| `build_seesaw.py` | Builds `SeesawBase` and child `Seesaw` (3 m beam, origin = pivot at 0.52 m, about 0.9k tris). Tilt the child about its local Y, up to about 17 degrees. |
| `build_swing_set.py` | Builds `SwingSet` (3.56 m A-frame, beam at 2.3 m) and children `Swing_1..3`, each with its origin on the beam. Swing them about local X. Real chain links make about 4.7k tris per swing; `CHAIN_LINKS = False` uses plain rods instead. |
| `make_playground_set.py` | Runs the five playground scripts and saves `playground_*.blend`, `old_playground_set.blend` and `render/old_playground_set_render.png`. Headless: `blender -b --python make_playground_set.py`. |
| `optimize_for_game.py` | Cleans the active mesh for the game: welds caps, fills holes, reduces triangles, re-unwraps with the grain aligned. |

## Running

In Blender, open a script in the Text Editor and click **Run Script**. Each build script
removes and rebuilds its own object at the origin. Scripts find `bentwood_lib.py` and
`../textures` relative to their own folder, so keep this folder layout:

```
old furniture/
  old_bentwood_chair.blend
  old_bentwood_table.blend
  old_bentwood_bar_stool.blend
  pendant_lamp_80s.blend
  gas_stove_80s.blend
  fridge_50s.blend
  old_bentwood_set.blend      (everything together, with a preview light and camera)
  textures/
  scripts/
```

## Conventions

- Units are metres, Z is up, and the chair front faces -Y. Each object's origin is on the floor at its centre.
- Grain runs along texture U, and `TILE = 0.6` m per texture repeat across the whole set.
- Joints are 1–2 mm press fits, so parts touch without visible gaps.
- Tube control points must be evenly spaced, because uneven spacing makes the Catmull-Rom curve overshoot.
