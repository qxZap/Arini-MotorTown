#!/usr/bin/env python3
"""server_test.py -- stop the dedicated server, start it, report the session.

    python server_test.py            # restart and watch
    python server_test.py --stop     # just stop it

WHY THIS EXISTS
    "Does the server work" has exactly one answer, and it is not whether the
    process is alive: a dedicated server with a bad pak loads the world, logs
    "World loading completed", ticks, and then never creates its Steam
    session. It stays up forever and never appears in any listing.

    So the test is: does the log reach "Session created!". Vanilla does it in
    about two seconds; a client-cooked pak never does.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from mt_paths import _cfg

SERVER = Path(_cfg("MT_SERVER_DIR", "") or "")
EXE = "MotorTownServer-Win64-Shipping"
BAT = "RunDedicatedServer.bat"
LOGS = "MotorTown/Saved/ServerLog"
GOOD = "Session created!"
# Vanilla reaches it in ~2s; 90s is slack for the island's own load, which is
# where the extra time goes.
WAIT_SECONDS = 150


def stop() -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"Get-Process {EXE} -EA SilentlyContinue | Stop-Process -Force"],
                   capture_output=True)
    time.sleep(3)


def newest_log() -> Path | None:
    d = SERVER / LOGS
    logs = sorted(d.glob("*.log"), key=lambda p: p.stat().st_mtime) if d.is_dir() else []
    return logs[-1] if logs else None


def main() -> int:
    if not SERVER.is_dir():
        print("  MT_SERVER_DIR not set or missing", file=sys.stderr)
        return 2
    before = newest_log()
    stop()
    if "--stop" in sys.argv:
        print("  server stopped")
        return 0

    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f'Start-Process -FilePath "{SERVER / BAT}" -WorkingDirectory "{SERVER}"'],
                   capture_output=True)

    deadline = time.time() + WAIT_SECONDS
    log = None
    while time.time() < deadline:
        time.sleep(3)
        log = newest_log()
        if log is None or (before is not None and log == before):
            continue
        text = log.read_text(encoding="utf-8", errors="replace")
        if GOOD in text:
            print(f"  SESSION CREATED  ({log.name})")
            for line in text.splitlines():
                if "Session" in line or "started" in line:
                    print("    " + line.strip())
            return 0
        if "Game Tick Started" in text:
            # It is up and ticking. Keep waiting -- the session comes after.
            pass
    print(f"  NO SESSION after {WAIT_SECONDS}s -- the server is up but will not list.",
          file=sys.stderr)
    if log is not None:
        print(f"  {log.name}:", file=sys.stderr)
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            print("    " + line.strip(), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
