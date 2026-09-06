# Arini on a dedicated server

Everything needed to build, ship and run the island on a Motor Town dedicated
server. Written for whoever picks this up next, human or agent.

---

## 1. The one thing to understand first

**Motor Town cooks its content twice, and the two cooks are not interchangeable.**

|                        | client                     | dedicated server              |
|------------------------|----------------------------|-------------------------------|
| pak                    | `MotorTown-Windows.pak`    | `MotorTown-WindowsServer.pak` |
| `Jeju_World.uexp`      | 290 MB                     | 371 MB                        |
| world-partition cells  | 11,771 entries             | 11,476 entries                |
| property serialization | **unversioned**            | **versioned**                 |

Unversioned means property names and types are absent from the file and
resolved by index through the `.usmap` — that is what the whole `mappings/`
mechanism exists for. Versioned means every property carries its name and type
inline, which is why the same blueprint is 5,857 bytes server-side and 759
client-side.

Consequences, all learned the hard way:

- A **client pak dropped on a server** loads far enough to log
  `World loading completed`, then never creates its Steam session. The server
  stays up forever and appears in no listing. It does not crash and it does not
  tell you why.
- Anything this toolchain **constructs** must be written in whichever format the
  target package uses. See section 6.
- **Client and server content must match.** A client that arrives somewhere the
  server is missing actors does not error — it hangs, or drops with
  "Your connection to the host has been lost".

---

## 2. Prerequisites

