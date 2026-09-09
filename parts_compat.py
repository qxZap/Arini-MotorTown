#!/usr/bin/env python3
"""parts_compat.py -- a standalone compat between a parts mod and the mods it unregisters.

    Ships as ProxyWheels_<Mod>_Compat_<idx>_P.pak.

    python parts_compat.py --base zzzProxyTechWheels --out ProxyWheels_Atlas_Compat_P.pak
    python parts_compat.py --base zzzProxyTechWheels --deploy

WHY THIS IS ITS OWN PAK, NOT PART OF THE ISLAND
    It fixes a quarrel between OTHER PEOPLE'S MODS. Atlas 8x8 ships its own copy
    of the VehicleParts composite naming only the parent tables it knows about,
    it mounts after almost everything, and the last copy wins -- so
    ProxyTechWheels' Wheels_PT and MoreTuning's License_OversizeEscort1 stop
    being registered and those parts silently vanish.

    None of that involves Arini. Somebody running Atlas with wheel mods and no
    map needs this fix; somebody running the island with no wheel mods does not.
    Bundling it into the island's compat would force both on everyone, which is
    why it lives here.

    It also carries the transfer-case labels: vanilla's Vehicle string table
    stops at six driven wheels ("4L", "6L"), so an 8x8 asks for a key nobody
    wrote and the readout comes up blank. That is Atlas versus vanilla, not
    Atlas versus the island, so it belongs with this pak too.

NAMING
    The output must mount AFTER the mod whose copy is winning. A filename sorts
    before itself-plus-a-suffix, so naming it <thatmod>_<something>_P.pak lands
    it immediately after and nowhere else -- no run of z's needed, and it does
    not leapfrog mods it has no argument with.

RUN IT WHEN A MOD UPDATES, not every build. Which copy to build on is a
judgement call -- see composite_merge.py, which reports who drops what.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mt_paths import GAME_PAKDIR, MAPPINGS, REPAK, WORK_DIR
from composite_merge import extract, paks_shipping, parents, repak_exe

COMPOSITE = "DataAsset/VehicleParts/VehicleParts.uasset"
LABELS_REL = "DataAsset/StringTables/Vehicle.uasset"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True,
                    help="pak substring whose composite to build on (the one that worked)")
    ap.add_argument("--out", help="output .pak path")
    ap.add_argument("--deploy", action="store_true", help="copy into the game's Paks/")
    ap.add_argument("--no-labels", action="store_true", help="skip the transfer-case labels")
    args = ap.parse_args()

    entry = f"MotorTown/Content/{COMPOSITE}"
    found = paks_shipping(entry)
    if not found:
        print("  nothing ships the parts composite", file=sys.stderr)
        return 1

    match = [p for p in found if args.base.lower() in p.name.lower()]
    if not match:
        print(f"  --base {args.base!r} matched none of: "
              f"{', '.join(p.name for p in found)}", file=sys.stderr)
        return 1
    base_pak = match[-1]

    # The union across every copy, so no mod loses its parents whichever base wins.
    work = Path(WORK_DIR) / "parts_compat"
    shutil.rmtree(work, ignore_errors=True)
    union: set[str] = set()
    for i, pak in enumerate(found):
        got = extract(pak, entry, work / str(i))
        if got:
            union |= set(parents(got))

    stage = work / "stage"
    dst = stage / "MotorTown" / "Content" / Path(COMPOSITE).parent
    dst.mkdir(parents=True, exist_ok=True)
    src = extract(base_pak, entry, work / "base")
    if not src:
        print(f"  could not extract the composite from {base_pak.name}", file=sys.stderr)
        return 1
    for ext in (".uasset", ".uexp", ".ubulk"):
        s = Path(str(src.with_suffix("")) + ext)
        if s.is_file():
            shutil.copy2(s, dst / s.name)
    staged = dst / src.name
    print(f"  base: {base_pak.name}")

    add = ",".join(f"/Game/{Path(COMPOSITE).parent.as_posix()}/{p}" for p in sorted(union))
    r = subprocess.run([str(INJECTOR), "register-parent-tables", "--uasset", str(staged),
                        "--mappings", str(MAPPINGS), "--add", add],
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip() and "already registered" not in line:
            print("    " + line.strip())
    if r.returncode != 0:
        return r.returncode

    if not args.no_labels:
        rc = _add_labels(stage, work)
        if rc:
            return rc

    # THE PATCH INDEX DECIDES, NOT THE FILENAME.
    #
    # Unreal reads the digits immediately before the _P suffix as a patch index,
    # and a higher index wins outright -- filename order never gets consulted.
    # Atlas ships as ..._1_0_1_P.pak, i.e. index 1, which is why its README
    # insists on that exact suffix. Every pak we shipped ended in a plain _P
    # (index 0), so four different composites were outranked before their
    # contents mattered, including a byte-identical copy of the one that works.
    #
    # So: name after the winner AND outrank it.
    winner = found[-1]
    m = re.search(r"_(\d+)_P$", winner.stem)
    idx = int(m.group(1)) + 1 if m else 1
    out = Path(args.out) if args.out else Path(f"ProxyWheels_{winner.stem.split("_")[1]}_Compat_{idx}_P.pak")
    print(f"  outranking {winner.name} (patch index {idx - 1}) with index {idx}")
    subprocess.run([repak_exe(), "pack", str(stage), str(out)],
                   capture_output=True, text=True)
    if not out.is_file():
        print("  packing failed", file=sys.stderr)
        return 1
    print(f"  wrote {out}  ({out.stat().st_size:,} bytes)")

    if args.deploy:
        # Land immediately after the mod we are patching: a name sorts before
        # itself plus a suffix, so this needs no z-padding at all.
        target = Path(GAME_PAKDIR) / out.name
        shutil.copy2(out, target)
        print(f"  deployed {target.name}")
    return 0


def _add_labels(stage: Path, work: Path) -> int:
    """Transfer-case keys vanilla never defined (see drivemode_labels.py)."""
    from drivemode_labels import LABELS
    from mt_paths import GAME_CONTENT
    src = Path(GAME_CONTENT) / LABELS_REL
    if not src.is_file():
        print("  vanilla Vehicle string table not found -- labels skipped", file=sys.stderr)
        return 0
    dst = stage / "MotorTown" / "Content" / Path(LABELS_REL).parent
    dst.mkdir(parents=True, exist_ok=True)
    for ext in (".uasset", ".uexp", ".ubulk"):
        s = Path(str(src.with_suffix("")) + ext)
        if s.is_file():
            shutil.copy2(s, dst / s.name)
    staged = dst / src.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(LABELS, fh)
        entries = fh.name
    try:
        r = subprocess.run([str(INJECTOR), "extend-stringtable", "--src", str(staged),
                            "--output", str(staged), "--mappings", str(MAPPINGS),
                            "--entries", entries], capture_output=True, text=True)
    finally:
        Path(entries).unlink(missing_ok=True)
    for line in r.stdout.splitlines():
        if "StringTable" in line:
            print("    " + line.strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
