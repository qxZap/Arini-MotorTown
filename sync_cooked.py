#!/usr/bin/env python3
"""sync_cooked.py -- refresh staged assets from the editor's cooked output.

    python sync_cooked.py <mod content dir> [--dry-run]

WHY THIS EXISTS
    copy_asset_to_mod only runs for assets a MESH references, pulled in while
    walking the scene export. Anything staged by another route is copied once
    and then never looked at again -- the in-game world map is the case in
    point: T_WorldMap_Jeju is not referenced by any mesh, so it sat in staging
    from 25 August and shipped in every build after, however many times it was
    re-cooked.

    So: for everything ALREADY staged, if the cooked output holds a different
    copy, take the cooked one. Re-cooking anything is then enough to ship it,
    which is the rule the pipeline already claims for meshes and should not
    have had an exception to.

WHAT IT WILL NOT DO
    It never ADDS files. Staging is the list of what this mod ships, decided
    by the mesh walk and the prune; this step only keeps those files current.
    Adding on sight would drag in every asset the editor happens to have
    cooked.

    It compares CONTENT, not timestamps. A re-cook rewrites mtimes on
    everything it touches, so by timestamp 525 files looked stale here when
    exactly 4 had actually changed.
"""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

from mt_paths import COOKED_CONTENT


def digest(p: Path) -> str:
    h = hashlib.sha1()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pipeline_owned() -> set[str]:
    """Assets the BUILD writes, which cooked output must never overwrite.

    build_materials.py points MI_DC_DirtRoad and friends at our derived
    physical materials so snow and dirt dig. The cooked copies still point at
    the vanilla ones, so syncing them would silently undo that -- the material
    would look correct in the editor and the ruts would just stop happening.
    """
    import json
    out: set[str] = set()
    p = Path("materials.json")
    if not p.is_file():
        return out
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return out
    for e in cfg.get("derived") or []:
        m = (e.get("material") or {}).get("existing")
        if m:
            out.add(m)
        t = (e.get("physmat") or {}).get("to")
        if t:
            out.add(t)
    for e in cfg.get("particle_variants") or []:
        if e.get("to"):
            out.add(e["to"])
    return out


def sync(content: Path, cooked: Path, dry: bool = False) -> tuple[int, int]:
    owned = pipeline_owned()
    changed, checked = [], 0
    for p in sorted(content.rglob("*")):
        if not p.is_file():
            continue
        c = cooked / p.relative_to(content)
        if not c.is_file():
            continue
        if p.relative_to(content).with_suffix("").as_posix() in owned:
            continue          # the build owns this one
        checked += 1
        # Cheap reject first: a different size cannot be the same content, and
        # hashing 167 MB of texture bulk on every build for nothing is rude.
        if c.stat().st_size == p.stat().st_size and digest(c) == digest(p):
            continue
        changed.append((p, c))
    for p, c in changed:
        rel = p.relative_to(content).as_posix()
        size = c.stat().st_size / 1048576
        print(f"    {rel}  ({size:.2f} MB)")
        if not dry:
            shutil.copy2(c, p)
    return len(changed), checked


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    content = Path(sys.argv[1])
    if not content.is_dir():
        print(f"  no content dir at {content}", file=sys.stderr)
        return 1
    if not COOKED_CONTENT:
        print("  MTMI_COOKED_CONTENT not set -- nothing to sync")
        return 0
    cooked = Path(COOKED_CONTENT)
    if not cooked.is_dir():
        print(f"  cooked output not found at {cooked} -- nothing to sync")
        return 0
    n, checked = sync(content, cooked, "--dry-run" in sys.argv)
    verb = "would refresh" if "--dry-run" in sys.argv else "refreshed"
    print(f"  {verb} {n} of {checked} staged file(s) from cooked output")
    return 0


def _selfcheck() -> None:
    """Changed content is taken; identical content is left alone even when the
    cooked copy is newer; a cooked-only file is never added."""
    import os, tempfile, time
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        st, ck = root / "stage", root / "cooked"
        for d in (st, ck):
            (d / "sub").mkdir(parents=True)
        (st / "sub" / "changed.uasset").write_bytes(b"old")
        (ck / "sub" / "changed.uasset").write_bytes(b"new")
        (st / "sub" / "same.uasset").write_bytes(b"same")
        (ck / "sub" / "same.uasset").write_bytes(b"same")
        os.utime(ck / "sub" / "same.uasset", (time.time() + 999, time.time() + 999))
        (ck / "sub" / "extra.uasset").write_bytes(b"not ours")
        n, _ = sync(st, ck)
        assert n == 1, n
        # a pipeline-owned asset is never taken from cooked
        import json as _j
        (root/"materials.json").write_text(_j.dumps(
            {"derived": [{"material": {"existing": "sub/changed"}}]}), encoding="utf-8")
        cwd = os.getcwd(); os.chdir(root)
        try:
            (st/"sub"/"changed.uasset").write_bytes(b"built")
            n2, _ = sync(st, ck)
        finally:
            os.chdir(cwd)
        assert n2 == 0, f"pipeline-owned asset was overwritten ({n2})"
        assert (st/"sub"/"changed.uasset").read_bytes() == b"built"
        assert (st / "sub" / "same.uasset").read_bytes() == b"same"
        assert not (st / "sub" / "extra.uasset").exists(), "must never add files"
        print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        raise SystemExit(main())
