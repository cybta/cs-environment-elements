# CS Environment Elements — TODO

One Blender add-on for the carpentry-simulator world. It replaces **House Generator**
(`room-generator/room_generator`) and **TreeGen** (`cs-tree-generator/treegen`); the old
folders stay untouched as a backup until this one is proven.

Sidebar tab **CS Env** → section switch at the top: Nature · Buildings · Props · Interior.
(The World section, an experimental whole-map builder, was removed on 2026-11-22.)

```
cs_environment_elements/
  core/       materials, bundled textures (assets/), scene helpers, tab + section switch
  nature/     trees, bushes, rocks                  (was TreeGen)
  buildings/  house, villa, cottage, shops, fences, Surroundings, LODs  (was House Generator)
  props/      outdoor props; ships the playground models for now
  interior/   furniture, Old / New
tools/        texture/mountain bake scripts (not part of the add-on zip)
```

## Phase 1 — merge (in progress)

- [x] New folder, package layout, one `bl_info` (v1.0.0, Blender 4.2+)
- [x] Shared helpers moved from `room_generator/__init__.py` to `core/materials.py`, `core/scene_utils.py`
- [x] Shared textures + `neighborhood_materials` moved to `core/`
- [x] World uses the nature section directly (no more `addon_utils.enable("treegen")`)
- [x] Playground models + textures bundled in `props/assets` (were read from the Desktop)
- [x] One tab "CS Env" with the section switch; every panel moved in
- [x] Refuses to enable while the old House Generator / TreeGen add-ons are on
- [x] Settings, operators and object/scene properties keep their old names, so saved .blend files still work
- [x] Headless test: register / unregister twice, section gating, every building type (with LODs),
      fence, tree, rock, bundled playground models + textures — all pass (2026-11-22)
- [x] ~~World build test~~ — World section removed (2026-11-22)
- [ ] Check in the real UI (panel order, sections, nothing missing)
- [x] Build `cs_environment_elements.zip` (`tools/build_zip.py`), install it in Blender 4.4,
      disable the two old add-ons (left installed, just off) — 2026-11-22; reinstalled 2026-11-24 (330 MB:
      organic peeling, white trim paint, gravel relief, Selected Paint)
- [ ] Zip is 246 MB: mostly textures (core/assets ~136 MB) — see "Cut zip size" below
- [ ] Put the project under git (local only)

## Naming (done 2026-11-22)

- [x] Everything made is named `<thing>-<style>-<n>` (`core/naming.py`): house-1, villa-modern-1,
      cottage-timber-1, cottage-painted-1, shop-row-1, fence-old-1, tree-pine-1, bush-flowering-1,
      rock-boulder-1, sofa-old-3seat-1, playground-old-swing-1 …; parts are `<name>_<part>`
- [x] Buildings: Generate = new one; Rebuild Selected keeps name and place (other type → next name)
- [x] Fences rebuild per outline and keep their name; trees/rocks rename when species/type changes
- [ ] Surroundings and World keep their own names (SR_Plot_01_House, Rock_0001…) — switch too?
- [ ] Villa plans can have two rooms with the same name (…_Study_Floor.001)

## Ground and sidewalk (done 2026-11-22)

- [x] Floor Above Ground: cottages 0.75 m (piles 3 cm into the gravel, plinth 13 cm), house / villa
      0.2 m (one slab), shops 0.15 m (their street sidewalk lands on the ground, 15 cm step at
      each door); set on type change, editable; root stays on the ground
- [x] House: 0.7 m sidewalk ring, top level with the floor (no step at the door)
- [x] Cottage: one gravel block (C_world_gravel) under house + veranda, 0.7 m round, past the steps
- [x] Shops: ring behind and beside, level with their street sidewalk; the street sidewalk + kerb
      reach past the sides by the same width, so front and sides are one continuous surface;
      villas: none (own paving)
