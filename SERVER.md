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
| `MTMI_SKIP_DEALERS=1` | the 24 dealer spawn points are still reverse-engineered *unversioned* blobs the server cook cannot read. See section 7. |
| `MTMI_NO_FOLIAGE=1` | see section 5. **Not** `MTMI_SKIP_FOLIAGE` — that one is set to 1 on *every* build and means something else entirely: "drop `fol_*` from the mesh stage", because foliage ships as instanced cells in step [4]. Reading it to gate step [4] would switch foliage off for the **client** too, which is how the island lost its foliage once before. |
| `MTMI_SERVER_CVARS=1` | ships `wp.Runtime.BlockOnSlowStreaming=0` and `wp.Runtime.MaxLoadingStreamingCells=16` in the server ini only. Blocking on slow streaming has no place on a server and every reason to stay on a client. |

---

## 5. Foliage, and why the server ships cells but not instances

Two separate problems live here. They were tangled together for a long time and
they have different answers.

### 5a. The cells must exist on both sides, or clients drop

**A client and a server must register the same world-partition cells.** When a
client streams a cell in and makes it visible, it tells the server so. A server
that has never heard of that cell package has no good answer, and the client
does not degrade gracefully -- it drops with *"Your connection to the host has
been lost"*.

Shipping no foliage at all left the server missing **2,511 of the client's
2,565 cells**, and no player could stay on the island. Sessions lasted 1m47s,
38s, 29s, 11s, 3s -- shrinking as the player's saved spawn point crept onto the
island, which made it look like a teleport bug rather than a proximity one.

So the server registers **every** foliage cell -- same names, same bounds, same
components -- with **zero instances in them** (`MTMI_FOLIAGE_NO_INSTANCES=1`).
Cell bounds are still computed from the real instance positions, so both sides
describe the same piece of world. Cost measured: tick-start to `Creating
Session` goes 15 s -> 23 s, peak RAM 6.79 -> 6.94 GB. Effectively free.

The same class of bug bites in the other direction, and worse: an asset only the
**server** has is one it can reference in something it replicates, and a client
that cannot resolve it drops. Two of those shipped undetected -- the Vista GTR
(`Cars/Models/Vista/V8C52`) and a bus mesh -- because
`check_server_parity.py` only ever compared client-minus-server. It checks both
directions now.

### 5b. The instances are what keep a foliage server off Steam

**The gate is time on the game thread, not memory.** Server-side world-partition
streaming is disabled -- UE's default for a server, baked at cook time, not
readable from a cvar -- so every cell loads at once and the server builds a
Chaos body for every colliding instance before it registers with Steam. That
blocks the thread past the Steam game-server logon timeout, and MT never
re-logs-on: it only retries `CreateSession`, which then fails forever against a
dead logon.

| build | tick start -> `Creating Session` | create call | peak RAM | result |
|---|---|---|---|---|
| vanilla, no island | 15 s | 2 s | 6.79 GB | `Session created!` |
| island, no foliage at all | 13-24 s | 1-2 s | ~7 GB | lists, but clients drop (5a) |
| island, empty foliage cells | 23 s | 1 s | 6.94 GB | `Session created!` |
| island, all 3.49M instances | 143 s | 135 s, then fails | 17.5 GB | `Failed to create session on Steam` |

The tell that this is a *dead logon* rather than ongoing work: the failed server
then sits at **0.9% of one core**, completely idle, and every 30-second retry
still fails. Nothing is stuck. Steam is simply gone.

The cost is **1,969,202 colliding instances** -- trees and bushes, one body
each. The other 1,524,740 (grass, corn, wheat) are cooked `NoCollision` and have
no bodies at all.

### Things that do NOT fix it

- **`wp.Runtime.EnableServerStreaming=1`** (and `...Out`, and
  `UpdateStreamingStateTimeLimit`), whether set in
  `Saved/Config/WindowsServer/Engine.ini` under `[SystemSettings]` or passed as
  `-dpcvars=`. Measured against vanilla with no island pak: **6792 MB with it
  off, 6764 MB with it on.** A flat line. UE resolves server streaming into
  `bIsServerStreamingEnabled` during the cook and MT cooked it off -- the name
  does not even appear in `Jeju_World.umap`.
- **Lowering the Landscape grid loading range.** Loading ranges are never
  consulted when streaming is off.
- **Waiting.** RAM is flat for 12+ minutes and the retries never succeed.

### What this costs

Winches do not attach to trees -- there is no body to trace against. Ground,
buildings and props all winch normally. Whether tree collision can be afforded
inside the Steam deadline is a question of how many bodies fit in the budget
between 23 s and 143 s; `MTMI_FOLIAGE_COLLIDABLE_ONLY=1` ships the 1.97M
colliding instances and nothing else, and is the next thing to measure.

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
| **dealers** | 24 `MTDealerVehicleSpawnPoint` actors omitted server-side. Still unversioned blobs; fixing them needs a real one to model and there is none in any cell — they live in the persistent map, a 25-minute parse. |
| **foliage** | Section 5. Client-side only. |
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
