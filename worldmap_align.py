#!/usr/bin/env python3
"""worldmap_align.py -- point the game's map bounds at the map image we ship.

    python worldmap_align.py <mod content dir> [--dry-run]

WHY THIS EXISTS
    The in-game map is TWO things that must agree: a texture, and the world
    rectangle the game believes that texture covers. The rectangle lives in
    DataAsset/GameResource.uasset at DriveMaps[0].WorldMap, as a centre and a
    size.

    Shipping one without the other is the quiet failure worldmap.py warns
    about in its own output: "puts the island in the right place and every
    marker in the wrong one". The island looks fine, roads sit slightly off,
    and nothing errors.

    worldmap.py records the rectangle for the image it produced in
    worldmap_bounds.json. This applies it. Before, that was a line printed for
    a human to copy, which is exactly the kind of step that gets skipped --
    the shipped pak was 18 km out in X because a texture got refreshed and the
    bounds did not.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mt_paths import MAPPINGS

BOUNDS = Path("worldmap_bounds.json")
GAME_RESOURCE = "DataAsset/GameResource.uasset"
WORLD_MAP = "UI/InGame/Map/WorldMap/T_WorldMap_Jeju.uasset"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")


def wanted() -> tuple[float, float, float] | None:
    """(centre x, centre y, size) for the image worldmap.py last produced."""
    if not BOUNDS.is_file():
        return None
    try:
        b = json.loads(BOUNDS.read_text(encoding="utf-8"))
        x0, x1 = float(b["min_x"]), float(b["max_x"])
        y0, y1 = float(b["min_y"]), float(b["max_y"])
    except Exception:
        return None
    # set-worldmap takes a centre and ONE size, so the rectangle has to be
    # square. worldmap.py makes it square; take the larger span if it is not.
    return (x0 + x1) / 2, (y0 + y1) / 2, max(x1 - x0, y1 - y0)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    content = Path(sys.argv[1])
    dry = "--dry-run" in sys.argv

    if not (content / WORLD_MAP).is_file():
        print("  no world map staged -- bounds left alone")
        return 0
    target = content / GAME_RESOURCE
    if not target.is_file():
        print(f"  {GAME_RESOURCE} not staged -- cannot set map bounds", file=sys.stderr)
        return 1
    w = wanted()
    if w is None:
        print("  worldmap_bounds.json missing or unreadable -- bounds left alone")
        return 0
    cx, cy, size = w

    if not INJECTOR.is_file():
        print("  injector not built -- bounds left alone", file=sys.stderr)
        return 1
    args = [str(INJECTOR), "set-worldmap", "--mappings", str(MAPPINGS),
            "--uasset", str(target)]
    if not dry:
        args += ["--center-x", f"{cx:.0f}", "--center-y", f"{cy:.0f}",
                 "--size", f"{size:.0f}"]
    r = subprocess.run(args, capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            print("    " + line.strip())
    if r.returncode != 0:
        return r.returncode
    verb = "would set" if dry else "set"
    print(f"  {verb} map bounds: centre ({cx:.0f}, {cy:.0f}) size {size:.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
