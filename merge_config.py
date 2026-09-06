#!/usr/bin/env python3
"""
merge_config.py — ship the console variables the map needs, without
throwing away anyone else's.

Some things the map places only render if a renderer feature is switched
on. Local fog volumes are the case in point: ALocalFogVolume is in MT's
build and the actor injects fine, but nothing draws until
r.SupportLocalFogVolumes is set. MT reads those from
MotorTown/Config/UserEngine.ini inside a pak.

The catch is load order. Our pak is prefixed `zzzz_` so it wins, which
means a bare UserEngine.ini of ours REPLACES the one CapitalistEconomy
ships — silently wiping ~18 economy cvars. So this reads every copy in
the load order, merges them in order, then layers ours on top. Other
mods' settings survive; ours win only for the keys we actually set.

    python merge_config.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from mt_paths import MOD_ROOT, effective_pak_entries, _cfg

ENTRY = "MotorTown/Config/UserEngine.ini"
OUT = MOD_ROOT / "MotorTown" / "Config" / "UserEngine.ini"

# What this map needs switched on, as {section: {key: value}}.
# Keep this list to things the map genuinely cannot work without —
# it is layered over every other mod's settings, so each entry here is a
# value we take away from the user.
def _local_fog_volumes() -> int:
    """How many LocalFogVolume actors this build actually ships.

    The source is the SCENE EXPORT, not fog_placements.json. Those are two
    different things and I checked the wrong one: fog_placements.json is a
    hand-authored list that is empty and unused, while ue.py exports the real
    ALocalFogVolume actors to static_meshes_parts/fog_volumes.json, and there
    are eleven of them.
    """
    import json
    p = Path("static_meshes_parts") / "fog_volumes.json"
    if not p.is_file():
        return 0
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return 0
    v = d if isinstance(d, list) else (d.get("fog_volumes") or [])
    return len(v)


def _foliage_cull_scale() -> str:
    """MTMI_FOLIAGE_CULL_SCALE as a cvar value, or "" to ship nothing.

    Two different knobs control how much foliage you see, and they bill to
    different budgets:

        Landscape grid LoadingRange  -> how many cells stay RESIDENT  -> RAM
        instance cull distance       -> how many instances DRAW       -> GPU

    Cull distance is baked into every component in every cell, so changing it
    normally costs a full rebuild. foliage.CullDistanceScale multiplies it at
    runtime instead, which is what makes a quality tier an ini change.

    It must never push the draw distance past the loading range: instances
    still drawing when their cell unloads pop out instead of fading.
    inject_foliage_cells.py checks the baked numbers; this scales them AFTER
    that check, so the headroom has to be left by hand.
    """
    # _cfg, not os.environ: a standalone repack must honour .env the same
    # way build.bat does, or the tier silently does not ship.
    v = (_cfg("MTMI_FOLIAGE_CULL_SCALE", "") or "").strip()
    if not v:
        return ""
    try:
        f = float(v)
    except ValueError:
        print(f"  MTMI_FOLIAGE_CULL_SCALE={v!r} is not a number -- ignored",
              file=sys.stderr)
        return ""
    return "" if f == 1.0 else f"{f:g}"


REQUIRED: dict[str, dict[str, str]] = {
    # Local fog volumes are off by default in a cooked build: the actors load
    # and draw nothing without this. Shipped only when the scene actually has
    # some, because every key here is a value taken away from the player.
    "ConsoleVariables": {
        # r.Nanite.MaxCandidateClusters / MaxVisibleClusters are NOT here any
        # more. They were raised because Nanite's cluster buffers are fixed
        # size -- Epic: "There is no mechanism for dynamically resizing either
        # of these buffers ... typically manifesting as missing or blinking
        # geometry" -- which was the reported "blind areas with no foliage",
        # ~3.5M Nanite foliage instances overflowing them.
        #
        # No foliage is Nanite now, so nothing on this island contributes to
        # those buffers and vanilla's own values cover vanilla's own content.
        # MaxVisibleClusters was 4194304, which is EXACTLY the game's default,
        # so it never did anything at all. MaxCandidateClusters was double the
        # game's 16777216, and Epic states 12 bytes per candidate cluster --
        # about 200 MB of GPU memory handed back.
        #
        # If blind areas or blinking geometry ever return, put
        # "r.Nanite.MaxCandidateClusters": "33554432" back here first.
        # Local fog volumes are off by default in a cooked build: the actors load
        # and draw nothing without this. Only shipped when the scene has some.
        **({"r.SupportLocalFogVolumes": "1"} if _local_fog_volumes() else {}),
        # DEDICATED SERVER only. Entering the island makes the server stream in
        # its cells, and stock settings load 4 at a time while BLOCKING the
        # game thread on slow streaming. The server survives it -- it logs a
        # clean Player Logout -- but it stops answering long enough for the
        # client to time out, so teleporting to Arini drops the connection.
        # Neither belongs in a client build: blocking is what stops a client
        # driving into terrain that has not arrived yet.
        **({"wp.Runtime.BlockOnSlowStreaming": "0",
            "wp.Runtime.MaxLoadingStreamingCells": "16"}
           if _cfg("MTMI_SERVER_CVARS", "") == "1" else {}),
        # Quality tier: multiplies the baked per-instance cull distance so
        # "see twice as far" is an ini change, not a 12-minute rebuild.
        # Absent (or 1) ships nothing -- every key here is a value taken away
        # from the player.
        **({"foliage.CullDistanceScale": _foliage_cull_scale()}
           if _foliage_cull_scale() else {}),
    },
    # r.VolumetricFog is NOT here. It governs the exponential height fog's
    # volumetrics, and this build never touches the height fog -- ue.py
    # exports height_fog.json but nothing applies it. What the island places
    # is eleven LOCAL fog volumes, which are a separate UE 5.5 feature behind
    # the switch above. Pinning a renderer feature we do not use would replace
    # every other mod's UserEngine.ini for nothing.
}


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    """Minimal INI reader. Preserves key spelling; last write wins, which
    is what UE does within a single file."""
    out: dict[str, dict[str, str]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith((";", "#")):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1)
            out.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out.setdefault(section, {})[k.strip()] = v.strip()
    return out


def render(cfg: dict[str, dict[str, str]]) -> str:
    parts = []
    for section, kv in cfg.items():
        if not kv:
            continue
        parts.append(f"[{section}]")
        parts.extend(f"{k} = {v}" for k, v in kv.items())
        parts.append("")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # MTMI_CONFIG_OFF=1 ships no UserEngine.ini whatsoever. Shipping none is
    # not the same as shipping an empty one: our pak loads last, so a file we
    # ship REPLACES every other mod's copy. No file means no override at all,
    # and every other mod keeps its own settings untouched.
    if os.environ.get("MTMI_CONFIG_OFF") == "1":
        if OUT.exists():
            OUT.unlink()
            print(f"  UserEngine.ini: removed (MTMI_CONFIG_OFF=1) -- no override shipped")
        else:
            print(f"  UserEngine.ini: not shipped (MTMI_CONFIG_OFF=1)")
        return 0

    merged: dict[str, dict[str, str]] = {}
    sources = effective_pak_entries(ENTRY)
    for pak_name, path in sources:
        try:
            cfg = parse_ini(path.read_text(encoding="utf-8", errors="replace"))
        except OSError as e:
            print(f"    {pak_name}: unreadable ({e}) — skipped", file=sys.stderr)
            continue
        n = sum(len(v) for v in cfg.values())
        print(f"    inherit {n:3d} setting(s) from {pak_name}")
        for section, kv in cfg.items():
            merged.setdefault(section, {}).update(kv)

    added = []
    for section, kv in REQUIRED.items():
        for k, v in kv.items():
            prev = merged.get(section, {}).get(k)
            if prev != v:
                added.append(f"{k}={v}" + (f" (was {prev})" if prev is not None else ""))
            merged.setdefault(section, {})[k] = v

    total = sum(len(v) for v in merged.values())
    if args.dry_run:
        print(f"  would write {total} setting(s) to {OUT}")
        print(render(merged))
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(merged), encoding="utf-8")
    print(f"  UserEngine.ini: {total} setting(s) from {len(sources)} pak(s) + "
          f"{len(added)} of ours ({', '.join(added) or 'none new'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
