#!/usr/bin/env python3
"""check_layer_sync.py -- catch compat paks left behind by a base rebuild.

    python check_layer_sync.py            # check the DEPLOYED paks
    python check_layer_sync.py --quiet    # only complain

WHY THIS EXISTS
    A compat layer ships the Mod* delivery-point classes and mounts AFTER the
    base pak, so its copy of every class WINS. That is the entire mechanism --
    the class name is sha1(delivery point key), identical in every layer, so
    the base map's actors already point at the class the layer overrides.

    Which means a base rebuild regenerates classes the compats then override
    with older copies, and nothing else in the pipeline looks across layers:
    every pak verifies fine on its own.

    HOW MUCH THIS ACTUALLY MATTERS IS UNPROVEN. It was written while chasing

        LowLevelFatalError UObjectArchetype.cpp:175
        SceneComponent .../Mod85A97ADA.Default__Mod85A97ADA_C:SceneComponent
        had RF_NeedLoad when being set up as an archetype

    on a build where the compats were 20 hours stale -- but that turned out
    NOT to be the cause. The .uexp holding the recipe data was byte-identical
    between base and compat, only the .uasset header differed, and that same
    pairing had been played for an hour without trouble. The real cause was an
    editor export landing DURING the build, so the map was generated from a
    half-written scene.

    So treat a stale compat as a smell worth clearing, not a proven fault.

WHAT IT CHECKS
    Every deployed compat pak must be at least as new as the deployed base.
    Not byte equality -- compats ship DIFFERENT recipes on purpose, so their
    classes legitimately differ. What must hold is that they were generated
    against the same base, and mtime is the cheap proxy for that.
"""
from __future__ import annotations

import sys
from pathlib import Path

from mods import load
from mt_paths import GAME_PAKDIR

# A base rebuild regenerates classes the compats override, so a compat older
# than the base is stale. The reverse is fine: a cargo-only change repacks the
# compat and leaves the base alone.
SLACK_SECONDS = 0


def main() -> int:
    quiet = "--quiet" in sys.argv
    _, layers = load()
    paks = Path(GAME_PAKDIR)

    def pak_of(layer: str) -> Path:
        l = layers[layer]
        return paks / f"{l.get('pak_prefix', 'zzzz_')}{l['mod_name']}.pak"

    base_layer = next((k for k, v in layers.items() if not v.get("delta")), None)
    if base_layer is None:
        print("  no non-delta layer in mods.json -- nothing to check")
        return 0
    base = pak_of(base_layer)
    if not base.is_file():
        print(f"  base pak not deployed ({base.name}) -- nothing to check")
        return 0
    base_mt = base.stat().st_mtime

    stale, missing, ok = [], [], []
    for layer, l in layers.items():
        if not l.get("delta"):
            continue
        p = pak_of(layer)
        if not p.is_file():
            missing.append(layer)
            continue
        (stale if p.stat().st_mtime + SLACK_SECONDS < base_mt else ok).append(
            (layer, p, p.stat().st_mtime))

    if not quiet:
        import datetime
        def when(t): return datetime.datetime.fromtimestamp(t).strftime("%m-%d %H:%M")
        print(f"  base {base.name}  {when(base_mt)}")
        for layer, p, t in sorted(ok) + sorted(stale):
            mark = "STALE" if (layer, p, t) in stale else "ok"
            print(f"    {mark:<5} {p.name:<40} {when(t)}")
        for layer in missing:
            print(f"    ----  {layer}: not deployed")

    if stale:
        print(f"
  {len(stale)} compat pak(s) older than the base. Their Mod* "
              f"classes were generated against an earlier map and they mount "
              f"last, so they win. NOT known to be fatal on its own -- clear "
              f"it before blaming anything subtler.", file=sys.stderr)
        print(f"  Rebuild them: build.bat --layer "
              + " / --layer ".join(l for l, _, _ in stale), file=sys.stderr)
        return 0
    if not quiet:
        print("  every deployed compat is at least as new as the base")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