- [x] Only from the panel buttons (`_build(site=True)`); Surroundings / World unchanged
- [ ] Shops' sidewalk top is exactly at ground level: hidden by a flat ground plane at the same
      height — user to decide (keep 0.15, or 0.19 so it stands 4 cm proud)

## Fences

- [x] Old fence: default gap 0.06 m (about half a 13 cm board); World's old fences 0.05–0.07 m
- [x] Old fence paint (`buildings/fence_paint.py`): colour picker, Peeling slider, Random Paint;
      one material C_fence_old_paint (+ _card) for every fence; colour + peel in the "Paint"
      colour attribute (glTF COLOR_0) on all meshes and LODs; shared peel mask
      `core/assets/old-fence/fence_paint_mask.png` (tools/make_fence_paint_mask.py);
      Godot shaders + setup in `core/assets/old-fence/godot/`; World's old fences get random paint
- [ ] Try the Godot shaders in the real project (not compiled in Godot yet)
- [x] Same system for the cottages (`core/paint.py`, `buildings/cottage_paint.py`): painted siding
      (lap + upright planks) and every cottage's corrugated roof; colour = named / Random (seed) /
      Custom picker, Peeling sliders, Random Paint; per-face paint (roof vs walls) in the same
      attribute; 3 materials (C_cottage_lap_paint, C_cottage_planks_paint_v, C_cottage_roof_paint)
      replace 11 per-colour textures; Godot: `core/assets/godot/peel_paint.gdshader`
- [x] Organic peeling (`tools/organic_noise.py`): domain-warped clumps + chips at every angle,
      per-board age; cottage materials detile (per-building shift from its position + a second,
      turned read of the wear map); rust on roofs smaller and scattered; nail rust per nail
- [x] Wear zones (`core/assets/neighborhood/wear_zones.png`, 256 px, over ~16 m, shifted per
      building): damage and roof rust gather in one or two areas instead of repeating per tile;
      roof rust moved out of the tiled _diff into the _paint alpha
- [x] Organic peeling v4 (user, 2026-11-23: "still repetitive, not organic"): where the paint lasts is now
      `core/paint_nodes.lasting`, shared by cottages and fences: big weather patches (wear_zones.png read at
      2.7 m and, turned 63 deg, at 6.3 m: never repeat) 0.72 + cracked flakes (`paint_flakes.png`, 2048 px over
      3 m, `tools/make_paint_flakes.py`: warped Voronoi cells, long along the grain / round on metal, G = cracks)
      0.21 + the surface's own board map 0.07 (fences 0.025: each plank's age flipped whole boards); cracks
      darken the paint just before it flakes. Where it peeled the wood is the timber cottages' old brown wood
      (user, 2026-11-23: not the pale, almost white patches): siding `under_tint` (lap 1.69/1.56/1.43, planks
      ~1), fences `fence_paint.PEELED_TINT` (0.40/0.36/0.28 on fence.png; every bare board, never-painted
      fences too); tints = cottage_wood_diff.jpg's mean colour (linear). The white trim (`C_cottage_trim`:
      window frames + casings, corner boards, bargeboards, veranda posts / rails / balusters) is peeling paint
      too (user, 2026-11-23: "the white elements"): white over cottage_wood_diff, upright grain, peel = the
      walls' + `cottage_paint.TRIM_EXTRA_PEEL` (timber cottages: the Peeling slider shows as "Trim Peeling");
      bare roof metal darker (`UNDER_TINT_ROOF`), "Grey Corrugated" paint 0.52 -> 0.34 sRGB (read near-white in
      sun). Wood grain along each piece (`buildings/grain.py`, user 2026-11-24): trim / veranda timber face UVs
      turned so the grain follows the face's longest side. Old neighbourhood palette (user, 2026-11-24,
      `drawn_lots.SCHEMES`): 40 % blue (6389a6 / 153752), 40 % teal (7ba3a1 / 225855), 20 % red (a66363 / 3a1414),
      light = walls + the lot's fence, dark = roof; walls 3-5 %, trim 3-6 %, roofs 3-8 %, fences 10-20 % peeled,
      every fence painted
      (user: "less sad", max 10-20 %).
      Fences: second UV layer "WearUV" (fence_geom, kept by lod.py + lod_cards; glTF TEXCOORD_1 / Godot UV2) =
      metres, U along the grain, continuous across boards. Godot: `core/assets/godot/paint_lasting.gdshaderinc`
      (compiles in 4.7.2, Vulkan); the old per-tile second read (DETILE) is gone
