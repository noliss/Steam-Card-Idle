"""Single-game Steam idle worker.

Usage:
    python idle_worker.py <appid> [--dll PATH]
"""

from __future__ import annotations

import argparse
import ctypes
import os
import signal
import sys
import time
from pathlib import Path


def _load_api(dll_path: Path) -> ctypes.CDLL:
    if not dll_path.exists():
        raise FileNotFoundError(f"steam_api DLL not found: {dll_path}")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(dll_path.parent.resolve()))
    os.environ["PATH"] = str(dll_path.parent.resolve()) + os.pathsep + os.environ.get(
        "PATH", ""
    )
    return ctypes.CDLL(str(dll_path))


def run_idle(app_id: int, dll_path: Path) -> int:
    os.environ["SteamAppId"] = str(app_id)
    os.environ["SteamGameId"] = str(app_id)

    work = Path.cwd()
    appid_file = work / "steam_appid.txt"
    heartbeat = work / "heartbeat.txt"
    appid_file.write_text(str(app_id), encoding="ascii")

    api = _load_api(dll_path)
    api.SteamAPI_Init.restype = ctypes.c_bool
    api.SteamAPI_Init.argtypes = []
    api.SteamAPI_Shutdown.restype = None
    api.SteamAPI_Shutdown.argtypes = []
    api.SteamAPI_RunCallbacks.restype = None
    api.SteamAPI_RunCallbacks.argtypes = []

    if not api.SteamAPI_Init():
        try:
            (work / "worker_error.txt").write_text(
                "SteamAPI_Init failed — is Steam running and logged in?",
                encoding="utf-8",
            )
        except OSError:
            pass
        try:
            appid_file.unlink(missing_ok=True)
        except OSError:
            pass
        return 1

    stop = False

    def _stop(*_args: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _stop)

    try:
        heartbeat.write_text(str(time.time()), encoding="ascii")
    except OSError:
        pass

    try:
        while not stop:
            api.SteamAPI_RunCallbacks()
            try:
                heartbeat.write_text(str(time.time()), encoding="ascii")
            except OSError:
                pass
            time.sleep(0.5)
    finally:
        try:
            api.SteamAPI_Shutdown()
        except Exception:
            pass
        for path in (appid_file, heartbeat):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Idle a single Steam app")
    parser.add_argument("appid", type=int)
    parser.add_argument("--dll", type=Path, default=None)
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    try:
        from .paths import app_root

        root = app_root()
    except Exception:
        pass
    dll = args.dll or (root / "native" / "steam_api64.dll")
    return run_idle(args.appid, dll)


if __name__ == "__main__":
    raise SystemExit(main())