1. **The dedicated server installed** via Steam ("Motor Town Behind The Wheel -
   Dedicated Server"). The tooling reads its pak and deploys into its
   `MotorTown/Content/Paks`.

2. **A WindowsServer cook of the addon.** The editor's Platforms menu will not
   offer it for a content-only project, so run the commandlet:

       "<UE_5.5>\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"
         "<project>\MTMapAddon.uproject"
         -run=Cook -TargetPlatform=WindowsServer -unversioned -stdout -unattended

   - `-TargetPlatform=WindowsServer` is the whole point; `Windows` gives you the
     client cook you already have.
   - `-unversioned` must stay — it means unversioned *cooked content*, not
     unversioned properties, and the pipeline depends on it.
   - **Close the editor first**, or the cook fails on file locks.
   - Output lands in `Saved/Cooked/WindowsServer/`, beside `Windows/`. Nothing
     is overwritten. Expect ~1.3 GB against the client's ~5.1 GB — the server
     keeps collision and gameplay data and drops the rendering payload.

3. **A server-side vanilla extract**, once per game update:

       MT_GAME_DIR=<dedicated server dir>
       MTMI_GAME_CONTENT=<repo>/vanilla_extract_server/MotorTown/Content
       python bootstrap_extract.py --full

   ~7.5 GB. `bootstrap_extract` and `mt_paths` both recognise
   `MotorTown-WindowsServer.pak` as a valid base pak.

---

## 3. Building

    build.bat --layer server

That is all. The `server` layer in `mods.json` carries its own environment and
build.bat applies it, so no flags are needed. It deploys into the **dedicated
server's** Paks folder automatically, because deploy follows `MT_GAME_DIR`.

To repack without re-running the ~40-minute injection — after a re-cook, a
material change, or an ini change:

    python repack_layer.py server

---

## 4. Environment variables

Machine paths live in `.env`; the layer's own settings live in `mods.json` and
are applied by build.bat. `${NAME}` inside a layer's `env` block expands from
`.env`, and an unset one is **fatal** — a server build that quietly fell back to
the client cook would produce a pak that looks right and cannot host.

### In `.env` (per machine)

| variable | meaning |
|---|---|
| `MT_SERVER_DIR` | the dedicated server install directory |
| `MTMI_COOKED_CONTENT_SERVER` | `Saved/Cooked/WindowsServer/<project>/Content` |

### Set by the `server` layer — do not set these by hand

| variable | why |
|---|---|
| `MT_GAME_DIR` | `${MT_SERVER_DIR}` — also the deploy target |
| `MTMI_GAME_CONTENT` | the server-side vanilla extract |
| `MTMI_COOKED_CONTENT` | `${MTMI_COOKED_CONTENT_SERVER}` |
| `MTMI_FOLIAGE_COLLIDABLE_ONLY=1` | ships only foliage that collides -- a server renders nothing, so grass, corn and wheat are pure cost. It EMPTIES those meshes and keeps their cells; removing them would delete grass-only tiles and break cell parity. See section 5a. |
| `MTMI_SERVER_STREAMING=1` | writes `ServerStreamingMode=Enabled` into the map so the server streams cells instead of holding the whole world. This is what makes tree collision affordable at all. See section 5b. |
| `MTMI_SERVER_CVARS=1` | ships `wp.Runtime.BlockOnSlowStreaming=0` and `wp.Runtime.MaxLoadingStreamingCells=16` in the server ini only. Blocking on slow streaming has no place on a server and every reason to stay on a client. |

---

## 5. Foliage on the server, and the flag that makes it possible

The island ships **all of its tree and bush collision** to the dedicated server,
and the server starts in five seconds on 1.9 GB. Getting there took unpicking
two separate problems that looked like one.

### 5a. Both sides must register the same cells

**A client and a server must agree on which world-partition cells exist.** When
a client streams a cell in and makes it visible it tells the server so, and a
server that has never heard of that cell package does not degrade gracefully --
the client drops with *"Your connection to the host has been lost"*.

Shipping no foliage left the server missing **2,511 of the client's 2,565
cells**, and nobody could stay on the island. Sessions ran 1m47s, 38s, 29s,
11s, 3s -- and the shrinking was the clue: the player's saved spawn point was
creeping onto Arini, so a proximity problem looked like a teleport bug.

`MTMI_FOLIAGE_COLLIDABLE_ONLY=1` must therefore **empty** the collision-free
meshes rather than remove them. Removing them deleted every tile holding
nothing but grass -- 2,565 cells became 2,407 -- and reintroduced exactly this
fault. It also empties them at write time, so cell bounds are still computed
from the real instance positions.

The mirror case is worse and shipped twice undetected: an asset only the
**server** has is one it can reference in something it replicates, and a client
that cannot resolve it drops. The Vista GTR (`Cars/Models/Vista/V8C52`) and a
bus mesh both went out server-only, because a repack reuses whatever is already
staged and the client's staging was older than the server's.
`check_server_parity.py` compared only client-minus-server and could not see
either. It checks both directions now, and the server-only direction is the one
that disconnects people.

### 5b. Server streaming, written into the map

A dedicated server loads **every** cell at once unless world-partition server
streaming is on. That is what made foliage unaffordable: one Chaos body per
colliding instance, 1,969,202 of them, built on the game thread before the
server registers with Steam. It blocks long enough that the Steam game-server
logon expires, and MT never re-logs-on -- it only retries `CreateSession`,
which then fails forever against a dead logon. The tell is that the failed
server afterwards idles at **0.9% of one core** and still fails every retry.
Nothing is stuck; Steam is simply gone.

`UWorldPartition::ServerStreamingMode` is absent from `Jeju_World.umap`, so it
sits at `ProjectDefault`, which is supposed to defer to
`wp.Runtime.EnableServerStreaming`. **On this build that cvar does nothing** --
measured flat, with and without the island pak, set through `[SystemSettings]`
in `Saved/Config/WindowsServer/Engine.ini` and through `-dpcvars=`. Why it is
inert is still unknown. Writing the enum onto the WorldPartition export leaves
nothing to defer to, and that works:

    MTMI_SERVER_STREAMING=1     -> build.bat step [5e3]
    MTBPInjector set-server-streaming --mode Enabled --out-mode Enabled

Measured, same machine, same foliage:

| build | tree bodies placed | tick -> `Creating Session` | peak RAM | result |
|---|---|---|---|---|
| vanilla, no island | 0 | 15 s | 6.79 GB | lists |
| island, no foliage at all | 0 | 13-24 s | ~7 GB | lists, but clients drop (5a) |
| island, empty foliage cells | 0 | 23 s | 6.95 GB | lists, no tree winching |
| island, colliding foliage | 1.96M | 117 s | 17.4 GB | **never lists** |
| island, all foliage | 1.97M | 143 s | 17.5 GB | **never lists** |
| **colliding foliage + server streaming** | **1.96M** | **5 s** | **1.93 GB** | **lists, winches work** |

Note the last row is faster and smaller than **vanilla**: the server is no
longer holding Jeju either.

### Dead ends, measured

- **`MTMI_FOLIAGE_COLLIDABLE_ONLY` as a way to fit under the Steam deadline.**
  It drops the 1,524,740 `NoCollision` instances, which cost ~26 s of instance
  creation but have no physics bodies -- 143 s becomes 117 s and still fails.
  It is worth setting on a server anyway (a server renders nothing), just not
  for this reason.
- **Lowering the Landscape grid loading range.** Loading ranges are never
  consulted while server streaming is off.
- **Waiting.** RAM is flat for 12+ minutes and the retries never succeed.

### What to watch

Server streaming is engine behaviour MT's own server has never shipped with. It
applies to **vanilla Jeju as well as the island**, so AI traffic, NPCs and
deliveries on the mainland are the things to watch after a game update.
`--out-mode Enabled` also unloads cells behind a player; if anything stops
responding when driving fast, drop back to `--out-mode Disabled` and keep only
load-in.

---

## 6. What had to be fixed to make this work at all

Recorded because every one of these fails silently.

**Versioned writing.** Nothing the toolchain constructs carried a
`PropertyTypeName`, which a versioned write requires on every property.
`MainSerializer` now derives them, as a pre-pass in `UAsset.Write` — deriving
lazily interns names after the name map is sealed. `verify-typenames` checks
derived against real on an asset that has them: 2,752 properties, zero
mismatches.

**Cloned type names.** An `FName` indexes *its own package's* name map, and type
names are built out of `FName`s. Cloning an export between assets carried the
source's indices, so every property on a cloned blueprint actor read back as
`UnknownPropertyData` with a numeric type. The same pre-pass re-interns them.

**Enum spelling.** A versioned package stores enum values fully qualified
(`EDeliveryCargoType::SmallPackage`); the `.usmap` is inconsistent — native
enums bare, Blueprint enums qualified. Both forms are accepted now; matching one
broke the other. `verify_build.py` normalises the same way.

**Static mesh actors.** Built as hand-written unversioned property blobs, which
the versioned cook reads as garbage. They are now built as typed properties when
the target is versioned. The blob also set `Mobility = Movable`;
`AStaticMeshActor` constructs its root component *Static*, so forcing it Movable
leaves the component disagreeing with its own class — the client tolerates that,
the server hangs on it.

**The delivery points.** The worst one. Step 3 placed all 34; step 5 wrote the
level back through UAssetAPI's typed `LevelExport` path and they were gone. That
path only ever ran on the server — on the client the PersistentLevel does not
parse as a `LevelExport`, so it takes a raw byte patch that preserves
everything. Both targets now use the raw path. The symptom was a client
teleporting to the island and hanging forever, waiting for actors the server
would never send.

**Build ordering.** `MTMI_GAME_CONTENT` is defaulted near the top of build.bat,
and `VANILLA_MAP` and the deploy directory derive from it, long before `--layer`
is parsed. The server build was silently reading the **client** map and
deploying into the **client's** Paks folder. Both are re-derived after the layer
env, with delayed expansion — `%VAR%` inside a parenthesised block resolves at
parse time.

---

## 7. Known gaps

| gap | detail |
|---|---|
| **grass, corn, wheat** | 1,524,740 `NoCollision` instances are not placed server-side. They render on nobody and block nothing. Trees and bushes ARE placed, with collision. |
| **`DataAsset/GameResource`** | the world-map bounds; not staged server-side because the server cook produces no map texture. Map-UI data, no gameplay effect. |
| **compat paks are client builds** | the economy compats shipped to a server are client-cooked. They mount last, so their `Mod*` classes override the server-cooked ones. It works — the server reads unversioned packages fine — but if recipes misbehave, build a `*_server` compat layer. |

---

## 8. Checks

    python verify_build.py            # the pak on its own: 77 checks
    python check_server_parity.py     # the server against the client
    python check_layer_sync.py        # compat paks vs the base

`check_server_parity.py` is the one that matters here. It compares **sets**, not
bytes — the two are separate cooks, so every shared asset legitimately differs
in size and content. It checks for the same cells, the same delivery-point
classes, and crucially that the **map actually places** the same number of
delivery points on both. That last check is what would have caught the lost
delivery points immediately.

---

## 9. Running a server

1. Install the dedicated server from Steam.
2. Copy `zzzz_Arini_Server_P.pak` into
   `...\Motor Town Behind The Wheel - Dedicated Server\MotorTown\Content\Paks\`.
3. Run `RunDedicatedServer.bat`.
4. Watch `MotorTown\Saved\ServerLog\<timestamp>.log`. The only line that matters:

       Session created!
       [Session] URL: steam.<id>:7777 (Steam: Y, Relay: Y, SteamNet: Y)

   Reaching `Game Tick Started` and stopping there means the server is up and
   will never appear in any listing. That is the failure mode — not a crash.

**Players need the client pak too.** Server and client paks are not
interchangeable and both must be installed: the server one on the server, the
client one on every player.

### With economy mods

Install the mods themselves, then our compat, minding filename order — Unreal
mounts paks in filename order and the last one wins:

    X_qxZap_CapitalistEconomy*.pak       the mod
    zzProxysOversizeCargoV4-*.pak        the mod
    zzzz_Arini_Server_P.pak              the island
    zzzz_Arini_zProxyCapEcon_P.pak       our compat - must sort AFTER the island

Use the **non-MTNet** compat on a server.
