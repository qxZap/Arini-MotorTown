#!/usr/bin/env python3
"""check_server_parity.py -- the server must ship what the client ships.

    python check_server_parity.py            # report
    python check_server_parity.py --quiet    # only complain

WHY THIS EXISTS
    A dedicated server and its clients run the same world. If the server's copy
    is missing content the client has, the client arrives somewhere and waits
    for actors the server will never send -- it does not error, it hangs, or the
    connection simply drops with "Your connection to the host has been lost".

    That is not hypothetical. The server build silently lost all 34
    delivery-point actors: step 3 placed them, step 5 wrote the level back
    through UAssetAPI's typed LevelExport path, and they were gone. Every pak
    verified fine on its own, because nothing compared the two builds.

WHAT IS ALLOWED TO DIFFER
    Byte-for-byte equality is NOT the test -- the two are separate cooks. The
    server's packages are versioned, the client's unversioned, so every shared
    asset differs in size and content. What must match is the SET of things:
    the same cells, the same delivery-point classes, the same classes
    referenced by the map.

    The server legitimately lacks purely visual assets the client cook does not
    even produce (the in-game map texture, UI). Those are listed, not failed.
"""
from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path("Arini_P/MotorTown/Content")
SERVER = Path("Arini_Server_P/MotorTown/Content")
CELLS = "Maps/Jeju/Jeju_World/_Generated_"
DP = "Objects/Mission/Delivery/DeliveryPoint"

# Client-only trees the server cook does not produce at all. Rendering data.
VISUAL_ONLY = ("UI/", "Textures/", "T_WorldMap")

_fail: list[str] = []
_ok: list[str] = []


def ok(m): _ok.append(m); print(f"  [ok]   {m}")
def bad(m): _fail.append(m); print(f"  [FAIL] {m}", file=sys.stderr)


def names(root: Path, sub: str, pat: str) -> set[str]:
    d = root / sub
    return {p.stem for p in d.glob(pat)} if d.is_dir() else set()


def referenced(map_file: Path, classes: set[str]) -> set[str]:
    """Which of `classes` the map's name table mentions."""
    if not map_file.is_file():
        return set()
    blob = map_file.read_bytes()
    return {c for c in classes if c.encode("ascii", "ignore") in blob}


def main() -> int:
    quiet = "--quiet" in sys.argv
    if not CLIENT.is_dir() or not SERVER.is_dir():
        print("  one of the two builds is not staged -- nothing to compare")
        return 0

    # 1. world-partition cells
    c_cells, s_cells = names(CLIENT, CELLS, "*.umap"), names(SERVER, CELLS, "*.umap")
    missing = c_cells - s_cells
    if missing:
        bad(f"server is missing {len(missing)} of {len(c_cells)} cell(s), "
            f"e.g. {', '.join(sorted(missing)[:3])}")
    else:
        ok(f"same {len(c_cells)} world-partition cell(s)")
    if extra := s_cells - c_cells:
        bad(f"server ships {len(extra)} cell(s) the client does not: "
            f"{', '.join(sorted(extra)[:3])}")

    # 2. delivery-point classes, and that the MAP actually places them
    c_dp, s_dp = names(CLIENT, DP, "Mod*.uasset"), names(SERVER, DP, "Mod*.uasset")
    if c_dp - s_dp:
        bad(f"server is missing {len(c_dp - s_dp)} delivery-point class(es)")
    else:
        ok(f"same {len(c_dp)} delivery-point class(es)")

    # Shipping the class is not the same as PLACING the actor. This is the
    # check that would have caught the lost delivery points.
    c_ref = referenced(CLIENT / "Maps/Jeju/Jeju_World.umap", c_dp)
    s_ref = referenced(SERVER / "Maps/Jeju/Jeju_World.umap", c_dp & s_dp)
    if len(s_ref) < len(c_ref):
        bad(f"the server MAP places only {len(s_ref)} delivery point(s) where the "
            f"client places {len(c_ref)} -- clients will hang waiting for actors "
            f"the server never sends")
    elif c_ref:
        ok(f"the map places the same {len(c_ref)} delivery point(s) on both")

    # 3. every other shipped asset
    def tree(root: Path) -> set[str]:
        return {p.relative_to(root).with_suffix("").as_posix()
                for p in root.rglob("*") if p.is_file()}
    c_all, s_all = tree(CLIENT), tree(SERVER)
    gone = {p for p in c_all - s_all
            if not p.startswith(CELLS) and not any(v in p for v in VISUAL_ONLY)}
    if gone:
        bad(f"server is missing {len(gone)} shipped asset(s), "
            f"e.g. {', '.join(sorted(gone)[:4])}")
    else:
        ok("server ships every non-visual asset the client does")
    if not quiet:
        visual = {p for p in c_all - s_all if any(v in p for v in VISUAL_ONLY)}
        if visual:
            print(f"  [note] {len(visual)} client-only visual asset(s) — expected, "
                  f"the server cook does not produce them")

    print(f"\n  PARITY: {'OK' if not _fail else str(len(_fail)) + ' difference(s)'} "
          f"— {len(_ok)} check(s) passed")
    return 1 if _fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
