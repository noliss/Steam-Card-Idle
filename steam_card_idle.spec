# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for Steam Card Idle (Windows)."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# SPECPATH = directory of this .spec (project root when file lives here)
ROOT = Path(SPECPATH).resolve()
if not (ROOT / "run_app.py").exists():
    # spec was under build/
    alt = ROOT.parent
    if (alt / "run_app.py").exists():
        ROOT = alt

PKG = ROOT / "steam_card_idle"

datas = [
    (str(PKG / "web"), "steam_card_idle/web"),
    (str(ROOT / "native" / "steam_api64.dll"), "native"),
    (str(ROOT / "assets" / "icon.ico"), "assets"),
]
datas += collect_data_files("webview")

binaries = []
hiddenimports = [
    "webview",
    "webview.platforms.edgechromium",
    "clr_loader",
    "pythonnet",
    "bs4",
    "lxml",
    "lxml.etree",
    "lxml._elementpath",
    "browser_cookie3",
    "playwright",
    "playwright.sync_api",
    "socks",
]
hiddenimports += collect_submodules("steam_card_idle")

tmp_ret = collect_all("playwright")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

a = Analysis(
    [str(ROOT / "run_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pytest"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SteamCardIdle",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SteamCardIdle",
)
