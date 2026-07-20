from __future__ import annotations

import os
import shutil
import winreg
from pathlib import Path

from .config import NATIVE_DIR, ensure_dirs
from .paths import app_root, resource_root


def find_steam_path(configured: str = "") -> Path | None:
    if configured:
        p = Path(configured)
        if (p / "steam.exe").exists():
            return p

    candidates: list[Path] = []
    for key_path, value_name in (
        (r"Software\Valve\Steam", "SteamPath"),
        (r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"),
        (r"SOFTWARE\Valve\Steam", "InstallPath"),
    ):
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, key_path) as key:
                    value, _ = winreg.QueryValueEx(key, value_name)
                    candidates.append(Path(str(value)))
            except OSError:
                continue

    for env_name in ("STEAM_PATH", "SteamPath"):
        env = os.environ.get(env_name)
        if env:
            candidates.append(Path(env))

    candidates.extend(
        [
            Path(r"C:\Program Files (x86)\Steam"),
            Path(r"C:\Program Files\Steam"),
            Path(r"C:\Steam"),
            Path(r"C:\SteamOffline"),
        ]
    )

    seen: set[str] = set()
    for path in candidates:
        resolved = str(path.resolve()) if path.exists() else str(path)
        if resolved.lower() in seen:
            continue
        seen.add(resolved.lower())
        if (path / "steam.exe").exists():
            return path
    return None


def ensure_bundled_dll() -> Path | None:
    """Make sure native/steam_api64.dll exists next to the app (copy from bundle)."""
    ensure_dirs()
    target = NATIVE_DIR / "steam_api64.dll"
    if target.exists():
        return target

    candidates = [
        resource_root() / "native" / "steam_api64.dll",
        resource_root() / "steam_api64.dll",
        app_root() / "native" / "steam_api64.dll",
    ]
    for src in candidates:
        if src.exists():
            try:
                shutil.copy2(src, target)
                return target
            except OSError:
                return src
    return None


def find_steam_api_dll(steam_path: Path | None = None) -> Path | None:
    bundled = ensure_bundled_dll()
    if bundled and bundled.exists():
        return bundled

    local = NATIVE_DIR / "steam_api64.dll"
    if local.exists():
        return local

    search_roots: list[Path] = []
    if steam_path:
        search_roots.append(steam_path / "steamapps" / "common")
        search_roots.append(steam_path)

    for root in search_roots:
        if not root.exists():
            continue
        try:
            for hit in root.rglob("steam_api64.dll"):
                return hit
        except OSError:
            continue
    return None


def is_steam_running() -> bool:
    try:
        import subprocess

        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq steam.exe", "/NH"],
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return "steam.exe" in out.lower()
    except Exception:
        return False