- [x] Game check (2026-11-23, glTF export -> Godot 4.7.2 default import): TEXCOORD_1 + COLOR_0 arrive;
      Godot's 16-bit mesh compression made world-metre WearUV (+-318) 9.7 mm steps -> WearUV now measured from
      each fence's first part (+-27 m -> 0.8 mm); paint_flakes.png needs High Quality (BC7: 1 % texels across
      the threshold vs 6 % with BC1); Godot edges widen by fwidth (the game's main view has no AA)
- [ ] UE5 / other engines: no materials yet (Godot only). UE: "Use Full Precision UVs" (half-float UVs are
      2-16 mm steps at 3-27 m), lightmap UVs to channel 2 (not 1 = WearUV), normal maps green flip, data
      textures as Masks + BC7
- [x] "Selected Paint" panel (`buildings/paint_edit.py`, user 2026-11-24: edit one house / fence without
      rebuilding): select any part of a generated cottage or old fence -> its own colours + peeled % (walls of a
      painted cottage, trim, roof; a fence's paint), read and written straight through the root's stored paint
      (`Object.cs_paint`: get/set properties, no storage of their own, so old files work too); a change repaints
      that object and its LODs at once. "Peeling / Colours to Selected" copy the active one's values to every
      selected cottage or fence (walls only between painted cottages). Tested headless on the neighbourhood
- [ ] Old doors and window frames with the same paint?
- [x] Shared Sides (e.g. "4" or "2, 4", or pick the selected edge): left out for neighbouring plots /
      walls; the fence ends square there; no doubled corner posts unless "Posts at Shared Ends"
- [ ] LOD2/3 fence cards draw the planks from fence.png with its own narrow gaps, stretched to
      board + gap, so far away the fence still reads as close-boarded

## Phase 2 — Core

- [ ] Move LOD (`buildings/lod*.py`) to `core/` so props, furniture and rocks share it
- [ ] Section on/off toggles in the add-on preferences
- [ ] One preset system: save / load a whole setup
- [ ] Pivot / origin and real-world-scale conventions for every asset
- [ ] One materials library (old vs new looks, worn variants)
- [ ] Cut zip size: drop unused files (`core/assets/*.zip`, `Procedural Concrete.blend`?), check texture resolutions

## Phase 3 — Interior (furniture, Old / New)

Every type has a **Style: Old / New** switch with the same inputs.
Old pieces exist in `Desktop\old furniture` (`.blend` + build scripts in `scripts/`).
New pieces: the user will provide them after the merge.

- [x] Framework (`core/library.py`, `core/asset_ui.py`): Type → Style Old/New → Piece → Add at
      Cursor (+ rotation), Add All in a row; copies share meshes; textures relinked by file name;
      floor pieces land bottom-centre on the cursor, wall/ceiling/counter pieces on their own origin
- [x] Old (`interior/assets/old`, from Desktop\old furniture): wingback armchair, sofa 2/3 seater,
      bentwood chair / bar stool / table, 50s fridge, 80s gas stove, 80s pendant lamp
- [x] New (`interior/assets/new`, from carpentry simulator\ref\3D Models\furniture, not desk-ufa):
      couch, chair, dining + coffee table, bed, mattress single/double/queen/king, pillow,
      kitchen sink, wash basin, toilet, shower head, radiator
- [x] Workshop (no style): workbench, workshop desk
- [x] Tested headless: all 32 pieces + 6 playground props placed, sizes right, no missing textures
- [ ] Gaps to fill: Old bed / bathroom / heating; New lighting; New kitchen appliances
- [ ] Furniture LODs (pieces are 1k-34k tris; pillow 34k is heavy)
- [ ] More new pieces when the user sends them
- [ ] More: bed, wardrobe, shelves, desk, TV unit; kitchen counters + sink; bathroom
      (toilet, sink, bath); lamps, rugs, curtains, plants
- [ ] "Furnish room": scatter a themed set (living room, kitchen, bedroom) into a generated house

## Old neighbourhood scene (2026-11-23, waiting for the user's approval, then Godot)
- [x] Porch flicker in Godot (2026-11-25): posts flush with the veranda deck edge + rim joists = shared planes
      (z-fighting). `cottage.JOIST_SET_BACK` = 1 cm; export_old_neighborhood.py applies it to the existing .blend in
      memory (only where the faces still meet) and rebuilds those cottages' LODs.
      Repair in place: `buildings/cottage_fix.py` (`set_back_veranda`, operator `csenv.fix_porch` = "Fix Porch
      Posts" / All in the Selected Paint panel for cottages; the export calls the same function). Applied to
      out/old_neighborhood.blend 2026-11-25 (20/20; backup old_neighborhood_before_porch_fix_2026-11-25.blend).
- [x] Export leaves the trees out (`LEAVE_OUT`, user 2026-11-25: they will scatter their own), and the bushes and
      rocks (user 2026-11-26: they will place them later).
- [x] Far LODs baked to one material (`buildings/lod_bake.py`, `bake_far(root, out_dir)`, 2026-11-26): own UV map
      (smart project), Cycles EMIT bake of every material's base colour (paint included), 1024 px LOD2 / 512 px LOD3
      JPEG, then one plain material. Destructive: the export runs it in memory (old neighbourhood: 40 bakes, 46 s;
      cottage draw calls from the air 200 -> 34). No operator yet; lod.build puts the many-material LODs back.
- [x] Export skips Bump nodes (glTF writes the bump's colour picture as the normal map: the yard props' planks came
      out yellow in Godot) and merges each cottage's LOD0 into _Exterior / _Inside / _Glass + _GF_Doors (2026-11-25).
- [x] Fence LOD1 `slim` (2026-11-25, lod.py LEVELS): a fence part under 4 cm thick keeps only its broad faces +
      its top at LOD1 (fences only: roots with cards); old neighbourhood fence LOD1 98k -> 62k tris.

Built from the USER'S DRAWN PLAN (all in `tools/scenes/`, outputs in `out/`, game world coordinates):
1. `extract_poor_quarter.py` (in HeightmapTerrain.blend, read-only) -> `poor_quarter_layout.json`: the bake's
   road / driveway centre lines; `old_neighborhood/layout.Network(scale=0.6)` = the quarter shrunk to 60 %
2. `plan_old_neighborhood.py` + `draw_old_neighborhood_plan.py`: my proposed plans (frontage.py); superseded
3. `draw_old_neighborhood_roads.py` -> `old_neighborhood_roads.png` (roads only, 8 px/m) + `.json` (px -> m)
4. The user drew on it -> `old_neighborhood_Edit.png`: fences red, houses grey, organic dirt roads + driveways
   beige-brown, labels: 20 lots, "park" (SW), "Empty space" (in the loop)
5. `read_old_neighborhood_drawing.py` -> `old_neighborhood_drawn.json` + `.png` (lots, houses, gates, shared
   sides, door sides; lot numbers are the user's, their label positions are in the script)
6. `make_old_neighborhood.py` (drawn.py, drawn_lots.py, drawn_street.py + lots.py / street.py / terrain.py):
   the dirt as road mesh, 20 cottages on the drawn footprints, street-facing fences pushed toward the road
   so a street is 6 - 7 m fence to fence (user, 2026-11-23; `drawn.Plan.push_fences`, the dirt may run into
   the lots; built lines in `out/old_neighborhood_fences.json`), shared sides once (by the lower-numbered lot), gates + wicket doors + paths, yards, 14 poles + wires + service cables
   (poles stand outside a street fence, surface 20 cm from it, user 2026-11-23, `DrawnStreet._fence_spot`;
   clear of corners, gates and wicket doors; one side of the street per run; road edge only where no fence;
   hand nudges in make_old_neighborhood.py: the bridge feeder's last pole 2 m west, user 2026-11-23),
   no gravel bed under the cottages (user, 2026-11-23: "doesn't make sense", ground cover can come in Godot;
   `s.sidewalk = False`), each cottage on the lowest ground under it minus 3 cm so no pile hangs on a slope,
   Jagged rocks, Gravel & Rubble on the road edges, trees. ~30 s build + ~3 min renders.
   The existing Cottage_70m2 was only a size reference (user, 2026-11-23): removed, lot 3 is a new cottage.

- [ ] User review in Blender
- [ ] Park + empty space: not designed yet (grass)
- [ ] Move to Godot: export per collection (context not for export); the terrain bake must follow the drawn
      roads (60 % layout, and the dirt mask instead of the old SE dead end); remove Cottage_70m2 from valley.tscn

## Phase 4 — Props (outdoor)

- [x] Prop panel for the old playground set (swing, slide, seesaw, merry-go-round, bench, bin)
- [x] Gravel & Rubble relief (user, 2026-11-23 "add a bump map"): `tools/props/build_gravel_rubble.py` makes the
      normal maps from a real height: every pebble of the photo a dome (local contrast), deep gaps, humps,
      grain; stones: lumps + fracture ridges + pits; strength from the map (`slope_scale`: steepest tenth
      ~54 deg gravel, ~45 deg stones; stone Normal Map 0.6 -> 1.0). Normal maps, not Bump nodes, so glTF
      carries them. Blender's Solid view never shows normal maps: judge in Material Preview / Rendered
- [ ] New-style playground
- [ ] Street lamps, benches, bins, bus stop
- [~] Electricity poles with sagging wires (wires only in the old neighbourhood scene so far, street.py)
- [ ] Mailboxes, signs, fire hydrants, manholes
- [ ] Parked cars (simple, old and new)
- [ ] Fountain, well, market stall, clothesline

## Phase 5 — Nature additions

- [ ] Bushes and hedges (hedges double as fences)
- [ ] Flowers and grass tufts
- [ ] Fallen logs, stumps; seasonal tree variants (autumn, bare)
- [ ] Pond / stream with reeds
- [ ] Garden beds, vegetable patch

## Phase 6 — Buildings additions

- [ ] Garage / carport, shed, greenhouse, gazebo
- [ ] Gates, driveways
- [ ] Porch, balcony, awning, chimney options
- [ ] Swappable window / door library, old and new

## Houses and villas — for tomorrow (asked 2026-11-26, all houses / villas)

- [ ] **Mediterranean villa: more than one roof, and not a square block.** Today it is one box under one hip roof.
      Break the footprint up (wings / an L or T plan, a lower wing or a tower), each part with its own roof
      (hips and gables at different heights, joined by valleys), like the refs in `Desktop/ref/villas`.
- [ ] **Rooms about 1 m wide and 4 m deep (all houses and villas).** Some plans make long thin slivers. Find where
      the layout allows them (`_distribute` / `MIN_WIDTH`, row depth, bathrooms and stores in deep rows) and set a
      minimum width / maximum depth-to-width ratio per room kind; re-flow or merge instead of squeezing.
      Check the "rooms squeezed below comfortable width" warnings across areas and seeds.
- [ ] **More windows, so the facades are never empty.** Some walls are bare. Add windows by wall length / storey
      (a window rhythm along every outside wall, aligned between floors where it can), keep the
      Mediterranean villa's few round ones, and check all villa styles, houses and shops.

## Phase 7 — World (dropped)

The World section was experimental and was removed on 2026-11-22, with it these plans:
scattering props along roads and parks, interior fill for hero buildings, an Old / New / Mixed
era switch for a whole town.

## Valley east side: mid-range houses, villas, shops (started 2026-11-26)

User (2026-11-26): build them with the add-on generators (house / villa / shop, LODs, far bake, one export, like the
old neighbourhood); the user draws the lots.
- [x] `tools/scenes/extract_east.py` (Blender, terrain .blend read-only): the east roads + 27 driveways from the bake's
      own centre-line code -> `east_layout.json` (56 road + 27 driveway segments; all 83 sit on the painted road mask).
- [x] `tools/scenes/draw_east_roads.py` (system Python + Pillow) -> `out/east_roads.png` (6 px = 1 m, 4046 x 2210,
      flat land tinted, water blue, 10 m grid) + `out/east_roads.json` (px -> world).
- [x] 2026-11-26: a move 32 m away from the river was tried and undone (user kept the first spot; terrain
      restored from backup). Sheet with the building sizes: `out/east_roads_sizes.png` (`draw_east_roads.py
      east_roads_sizes`; sizes from `measure_building_sizes.py` -> `east_type_sizes.json`).
      **Handoff for the next session: `tools/scenes/EAST_SIDE_NOTES.md`.**
- [x] The user drew it (2026-11-25, `out/east_roads_sizes-with-houses.png`: pasted pictures, not the colour code):
      `read_east_drawing.py` -> `east_drawn.json/png`; shrunk x0.428 to the user's size (House 10's lot 650 m2, 7 m
      roads + 1.8 m sidewalks, shops 7 x 8 m, a back road to the shops 1-3 parking) by `plan_east.py` ->
      `east_plan.json/png`; built by `make_east.py` (+ `east/`) -> `out/east.blend` + 4 renders. House 1 is "Sam's
      Caffee" + a second shop (GROCER, the generator's pick). All in `tools/scenes/EAST_SIDE_NOTES.md`.

### East side fixes — the user's list for the next session (2026-11-25)

- [x] **1. Shops 1-3 (the row by the river) face the bridge road** (user, 2026-11-25: "the shopping center near the
      river is facing the parking, it should face the road"). `plan_east.py FACE_STREET`: turned round, its own
      sidewalk meets the street's at the pad edge (2.7 m further into the pad); the back road still runs along the
      parking's far side (`away` = the drawn front). Shops 4-6 still face their parking.
- [x] **2. Houses 100-140 m2 of floor in all**, 1 or 2 floors (`set_house`, seeded per lot): 7.8 x 6.4 to 15.1 x 9.0 m.
      A two-floor house this small can get too steep stairs ("stairwell is shallow"): `build_lot` tries other layout
      seeds (same size and roof), then one floor. `east_plan.png` shows the real footprints (see below).
- [x] **3. Modern + Gable villas**, alternated (no lots named): `make_east.py VILLA_STYLES` (1, 3, 5 Modern; 2, 4, 6
      Gable). Change the dict to swap any lot.
- [x] **4. Two shopping rows; Sam's Caffee is a shop in one** (user, 2026-11-25: "the Sam's Caffe should be in one of
      the other stores center and remove it from being stand alone"). The café row on House 1 is gone (House 1 is a
      house again, normal fence + gate); `make_east.py SHOP_SIGNS`: Shops 1-3 shop 1 (nearest the bridge) = Sam's
      Caffee, the rest generator names (no CAFE / TEA ROOM).
- [x] **5. Facades 3-5 m behind the gate**: `east/buildings.py GATE_GAP = 4.0` (3.9-4.0 m as built). Villas get a
      4 m own driveway / front path (`villa.FRONT_YARD` patched per build) ending on the fence; a path a slanted fence
      cuts is trimmed back inside. Sideways they stay on the plan's line unless the driveway would then miss the
      street (Villa 1: slid 3.3 m so its driveway meets the north loop's end). Lots unchanged.
- [x] **6. Fences** (the user's screenshots, 2026-11-25): "remove these bends, fences should be completely straight;
      the gate should lead to a parking lot while the door is aligned with the house door, same for the villas;
      replace this house (House 10) with a 2 floor":
      - straight lots: `east_lots.py` (from plan_east.py) rebuilds every lot from its real corners (142 -> 82), so
        each side is one straight fence; neighbours share their corners exactly (shared sides were fenced twice,
        their traced outlines lay 0.3-1 m apart); a side cutting into a sidewalk is moved back (verge strips where the
        street curves); the cul-de-sac lots get a few straight pieces round the turning circle. Left as drawn: the
        gaps between Villa 4 / 5 / 6 and on House 1's sides toward the shops (two fences there);
      - houses: a 3 x 6 m parking space beside the house (away from its front door if there's room) running out
        through the gate; only layouts with the front door on the street side are kept; a 1.2 m walk from the front
        door through the fence's door (in line) to the sidewalk, the mailbox on the door's far side from the gate;
      - villas: the gate on their driveway to the carport, the door where the front path meets the fence (Villa 3's
        entrance is beside its carport: its door sits next to the gate);
      - House 10: two floors.
- [x] **Round 2 (user's screenshots, 2026-11-25): "flatten the fences on House 5 and Villa 1; the land should be
      flattened and the fences straight on the Z axis; all houses 2 floors"**:
      - `east_lots.py`: a short side with no neighbour beside a street front joins the front (no corner), so House 5,
        Villa 1 and House 4's cul-de-sac side each have one straight front, set back off the road's end; small traced
        jogs (< 0.4 m) ironed out first, corners turning < 6° taken out at the end: every lot is 4 sides (Villa 1: 8);
      - `east/ground.py FlatGround`: the scene's ground levelled at the median height under the lots (42.99 m) over
        lots, pads and streets (+1 m), blended back over 12 m (bridge road's bank kept): cut up to 4.1 m (House 5's
        back), fill 1.6 m; every fence is level. **The game's heightmap isn't levelled yet**: the terrain step must do
        the same (east_built.json "ground");
      - every house two floors (`set_house`; sizes and roofs kept); a house whose parking strip would miss the street
        (House 5, at the road's end) slides sideways until it runs onto it (`_slide_to_street`).
- [x] **Round 3 (user's screenshot of Houses 4-6, 2026-11-25): "the fences should be aligned with the sidewalk; remove
      the curved end of the road and cut it straight and have the fountain in front of it"** (a round shape drawn: "a
      small fountain later"):
      - `plan_east.py CUL_DE_SACS` / `cut_ends`: that road is one straight line (through the junction), stops square
        where its curled end reached; a fountain spot (r 3.8 m, where the user drew it) 2.5 m beyond, on a paved plaza;
        the no-build lane runs on 30 m so Houses 4 and 5 keep straight fences past the end;
      - `east_lots.py _align_streets`: any street side along a straight stretch goes exactly onto the sidewalk's edge
        (Houses 4 / 5 / 6 at 5.4 m from the centreline, one line for 5 and 6);
      - Blender: square road ends, the plaza paved with kerbs, a placeholder basin ("ES Fountain (placeholder)") for
        the user's fountain; renders `east_culdesac_top.png`, `east_fountain.png`.
- [ ] The fountain itself (the user: "later"): replace the placeholder basin.
- [ ] Next: the terrain step (level the game's heightmap as east_built.json "ground" says, the east roads in the road
      masks, from east_plan.json + the driveways in east_built.json), export, Godot node, hills closer.

