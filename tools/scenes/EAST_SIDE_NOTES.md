# Valley east side: houses, villas, shops — handoff notes

Status 2026-11-25: **the drawing is in and read; waiting on the user's answers** (below). Nothing is built yet. Read
this first in a new session, then the old neighbourhood's scripts in this folder (the same pipeline, done once already).

## The drawing as received (2026-11-25)

`out/east_roads_sizes-with-houses.png` (+ the layered `out/east_roads_sizes.psd`): the sheet pasted on a bigger canvas
(4605 x 3219) at the SAME scale, offset (175, 562) px (found from the corner marks). It does NOT use the colour code:
- villas and houses are pasted top-down PICTURES (one villa, one house, copied and rotated), not filled footprints.
  They are drawn big: villa roofs ~62 x 39 m, house roofs ~47 x 25 m (their cars are ~2.3x real size);
- shop rows = grey 128 blocks with black dividers (2 rows of 3, each block ~103 x 37 m) on parking pads
  (183, 184, 178), ~9,500 m2 each; lot outlines red as asked; text labels for the names; "Park" east of Villa 6.
- Roads redrawn: kept the bridge road, the main street through the houses, the west connector and the east curve;
  removed the second north-south road + its cross link, the old south road (now the shops 4-6 parking) and the east
  stub; NEW: the north loop past the villas, villa driveway stubs, parking accesses. Old 3 m driveways that don't match
  the pictures are leftovers.
