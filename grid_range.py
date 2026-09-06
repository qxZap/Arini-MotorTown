#!/usr/bin/env python3
"""grid_range.py -- set a streaming grid's LoadingRange on the staged map.

    python grid_range.py <mod content dir> [--dry-run]

WHY THIS EXISTS
    Foliage cells are registered on the LANDSCAPE grid, not MainGrid
    (inject_foliage_cells.py sets grid="Landscape"). That was deliberate:
    Landscape's 409600 range keeps every foliage cell resident for the whole
    session, so nothing ever pops -- including when you look backward, which
    MainGrid's 25600 could never fix.

    The bill for "nothing ever pops", measured on the shipped instance set:

        loading range         resident instances   physics bodies
        409600 (4 km)                    996,583          519,277
        204800 (2 km)                    315,541          182,335
        102400 (1 km)                     96,723           51,180

    29% of the island is loaded at all times. That is where the RAM and the
    teleport time go, and no amount of collision simplification touches it --
    that made each of the half-million bodies cheaper, never fewer.

    MTMI_WP_LOADING_RANGE does NOT reach this. It only ever wrote MainGrid
    (Program.cs, RegisterCellsBatch), so the Landscape grid kept its vanilla
    409600 through every build.

WHAT IT DOES NOT DO
    Nothing, unless MTMI_LANDSCAPE_LOADING_RANGE is set. The Landscape grid
    also streams vanilla Jeju's terrain, so lowering it makes distant TERRAIN
    pop too. That is the reason this is a knob and not a default: it is a
    measurement tool until a foliage-only third grid exists.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from mt_paths import MAPPINGS, _cfg

MAIN_MAP = "Maps/Jeju/Jeju_World.umap"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")
GRID = "Landscape"
ENV = "MTMI_LANDSCAPE_LOADING_RANGE"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    content = Path(sys.argv[1])
    dry = "--dry-run" in sys.argv

    # _cfg, not os.environ: a standalone repack must honour .env the same
    # way build.bat does, or the setting silently does nothing.
    # Applying this re-opens and REWRITES the whole map. On the client that is
    # seconds. On the dedicated-server map it is 24 GB of RAM and 25+ minutes,
    # because a VERSIONED package materialises every one of its ~77k exports
    # instead of leaving unknown classes as raw bytes. Not worth paying per
    # build for one float, so the server layer sets MTMI_SKIP_GRID_RANGE=1.
    # (An empty MTMI_LANDSCAPE_LOADING_RANGE would NOT do it: _cfg falls back
    # to .env, which still has a value.)
    if (_cfg("MTMI_SKIP_GRID_RANGE", "") or "").strip() == "1":
        print("  grid range skipped (MTMI_SKIP_GRID_RANGE=1)")
        return 0
    raw = (_cfg(ENV, "") or "").strip()
    if not raw:
        return 0                      # not set: the grid keeps vanilla 409600
    try:
        rng = float(raw)
    except ValueError:
        print(f"  {ENV}={raw!r} is not a number -- ignored", file=sys.stderr)
        return 0

    target = content / MAIN_MAP
    if not target.is_file():
        print(f"  {MAIN_MAP} not staged -- {GRID} range left alone")
        return 0
    if not INJECTOR.is_file():
        print("  injector not built -- grid range left alone", file=sys.stderr)
        return 1
    if dry:
        print(f"  would set {GRID} LoadingRange -> {rng:.0f}")
        return 0

    r = subprocess.run([str(INJECTOR), "set-loading-range", "--mappings", str(MAPPINGS),
                        "--umap", str(target), "--grid", GRID, "--range", f"{rng:.0f}"],
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            print("    " + line.strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
