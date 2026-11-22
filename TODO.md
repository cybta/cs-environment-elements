# CS Environment Elements — TODO

One Blender add-on for the carpentry-simulator world. It replaces **House Generator**
(`room-generator/room_generator`) and **TreeGen** (`cs-tree-generator/treegen`); the old
folders stay untouched as a backup until this one is proven.

Sidebar tab **CS Env** → section switch at the top: Nature · Buildings · Props · Interior · World.

```
cs_environment_elements/
  core/       materials, bundled textures (assets/), scene helpers, tab + section switch
  nature/     trees, bushes, rocks                  (was TreeGen)
  buildings/  house, villa, cottage, shops, fences, Surroundings, LODs  (was House Generator)
  props/      outdoor props; ships the playground models for now
  interior/   furniture, Old / New
  world/      the whole map, uses every section above
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
- [ ] World build test — on hold, user said not to run it for now
- [ ] Check in the real UI (panel order, sections, nothing missing)
- [x] Build `cs_environment_elements.zip` (`tools/build_zip.py`), install it in Blender 4.4,
      disable the two old add-ons (left installed, just off) — 2026-11-22
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

## Phase 4 — Props (outdoor)

- [x] Prop panel for the old playground set (swing, slide, seesaw, merry-go-round, bench, bin)
- [ ] New-style playground
- [ ] Street lamps, benches, bins, bus stop
- [ ] Electricity poles with sagging wires
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

## Phase 7 — World

- [ ] Scatter props along roads and parks (lamps at intervals, benches in parks, poles on streets)
- [ ] Interior fill for hero buildings
- [ ] Era switch: Old / New / Mixed town (buildings, props and furniture follow it)
- [ ] Open from before: forest reads sparse with small trees; no cars yet
