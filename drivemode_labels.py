#!/usr/bin/env python3
"""drivemode_labels.py -- label transfer-case modes vanilla never anticipated.

    python drivemode_labels.py <mod content dir> [--dry-run]

WHY THIS EXISTS
    The transfer-case readout -- the one the drive-mode key cycles -- is not
    an enum. Motor Town builds a key at runtime from the number of driven
    wheels and the range, "<n>H" / "<n>L" / "<n>L-Lock", and looks it up in
    DataAsset/StringTables/Vehicle. The strings are not in the executable at
    all: "4L-Lock" appears there zero times, so the table IS the vocabulary.

    Vanilla defines RWD, 2WD, 4H, 4L, 4L-Lock, 6L and 6L-Lock, because no
    vanilla truck drives more than six wheels. Put an 8x8 in the game and it
    asks for a key nobody ever wrote, so the readout comes up blank -- which
    reads as a missing string table, and is one, just not a missing FILE.

WHAT IT DOES
    Extends the EFFECTIVE Vehicle string table -- the copy the game actually
    loads -- with the higher-axle combinations, in place. The package path and
    namespace are the lookup, so they must not move; this is why it uses
    `extend-stringtable` rather than `make-stringtable`, which clones a table
    under a NEW namespace and clears it.

    Existing keys are never overwritten. Key and value are identical here,
    which is how vanilla writes them: the readout shows the key itself.

WHAT IT DOES NOT DO
    Nothing unless MTMI_DRIVEMODE_LABELS=1, and nothing useful in a layer that
    does not mount last -- a table that loses the load order is not the one the
    game reads.

    It cannot verify the game asks for these exact keys. The naming follows
    vanilla's own pattern and the entries are inert if unused: an unrequested
    key costs a few bytes and changes nothing. A key we guessed WRONG would
    still read blank, so if a mode is still unlabelled, dump what the vehicle
    reports and add that spelling here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mt_paths import MAPPINGS, _cfg, effective_asset

REL = "DataAsset/StringTables/Vehicle.uasset"
SUBDIR = "DataAsset/StringTables"
INJECTOR = Path("MTBPInjector/bin/Release/net8.0/MTBPInjector.exe")

# Vanilla stops at six driven wheels. Everything here follows its spelling
# exactly -- "4L-Lock", not "4L Lock" or "4LLock" -- because the key is
# compared literally.
LABELS: dict[str, str] = {}
for _n in (2, 4, 6, 8, 10):
    for _r in ("H", "L"):
        LABELS[f"{_n}{_r}"] = f"{_n}{_r}"
        LABELS[f"{_n}{_r}-Lock"] = f"{_n}{_r}-Lock"
LABELS["AWD"] = "AWD"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    if (_cfg("MTMI_DRIVEMODE_LABELS", "") or "").strip() != "1":
        return 0
    content = Path(sys.argv[1])
    dry = "--dry-run" in sys.argv

    src = Path(effective_asset(REL))
    if not src.is_file():
        print(f"  drive-mode labels: {REL} not found -- skipped", file=sys.stderr)
        return 0
    if dry:
        print(f"  would extend {src.name} with {len(LABELS)} label(s)")
        return 0
    if not INJECTOR.is_file():
        print("  injector not built -- drive-mode labels skipped", file=sys.stderr)
        return 1

    dst_dir = content / SUBDIR
    dst_dir.mkdir(parents=True, exist_ok=True)
    # Sidecars travel with the asset; UAssetAPI needs the .uexp to read it.
    stem = src.with_suffix("")
    for ext in (".uasset", ".uexp", ".ubulk"):
        s = Path(str(stem) + ext)
        if s.is_file():
            shutil.copy2(s, dst_dir / s.name)
    staged = dst_dir / src.name

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as fh:
        json.dump(LABELS, fh)
        entries = fh.name
    try:
        r = subprocess.run([str(INJECTOR), "extend-stringtable",
                            "--src", str(staged), "--output", str(staged),
                            "--mappings", str(MAPPINGS), "--entries", entries],
                           capture_output=True, text=True)
    finally:
        Path(entries).unlink(missing_ok=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.strip() and "already present" not in line:
            print("    " + line.strip())
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