- Lots: 6 villas ~8,500-10,600 m2, 11 houses ~4,000-7,300 m2 (about 10x the island lots). Villa 1's lot reaches into
  the river (17 % water); villas 2-5 run 7-26 % past the flat land to the north (the sheet's top edge hid that).

`read_east_drawing.py` (numpy + Pillow: run it with Inkscape's Python, `C:/Program Files/Inkscape/bin/python.exe`;
~3 min) -> `out/east_drawn.json` (lots, drawn buildings with front direction, shop rows, parking, all in Blender
metres) + `out/east_drawn.png` (the redraw: pale = as drawn, solid = the generator at real size, red arrow = front;
drawing code in `east_drawn_render.py`). Lot names/seeds and label positions are hand-listed in the two scripts.

**Decided 2026-11-25 (user): shrink it.** "Make this part ~7 times smaller, House 10's land 650 m2, squeeze
everything down, keep the streets and the shapes; I like this neighbourhood." -> `plan_east.py ["House 10" 650]`
(Inkscape's Python) scales east_drawn.json by one factor about a point on the bridge road (bridge end fixed, roads
stay 7 m, lots trimmed back from the road, the factor solved so House 10 = 650 m2 after the trim; the centre as near
the bridge as the flat land allows), drops the drawn driveway stubs (each house / villa gets a 3 m drive from its
front to the road) and writes `out/east_plan.json` + `out/east_plan.png` (`east_plan_render.py`). Shared helpers:
`east_raster.py` (morphology, labelling, outlines, rectangles, road centrelines by thinning). THIS plan is what
make_east.py builds from; the terrain's east roads get replaced by its roads.
Result 2026-11-25: factor 0.417 (areas x0.174), centre (-63.1, -15.7) on the bridge road (~98 m east of the bridge
end (-161.2, -21.2)); House 10 652 m2; villa lots 1,440-1,790 m2, house lots 650-1,200 m2; buildings (the pictures
squeezed, their cars now life size) villas ~24-29 x 15-18 m, houses ~19-20 x 10 m, shop rows 43 x 15.5 m (3 shops of
14 m) on ~1,500-1,650 m2 parking; 640 m of 7 m road.
Then (user, 2026-11-25): **every shop 7 x 8 m** (both rows: 21 x 8 m, each row keeps its back line; `SHOP_W/SHOP_D`)
and **a back road for Shops 1-3**: from the bridge road up the parking's west side (1 m clear) and east into the back
of the lot (`BACK_ROADS`, built from the pad's outline so it follows the plan; saved under `added_roads`). Parking
tarmac now 1,353 / 1,469 m2; ~694 m of road. Waiting on: OK of the placement (as near the river as the flat land
allows), building villas/houses at the squeezed sizes (bigger than the presets), shop fronts toward the parking,
then a go for the terrain roads + make_east.py.

Open questions put to the user before the shrink (2026-11-25; sizes and the off-flat lots are settled by it): building size (real generator sizes vs as big as the pictures); Villa 1
in the river and villas 2-5 off the flat land (trim the lots or flatten more terrain); shop fronts (assumed: toward
their parking, so shops 1-3 turn their backs to the bridge road); villa style (assumed gable, the pictures have
pitched roofs) and house preset; which lots are the story's workshop, player's home and Mrs. Harper.

## What the user wants

- Fill the valley's east side (the road network east of the river, past the bridge) with **3 shops, the houses
  (mid-range) and the villas**, built with this add-on's generators: House, Modern Villa, Gable Villa, Shopping Row.
  LODs, far-LOD bake (`buildings/lod_bake.py`) and one export, like the old neighbourhood (user, 2026-11-26).
- The user draws the lots themselves on the sheet (below), like they did for the old neighbourhood.
- **After this:** bring the guard hills / mountains closer to the built areas, so there is no huge empty
  forest to wander (game TODO.md).

## The sheet to draw on

`out/east_roads_sizes.png` (4046 x 2610 px, **6 px = 1 m**, north up; `out/east_roads_sizes.json` = px -> world).
- Map area: rows 0-2099. World (Blender metres): x = -201.167 + px / 6, y = 174.893 - py / 6; Godot x = x, z = -y.
  Same frame as the first sheet `out/east_roads.png` (identical map, no sizes panel).
- Rows 2100+: colour key, the building sizes at the same scale, the island's lot sizes. Not map: a reader must
  only look at rows < 2100.
- Colours to use (same as the key): **lot / fence outline red (194, 26, 26)**, footprints FILLED: **house grey
  (171, 171, 171)**, **villa purple (140, 80, 170)**, **shop blue (40, 90, 200)**, plus a **number per lot**
  (as with the old neighbourhood, note each number's pixel position by eye when reading the drawing).
- Existing roads: grey 128 (7 m), driveways grey 150 (3 m); the 27 driveways are where the user's original
  drawing put houses. Flat land is tinted cream, water light blue.
- Which type each footprint is comes from its colour; the door / front side should face the nearest road or
  driveway (as read_old_neighborhood_drawing.py does: the side whose normal points most toward the lot's gate).

## Building sizes (measured, `measure_building_sizes.py` -> `east_type_sizes.json`)

walls = the building (width along the street x depth); all = with what it brings (sidewalk; villas: driveway +
paving in front; shops: street sidewalk).

| Type (panel preset) | walls (m) | all (m) | floors, height |
|---|---|---|---|
| House 100 m2 | 11.7 x 8.6 | 13.3 x 10.2 | 1, 5.9 m |
| House 130 m2 | 9.3 x 7.0 | 11.0 x 8.6 | 2, 8.3 m |
| House 200 m2 | 11.7 x 8.6 | 13.3 x 10.2 | 2, 8.8 m |
| Modern villa 200 / 240 / 320 m2 | 10.0 x 12.0 / 10.2 x 13.7 / 11.6 x 15.6 | 10.9 x 21.1 / 11.1 x 22.8 / 12.5 x 24.7 | 2, 6.4 m |
| Gable villa 170 / 200 / 260 m2 | 9.1 x 10.7 / 9.7 x 11.7 / 10.9 x 13.2 | 15.4 x 19.8 / 16.0 x 20.8 / 17.2 x 22.3 | 2, 8.7-9.5 m |
| Shopping row, 3 shops | 19.8 x 10.0 | 21.5 x 13.6 | 2, 9.8 m |
| Shopping row, 4 shops | 25.3 x 10.0 | 27.0 x 13.6 | 2, 9.8 m |

The generators fit the walls to the area asked for, so a drawn footprint maps to an area (W x D x floors) and the
nearest preset; Shopping Row has Shops (count), Shop Width (5 m default) and Depth (10 m) settings.

## Island references (what the east side replaces; `carpentry simulator/blender_src/terrain/out/site_plan.json`)

- N1: 22 house lots (10 x "50", 7 x "70", 4 x "140", 1 workshop "WS"), fence areas: 50 ~570 m2, 70 ~640 m2,
  140 ~1580 m2, workshop 516 m2. N2: 9 villas (5 modern ~1100 m2, 4 gable ~950 m2). 3 shop sites 30 x 24 m.
- The story uses island lots: **H01 = the workshop, H14 = the player's home, H18 = Mrs. Harper**, Jennifer's
  office upstairs in the Shopping Centre (knowledge pack §16a). When the valley becomes the game map, those need a
  home on the east side: ask the user which drawn lots they are.
- Old neighbourhood cottage lots: ~490 m2 median (about 20 x 25 m).

## Terrain state

- The east network is at `EAST_SHRINK.center = (175, 5)` (`carpentry simulator/blender_src/terrain/
  valley_road_centerlines.py`). On 2026-11-26 it was tried at (200, 25) (32 m further from the river); the user
  preferred (175, 5) and it was restored from `blender_src/terrain/out/backup_before_east_away_2026-11-26/` (exact
  files) + the Desktop `HeightmapTerrain_before_east_away_2026-11-26.blend`. If the roads move again, re-run
  `extract_east.py` and `draw_east_roads.py` and give the user a NEW sheet (they may be drawing on the old one).

## The Blender scene (2026-11-25, user: "start with the blender file: road with a sidewalk, houses, shops, villas;
## House 1 is a coffee shop, Sam's Caffee")

plan_east.py now also puts **1.8 m sidewalks** on every street (not on the parking accesses or the shops 1-3 back
road), trims the lots and parking to the sidewalk's outer edge and re-solves the factor so House 10 stays 650 m2
(now x0.428), and writes the surface map `out/east_plan_surfaces.png` (class x 50: 1 asphalt, 2 sidewalk,
3 parking, 4 driveway; mapping in east_plan.json "surfaces").

`make_east.py` (`blender -b --factory-startup --python make_east.py`, ~20 s, + renders; RENDER=0 skips them) ->
`out/east.blend` + `out/east_top / aerial / cafe / street.png`. Modules in `east/`:
- `surfaces.py` (built after the buildings): an asphalt base (streets, parking, under the sidewalks) and the raised
  sidewalks (+0.18 m, 0.15 m kerb, kerb faces on every edge) as 0.5 m terrain-following cells whose outline corners
  are snapped onto the exact edges (3.5 m / 5.3 m from the centrelines, the pads, 1.5 m either side of each
  driveway as built), so kerbs run smooth; 3 m driveways (C_path) from each front (a villa: the front end of its own
  driveway) to the asphalt; nothing over the river (the bridge spans it). It does not read
  east_plan_surfaces.png (that map is for the terrain's road masks later);
- `buildings.py`: (first build) House (2 floors, ~16-18.5 x 10.5 m), Gable Villa (300-360 m2, 11.6 m wide = the
  generator's max; own driveway, some with a pool), Shopping Row 3 x (7 x 8 m) (24.8 m long with the stair bay),
  and a two-shop café row on House 1; all changed by the user's fixes (below);
- `fences.py`: Modern fences on the lot outlines (shared sides once), gate + door + mailbox (lot number) where the
  driveway comes in; villas 1.8 m, houses 1.4 m.
Heights: a house / villa at the median ground under it; a shop row with its own sidewalk's top level with the street
sidewalk (terrain + 0.18) at its front edge.

**Fences, gates and doors (2026-11-25, the user's screenshots; add-on TODO "East side fixes" 6):**
- `east_lots.py` (called by plan_east.py after the lots are laid out): straight lot sides between the real corners
  (where a side starts / stops along a street, turns >= 30° elsewhere, and along a street where it bends > 1.5 m off
  straight: the cul-de-sac), corners of neighbours within 1.5 m merged and a corner on a neighbour's side inserted
  there, so a shared side is one fence; sides cutting into a sidewalk / road moved back (corners slide along the
  sides beside them). The gaps between Villas 4 / 5 / 6 and round House 1's shop side are in the drawing: two fences.
- houses: `buildings.py _house_parking`: a PAD_W x PAD_L (3 x 6 m) parking space beside the house, away from the
  front door when there's room (else the roomier side; the house slides over if it must), its strip runs along the
  front through the gate to the asphalt (the driveway); the house layout is retried until its ENTRANCE is on the
  street wall (and the stairs aren't too steep); `door_start` (in front of the door) -> `to_walk` (onto the
  sidewalk): a 1.2 m footpath (`surfaces.walk`), and the fence's door where it crosses (fences.py `_door_side`),
  the mailbox pillar on the side away from the gate;
- villas: gate on their own driveway (carport), door where their FrontPath meets the fence (+ a walk to the
  sidewalk across any verge);
- all houses two floors (user, round 2; `set_house`); a house whose parking strip would miss the street (a road's
  end in front of it: House 5) slides sideways until it runs onto it (`_slide_to_street`).
- round 2 (user): `east_lots.py` joins a short side with no neighbour beside a street front into that front (House
  5, Villa 1, House 4: one straight front set back off the road's end), irons out traced jogs < 0.4 m first and
  takes out corners turning < 6° last (every lot 4 sides, Villa 1 8);
- **level ground** (user, round 2: "the land should be flattened and the fences straight on the Z axis"):
  `east/ground.py FlatGround` wraps the terrain for the whole build: LEVEL = the median ground under the lots and
  pads (42.99 m) over every lot, pad and street (+ sidewalks) 1 m wider, blended back over 12 m; a street whose ground
  is > 1.5 m below the level (the bridge road's bank) keeps the terrain. Cut up to 4.1 m (House 5's back), fill up to
  1.6 m. The game's valley heightmap is NOT changed yet: the terrain step must level it the same way (the numbers are
  in `out/east_built.json` "ground").

**The user's fixes, done 2026-11-25** (add-on TODO "East side fixes" 1-5):
- Shops 1-3 face the bridge road (`plan_east.py FACE_STREET`; the plan's shop row has `faces`: "street" / "parking"),
  set forward in make_east so its 2.6 m sidewalk meets the street's at the pad edge. Shops 4-6 face their parking.
- No café building: House 1 is a house. `make_east.py SHOP_SIGNS = {"Shops 1-3": ["Sam's Caffee", None, None]}`
  (plan numbering: shop 1 nearest the bridge; the generator counts along its own +X, build_shops maps the two).
- Houses 100-140 m2 in all, 1 or 2 floors (seeded); a too-steep-stairs layout is retried with other seeds, then 1 floor.
- Villas: `make_east.py VILLA_STYLES` (Modern 280-340 m2, Gable 300-360 m2).
- Facades `GATE_GAP` = 4 m behind the gate (the villa's own driveway / path = 4 m, `villa.FRONT_YARD` patched for
  the build); sideways on the plan's line, or slid so the driveway is on it if it would miss the street.
- make_east writes `out/east_built.json` (walls, sizes, floors, gate distance, driveways, shop signs and door
  points) and runs `east_plan_render.py` (Inkscape's Python) to redraw `out/east_plan.png` with the buildings as
  built; plan_east.py alone draws the pictures' rectangles ("as drawn"). `east_plan_surfaces.png` still has the
  plan's driveways (from the pictures): the terrain step should take the driveways from east_built.json.
Not yet: street lamps, trees / yard things, parking bays, the export. Terrain: everything is 42-44 m except House 5
(its footprint spans ~2 m of the slope at the flat land's edge, so part of it is in the hill) -> the terrain step
must flatten the new layout.

**The cul-de-sac by Houses 4-6 (2026-11-25, the user's screenshot: red fence lines, a round shape = "a small
fountain later"; "the fences should be aligned with the sidewalk; remove the curved end of the road, cut it straight,
the fountain in front of it"):**
- `plan_east.py CUL_DE_SACS = ["House 5"]`, `cut_ends`: the road whose free end is nearest House 5 is refitted as one
  straight line (its straight run + the street straight on through the junction, PCA), starts on that line at the
  junction and stops SQUARE where the old curled end's asphalt reached (`flat_ends` [[road, 0|-1]]); the fountain
  spot (r FOUNTAIN_R 3.8 m, the user's circle measured from the screenshot: on the centreline ~30 m past the
  junction) FOUNTAIN_GAP 2.5 m beyond the end, on a plaza the street's width (10.6 m) with a round far end; the
  no-build `lane` runs on LANE 30 m so the lots either side are cut straight. All in east_plan.json "cul_de_sacs".
- `east_lots.py _align_streets`: a street side whose street runs straight along it (centreline within 0.6 m of a
  line, < 20° off) goes exactly onto the sidewalk's outer edge (+ CLEAR 0.1 m); its corners slide along the sides
  beside it. Houses 4 / 5 / 6 now 5.4 m off the centreline, House 6's far corner 5.56 m (the street starts to bend).
- Blender: square road ends in `surfaces._segments/_nearest` (and make_east's `to_asphalt`), the plaza paved at
  sidewalk height with kerbs, `surfaces.fountain_spot` a placeholder basin in "ES Fountain (placeholder)", the plaza
  and lane levelled (`ground.py`); renders `east_culdesac_top.png` + `east_fountain.png`.

## Next steps once the drawing is in

1. DONE 2026-11-25: `read_east_drawing.py` -> `out/east_drawn.json` + `out/east_drawn.png` (see above). Still to
   do there once the user answers: road centrelines for step 4.
2. `make_east.py`: like `make_old_neighborhood.py`: each footprint -> the generator of its type, sized to it, front
   to the road; fences on the outlines (modern / stone fences for villas, see `buildings/fence_modern.py`); ground
   heights from `valley_height.exr`. Saves `out/east.blend` (the user may hand-tune it after: then never rebuild
   over it without asking).
3. `export_east.py`: like `export_old_neighborhood.py` (LOD0 merge, far-LOD bake, Bump skip, LEAVE_OUT) ->
   `carpentry simulator/data/models/valley/east.glb`; a Godot node like `OldNeighborhood`
   (`scripts/world/old_neighborhood.gd`: LOD ranges, collision, door rule; the paint shaders only matter for cottages).
4. Clear / repaint the east roads in the terrain masks if the drawing changes them (as
   `valley_old_neighborhood_masks.py` did for the old quarter).

Tools in this folder: `extract_east.py` (Blender, terrain .blend read-only -> `east_layout.json`),
`draw_east_roads.py [name]` (system Python + Pillow -> `out/<name>.png/.json`), `measure_building_sizes.py`
(Blender -> `east_type_sizes.json`).
