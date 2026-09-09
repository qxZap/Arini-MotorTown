#!/usr/bin/env python3
"""parts_registry.py -- keep every installed parts table registered.

    python parts_registry.py <mod content dir> [--dry-run]

WHY THIS EXISTS
    DataAsset/VehicleParts/VehicleParts is a COMPOSITE table. It holds no
    parts; it NAMES the tables that do. Every parts mod ships its own copy
    listing the parents it happens to know about, and paks mount in filename
    order, so the last one wins and silently unregisters everybody else's
    tables.

    Nothing errors. The other mod's assets are still installed, still in the
    pak, still perfectly valid -- the game simply never looks at them, so the
    parts are not offered and their labels resolve to nothing. It reads as
    "the mod didn't install" or "a string table is missing".

    Measured 8 Sep: Atlas 8x8 Semi (six leading z's, so it mounts after almost
    everything) registers 21 parents and omits two that are installed --
    Wheels_PT, which is ProxyTechWheels', and License_OversizeEscort1, which
    is MoreTuning's. Proxy's custom wheels could not be fitted to any vehicle.

WHAT IT DOES
    Stages the EFFECTIVE composite -- the copy the game actually loads, via
    mt_paths.effective_asset -- and appends any parent table that some
    installed pak ships and nobody registers. It appends rather than writing a
    list of its own: the next mod to ship a composite would overwrite ours
    anyway, and a union is the only shape that survives being mounted over.

    Only useful in a layer that mounts LAST. A layer that loses the load order
    cannot fix this for anyone.

WHAT IT DOES NOT DO
    Nothing at all unless MTMI_PARTS_REGISTRY=1. It also never invents a table:
    a name is only registered if some installed pak actually ships that asset,
    so a typo or a since-removed mod cannot leave a dangling parent behind.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from mt_paths import GAME_CONTENT, GAME_PAKDIR, MAPPINGS, REPAK, _cfg, effective_asset

REL = "DataAsset/VehicleParts/VehicleParts.uasset"
SUBDIR = "DataAsset/VehicleParts"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")


def _own_paks() -> list[str]:
    """Filename fragments of paks WE produce, from mods.json's always_skip."""
    import json
    cfg = json.loads((Path(__file__).resolve().parent / "mods.json")
                     .read_text(encoding="utf-8"))
    out: list[str] = []
    for m in (cfg.get("mods") or {}).values():
        if m.get("always_skip"):
            out += [x.lower() for x in (m.get("match") or [])]
    return out


def shipped_tables() -> set[str]:
    """Every parts table any installed mod pak ships, by leaf name.

    Deliberately NOT filtered by the layer's MTMI_EXCLUDE_PAKS. That list
    exists so we never base our own tables on another mod's data, which is
    right -- but registering a parent table imports nobody's rows. It states
    that a table exists, and only when an installed pak actually ships it. A
    layer that hides MoreTuning from the cargo build must still register
    MoreTuning's parts, or hiding it from ourselves hides it from the player.

    Our own paks are skipped: a table we shipped last build is not evidence
    that a mod provides it.
    """
    own = _own_paks()
    found: set[str] = set()
    for pak in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda p: p.name.lower()):
        low = pak.name.lower()
        if low in ("motortown-windows.pak", "motortown.pak"):
            continue
        if any(x in low for x in own):
            continue
        r = subprocess.run([str(REPAK), "list", str(pak)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            continue
        for line in r.stdout.splitlines():
            e = line.strip().replace("\\", "/")
            if e.startswith(f"MotorTown/Content/{SUBDIR}/") and e.endswith(".uasset"):
                found.add(Path(e).stem)
    found.discard("VehicleParts")          # the composite itself is not a parent
    return found


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if (_cfg("MTMI_PARTS_REGISTRY", "") or "").strip() != "1":
        return 0
    content = Path(sys.argv[1])
    dry = "--dry-run" in sys.argv

    tables = shipped_tables()
    if not tables:
        print("  parts registry: no mod ships a parts table -- nothing to do")
        return 0

    # BASE ON VANILLA, not on the copy the game loads.
    #
    # effective_asset hands back the last mod's composite -- Atlas's -- and
    # appending to that produced a table that verified perfectly and did
    # nothing: 23 parents, well-formed imports, correct load order, and the
    # wheels stayed missing. The identical code path DOES work for the
    # Vehicles composite, and the only difference is that one starts from
    # vanilla's cooked asset.
    #
    # So start from vanilla here too and re-add every parent from scratch.
    # Nothing is lost by it: shipped_tables() already enumerates every parts
    # table any installed pak provides, which is a superset of what any single
    # mod's composite lists.
    src = GAME_CONTENT / REL
    if not Path(src).is_file():
        src = effective_asset(REL)
    if not Path(src).is_file():
        print(f"  parts registry: {REL} not found -- skipped", file=sys.stderr)
        return 0

    if dry:
        print(f"  would stage {Path(src).name} and offer {len(tables)} table(s)")
        return 0

    dst_dir = content / SUBDIR
    dst_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(src).with_suffix("")
    for ext in (".uasset", ".uexp", ".ubulk"):
        s = Path(str(stem) + ext)
        if s.is_file():
            shutil.copy2(s, dst_dir / s.name)
    staged = dst_dir / Path(REL).name
    print(f"  parts registry: staged from {Path(src).parent.name}/{Path(src).name}")

    if not INJECTOR.is_file():
        print("  injector not built -- parent tables left alone", file=sys.stderr)
        return 1
    add = ",".join(f"/Game/{SUBDIR}/{t}" for t in sorted(tables))
    r = subprocess.run([str(INJECTOR), "register-parent-tables",
                        "--uasset", str(staged), "--mappings", str(MAPPINGS),
                        "--add", add],
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            print("    " + line.strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
