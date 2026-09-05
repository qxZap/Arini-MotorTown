# Archived builds

Each folder is a deployable `zzzz_Arini_P.pak` plus the `.env` that produced
it. To go back to one, copy its pak over the one in the game's Paks folder;
to rebuild it, restore the two settings below and `python repack_layer.py
vanilla`.

Two knobs, two budgets. They are NOT interchangeable:

    Landscape grid LoadingRange  -> cells kept RESIDENT  -> RAM + load time
    foliage.CullDistanceScale    -> instances that DRAW  -> GPU

Foliage cells are registered on the **Landscape** streaming grid, not
MainGrid. `MTMI_WP_LOADING_RANGE` is MainGrid's and has never applied to
them, which is why vanilla's 409600 went unnoticed: ~996k instances and
~519k physics bodies resident at all times, 29% of the island.

Every tier keeps the same 4.1x margin between draw distance and unload
distance. Instances still drawing when their cell unloads pop out instead of
fading, so that ratio is the invariant, not either number alone.

| tier    | LoadingRange   | CullScale | draw      | resident inst | bodies  |
|---------|----------------|-----------|-----------|---------------|---------|
| default | 102400 (1 km)  | (none)    | 175-250 m |        96,723 |  51,180 |
| high    | 204800 (2 km)  | 2         | 350-500 m |       315,541 | 182,335 |
| extreme | 409600 (4 km)  | 4         | 0.7-1 km  |       996,583 | 519,277 |

Measured in game (this machine, many other mods loaded alongside):

| tier    | load | RAM   | FPS vs default |
|---------|------|-------|----------------|
| default | 3 s  | 5 GB  | --             |
| high    | 5 s  | 6 GB  | -5%            |
| extreme | ?    | ?     | ?              |

`extreme` is vanilla's own Landscape range, so it is the configuration the
island shipped with before any of this work -- but with the collision and
Nanite fixes on top, which cost it 9 GB and 15 s without them.
