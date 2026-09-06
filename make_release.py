#!/usr/bin/env python3
"""make_release.py -- zip the deployed paks into per-mod downloads.

One zip per audience, so a player never has to reason about which of six
paks applies to them. Compat zips that have an MTNet variant carry two
folders rather than two zips: same decision, one download.
"""
from __future__ import annotations
import shutil, zipfile
from pathlib import Path
from mt_paths import GAME_PAKDIR, _cfg

OUT = Path.home() / "Downloads" / "Arini"

# The server pak is deployed into the DEDICATED SERVER install, not the game's,
# because the two are separate targets with separate Paks folders.
SERVER_PAKDIR = (Path(_cfg("MT_SERVER_DIR", "") or "") / "MotorTown" / "Content" / "Paks")
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

    dict(zip_name="Arini_DedicatedServer.zip",
         title="Arini - dedicated server",
         from_server=True,
         body="""FOR SERVER OWNERS ONLY. This is NOT the pak players install.

A dedicated server and a game client need DIFFERENT builds of the island -- the
game cooks its content twice and the two are not interchangeable. Putting the
player pak on a server produces a server that starts, never appears in any
listing, and never tells you why.

  server  ->  this zip, into the dedicated server install
  players ->  Arini.zip, as normal

Everyone connecting still needs the player pak. Install it as usual.

INSTALL
  1. Copy zzzz_Arini_Server_P.pak into:
       ...\Motor Town Behind The Wheel - Dedicated Server\MotorTown\Content\Paks
  2. Start the server as you normally do.
  3. In MotorTown\Saved\ServerLog\<timestamp>.log you want to see:
       Session created!
       [Session] URL: steam.<id>:7777
     If the log stops at "Game Tick Started" the server is up but will never
     list -- that is the symptom of a wrong pak, not a crash.

WITH ECONOMY MODS
  Install the mods, then the compat, in filename order (last one wins):
       X_qxZap_CapitalistEconomy*.pak      the mod
       zzProxysOversizeCargoV4-*.pak       the mod
       zzzz_Arini_Server_P.pak             the island
       zzzz_Arini_zProxyCapEcon_P.pak      the compat, from its own download
  Use the NON-MTNet compat on a server.

WHAT THIS BUILD LEAVES OUT, DELIBERATELY
  Foliage. A server with nobody connected has no streaming source, so it would
  load every foliage cell at once -- about 17 GB -- and never finish starting.
  Foliage is not replicated, so it costs you nothing: players carry it in their
  own pak and both see and drive into it.

  The 24 vehicle dealership spawn points. Vanilla dealerships are unaffected.""",
         folders={None: ["zzzz_Arini_Server_P.pak"]}),
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
                    root = SERVER_PAKDIR if r.get("from_server") else Path(GAME_PAKDIR)
                    src = root / pak
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
