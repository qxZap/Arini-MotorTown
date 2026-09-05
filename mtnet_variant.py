#!/usr/bin/env python3
"""mtnet_variant.py -- build an MTNet compat from its non-MTNet twin.

    python mtnet_variant.py <base layer> <mtnet layer>

WHY THIS IS NOT A BUILD
    The two differ by ONE FILE. MTNet changes no cargo, no recipe and no
    delivery point -- it adds reverse-proxy endpoints to UserEngine.ini, and
    the compat exists so those survive alongside our fog switch. Regenerating
    the cargo tables and 34 blueprint classes to change an ini is ten minutes
    spent reproducing bytes we already have.

    So: copy the twin's staged tree, rewrite the ini with MTNet merged in,
    and pack under the zzzzzz_ prefix that sorts past ZZZZMTNet_P.
"""
from __future__ import annotations
import os, shutil, subprocess, sys
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
    base_layer, mtnet_layer = sys.argv[1], sys.argv[2]
    _, layers = load()
    src = Path(layers[base_layer]["mod_name"])
    dst = Path(layers[mtnet_layer]["mod_name"])
    if not src.is_dir():
        print(f"  {src} not staged -- build {base_layer} first", file=sys.stderr)
        return 1

    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    n = sum(1 for _ in dst.rglob("*") if _.is_file())
    print(f"  copied {src} -> {dst} ({n} files)")

    e = env_for(mtnet_layer)
    r = subprocess.run([sys.executable, "merge_config.py"], env=e,
                       capture_output=True, text=True)
    print("  " + (r.stdout.strip().splitlines() or ["merge_config: no output"])[-1])
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr); return 1

    r = subprocess.run(["cmd", "/c", str(Path("modp.bat").resolve()), e["MTMI_MOD_NAME"]],
                       env=e, cwd=str(Path.cwd()), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr, file=sys.stderr); return 1
    print(f"  packed {e['MTMI_PAK_PREFIX']}{e['MTMI_MOD_NAME']}.pak")

    r = subprocess.run([sys.executable, "verify_build.py"], env=e,
                       capture_output=True, text=True)
    tail = [l for l in r.stdout.splitlines() if "INTEGRITY" in l or "[FAIL]" in l]
    print("  " + "\n  ".join(tail[-4:]))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
