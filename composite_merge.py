#!/usr/bin/env python3
"""composite_merge.py -- see and repair CompositeDataTable conflicts by hand.

    python composite_merge.py <Content-relative asset>              # report only
    python composite_merge.py <asset> --base <pak> --apply <dir>    # write a merge

    e.g.
    python composite_merge.py DataAsset/VehicleParts/VehicleParts.uasset
    python composite_merge.py DataAsset/VehicleParts/VehicleParts.uasset \
        --base zzzProxyTechWheels --apply Arini_Atlas_P/MotorTown/Content

WHY THIS EXISTS
    A CompositeDataTable holds no rows. It NAMES the tables that do. Several
    mods each ship their own copy naming the parents THEY know about, paks
    mount in filename order, and the last one wins -- silently unregistering
    everybody else's tables. Nothing errors; the parts simply stop existing.

    This is deliberately a REPORT plus a manual merge, not a build step. The
    choice of which copy to build on is a judgement call that has already been
    wrong twice here: a merge based on Atlas's copy verified perfectly and did
    nothing in game, and so did one based on vanilla's. The base matters for
    reasons not visible in the file, so a human picks it and tries it. Expect
    to run this when a mod updates -- roughly monthly -- not every build.

WHAT --base MEANS
    The pak whose copy of the composite is used as the starting file. Pick the
    one that was DEMONSTRABLY WORKING before the conflict appeared, not the
    newest and not vanilla. Its parents plus every other copy's parents are
    then registered into it, so the result is the union no matter which base
    you choose -- only the file it is written on top of differs.

OODLE
    Some paks are Oodle-compressed and the bundled repak refuses a DLL whose
    hash it does not recognise. Point MTMI_REPAK_OODLE at a repak.exe that
    sits beside a matching oo2core DLL -- PakMerge ships one that works here.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from mt_paths import GAME_CONTENT, GAME_PAKDIR, MAPPINGS, REPAK, WORK_DIR

INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")


def repak_exe() -> str:
    """A repak that can actually decompress everything installed."""
    return os.environ.get("MTMI_REPAK_OODLE") or str(REPAK)


def paks_shipping(entry: str) -> list[Path]:
    """Every pak carrying this asset, in MOUNT ORDER (filename, case-fold)."""
    out = []
    for pak in sorted(GAME_PAKDIR.glob("*.pak"), key=lambda p: p.name.lower()):
        if pak.name.lower().startswith("motortown-window"):
            continue
        r = subprocess.run([repak_exe(), "list", str(pak)],
                           capture_output=True, text=True)
        if r.returncode == 0 and any(
                l.strip().replace("\\", "/") == entry for l in r.stdout.splitlines()):
            out.append(pak)
    return out


def extract(pak: Path, entry: str, dest: Path) -> Path | None:
    dest.mkdir(parents=True, exist_ok=True)
    stem = entry.rsplit(".", 1)[0]
    cmd = [repak_exe(), "unpack", "-o", str(dest)]
    for ext in (".uasset", ".uexp", ".ubulk"):
        cmd += ["--include", stem + ext]
    cmd.append(str(pak))
    subprocess.run(cmd, capture_output=True, text=True)
    got = dest / entry
    return got if got.is_file() else None


def parents(asset: Path) -> list[str]:
    """The parent table names this composite registers."""
    r = subprocess.run([str(INJECTOR), "inspect-imports", "--cell", str(asset),
                        "--mappings", str(MAPPINGS)], capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r"\s*-\d+:\s+(\S+)\s+\(class=DataTable,", line)
        if m:
            out.append(m.group(1))
    return sorted(set(out))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asset", help="Content-relative, e.g. DataAsset/VehicleParts/VehicleParts.uasset")
    ap.add_argument("--base", help="pak filename substring whose copy to build on")
    ap.add_argument("--apply", help="staging Content dir to write the merged asset into")
    args = ap.parse_args()

    entry = f"MotorTown/Content/{args.asset}"
    work = Path(WORK_DIR) / "composite_merge"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)

    found = paks_shipping(entry)
    if not found:
        print(f"  no installed pak ships {args.asset}")
        return 1

    print(f"  {args.asset}\n  shipped by {len(found)} pak(s), in mount order "
          f"(last one wins):\n")
    table: dict[str, list[str]] = {}
    van = GAME_CONTENT / args.asset
    if van.is_file():
        table["(vanilla)"] = parents(van)
    for i, pak in enumerate(found):
        got = extract(pak, entry, work / str(i))
        table[pak.name] = parents(got) if got else []
        mark = "  <- WINS" if i == len(found) - 1 else ""
        note = "" if got else "   (could not extract -- Oodle? see MTMI_REPAK_OODLE)"
        print(f"    {pak.name:52} {len(table[pak.name]):>3} parents{mark}{note}")

    union = sorted({p for ps in table.values() for p in ps})
    winner = found[-1].name
    dropped = sorted(set(union) - set(table.get(winner, [])))
    print(f"\n  union of everyone: {len(union)} parents")
    if dropped:
        print(f"  the winner DROPS {len(dropped)}: {', '.join(dropped)}")
    else:
        print("  the winner drops nothing -- no conflict here")

    for name, ps in table.items():
        missing = sorted(set(union) - set(ps))
        if missing:
            print(f"    {name:52} missing {', '.join(missing)}")

    if not args.base:
        print("\n  report only. Re-run with --base <pak substring> --apply <dir> to merge.")
        return 0

    match = [p for p in found if args.base.lower() in p.name.lower()]
    if not match:
        print(f"\n  --base {args.base!r} matched no pak that ships this asset", file=sys.stderr)
        return 1
    base_pak = match[-1]
    src = extract(base_pak, entry, work / "base")
    if not src:
        print(f"\n  could not extract from {base_pak.name}", file=sys.stderr)
        return 1
    print(f"\n  base: {base_pak.name}")

    if not args.apply:
        print("  --apply not given, nothing written")
        return 0
    dst_dir = Path(args.apply) / Path(args.asset).parent
    dst_dir.mkdir(parents=True, exist_ok=True)
    stem = src.with_suffix("")
    for ext in (".uasset", ".uexp", ".ubulk"):
        s = Path(str(stem) + ext)
        if s.is_file():
            shutil.copy2(s, dst_dir / s.name)
    staged = dst_dir / src.name

    add = ",".join(f"/Game/{Path(args.asset).parent.as_posix()}/{p}" for p in union)
    r = subprocess.run([str(INJECTOR), "register-parent-tables", "--uasset", str(staged),
                        "--mappings", str(MAPPINGS), "--add", add],
                       capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip():
            print("    " + line.strip())
    print(f"  wrote {staged}")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
