#!/usr/bin/env python3
"""repack_layer.py -- regenerate a layer's config and repack it.

    python repack_layer.py <layer> [<layer> ...]

For a change that touches only what merge_config writes. The staged tree is
already correct, so rebuilding the cargo tables and 34 blueprint classes to
change a console variable is minutes spent reproducing bytes we have.
"""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path
from mods import load


def env_for(layer: str) -> dict[str, str]:
    mods, layers = load()
    l = layers[layer]
    e = dict(os.environ)
    e["MTMI_LAYER"] = layer
    e["MTMI_MOD_NAME"] = l["mod_name"]
    e["MTMI_PAK_PREFIX"] = l.get("pak_prefix", "zzzz_")
    skip = list(l.get("skip") or []) + [k for k, m in mods.items() if m.get("always_skip")]
    e["MTMI_EXCLUDE_PAKS"] = ",".join(
        p for k in skip for p in (mods.get(k) or {}).get("match") or [])
    return e


def main() -> int:
    _, layers = load()
    rc = 0
    for layer in sys.argv[1:]:
        if layer not in layers:
            print(f"  no layer '{layer}'", file=sys.stderr); rc = 1; continue
        e = env_for(layer)
        stage = Path(e["MTMI_MOD_NAME"])
        if not stage.is_dir():
            print(f"  {layer}: {stage} not staged -- needs a real build"); rc = 1; continue
        print(f"  === {layer} -> {e['MTMI_PAK_PREFIX']}{e['MTMI_MOD_NAME']}.pak ===")
        for step in (["merge_config.py"], ):
            r = subprocess.run([sys.executable] + step, env=e, capture_output=True, text=True)
            tail = [l for l in r.stdout.splitlines() if l.strip()]
            print("    " + (tail[-1].strip() if tail else "(no output)"))
            if r.returncode:
                print(r.stderr, file=sys.stderr); rc = 1
        r = subprocess.run(["cmd", "/c", str(Path("modp.bat").resolve()), e["MTMI_MOD_NAME"]],
                           env=e, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout + r.stderr, file=sys.stderr); rc = 1; continue
        r = subprocess.run([sys.executable, "verify_build.py"], env=e,
                           capture_output=True, text=True)
        for l in r.stdout.splitlines():
            if "INTEGRITY" in l or "[FAIL]" in l:
                print("    " + l.strip())
        rc = rc or r.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
