#!/usr/bin/env python3
"""make_release.py -- zip the deployed paks into per-mod downloads.

One zip per audience, so a player never has to reason about which of six
paks applies to them. Compat zips that have an MTNet variant carry two
folders rather than two zips: same decision, one download.
"""
from __future__ import annotations
import shutil, zipfile
from pathlib import Path
from mt_paths import GAME_PAKDIR

OUT = Path.home() / "Downloads" / "Arini"
BASE = "zzzz_Arini_P.pak"

INSTALL = """HOW TO INSTALL
--------------
1. Find your Motor Town paks folder:
     ...\steamapps\common\Motor Town\MotorTown\Content\Paks
2. Copy the .pak file(s) from this zip into it.
3. That's it. Launch the game.

To uninstall, delete the .pak files you copied.

DO NOT RENAME THE FILES. Unreal mounts paks in filename order and the last
one wins, so the leading z's are what make a compatibility patch load after
the mod it patches. Rename one and it silently stops working -- everything
loads, nothing errors, and the changes just are not there.
"""

RELEASES = [
    dict(zip_name="Arini.zip", title="Arini - the island",
         body="""The island itself. This is the only file you need if you do not
run Capitalist Economy or Proxy's Oversized Cargo.

If you DO run either of those, install this AND the matching compatibility
patch from its own download. The compat patches do not contain the island --
they are a few hundred kilobytes of economy data that sits on top of it.""",
         folders={None: [BASE]}),

    dict(zip_name="Arini_CapitalistEconomy_Compat.zip",
         title="Arini - Capitalist Economy compatibility",
         body="""Requires the Arini island and Capitalist Economy.

Arini's cargo is priced against Capitalist Economy's own tables rather than
the vanilla ones, so the two economies agree instead of overwriting each
other.

  Default\    use this one
  MTNet\      use this one INSTEAD if you also run MTNet

The MTNet folder is not a different economy -- it is the same patch, built to
keep MTNet's reverse-proxy endpoints working. MTNet's config file would
otherwise replace ours and switch off the island's fog. Install ONE of the
two, never both.""",
         folders={"Default": ["zzzz_Arini_zCapEcon_P.pak"],
                  "MTNet":   ["zzzzz_Arini_CapEconMTNet_P.pak"]}),

    dict(zip_name="Arini_ProxyOversizedCargo_Compat.zip",
         title="Arini - Proxy's Oversized Cargo compatibility",
         body="""Requires the Arini island and Proxy's Oversized Cargo.

Adds 79 of Proxy's cargos to the island, priced for it, and opens a trade
route in both directions: Jeju's construction sites supply Galati Port, and
Braila Port produces 29 loads that Jeju's sites, mines and farms ask for and
nothing else in the game makes.""",
         folders={None: ["zzzz_Arini_zProxy_P.pak"]}),

    dict(zip_name="Arini_CapEcon_Proxy_Compat.zip",
         title="Arini - Capitalist Economy + Proxy compatibility",
         body="""Requires the Arini island, Capitalist Economy AND Proxy's Oversized
Cargo. Use this INSTEAD of the two single-mod patches, not alongside them.

  Default\    use this one
  MTNet\      use this one INSTEAD if you also run MTNet

Install ONE folder's pak, never both.""",
         folders={"Default": ["zzzz_Arini_zProxyCapEcon_P.pak"],
                  "MTNet":   ["zzzzz_Arini_ProxyCapEconMTNet_P.pak"]}),
]


def readme(r) -> str:
    return f"{r['title']}\n{'=' * len(r['title'])}\n\n{r['body']}\n\n{INSTALL}"


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    for r in RELEASES:
        z = OUT / r["zip_name"]
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", readme(r))
            for folder, paks in r["folders"].items():
                for pak in paks:
                    src = Path(GAME_PAKDIR) / pak
                    if not src.is_file():
                        print(f"  MISSING {pak}"); return 1
                    zf.write(src, f"{folder}/{pak}" if folder else pak)
        mb = z.stat().st_size / 1048576
        inner = ", ".join(f"{k or '.'}/{v[0]}" for k, v in r["folders"].items())
        print(f"  {z.name:<44} {mb:>8.1f} MB   {inner}")
    print(f"\n  -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
