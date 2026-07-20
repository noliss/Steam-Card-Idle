from __future__ import annotations

import argparse
import sys
import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from . import __version__
from .badges import fetch_badges, total_drops
from .config import AppConfig, ensure_dirs
from .orchestrator import Orchestrator, Phase
from .session import SessionError, build_session
from .steam_paths import find_steam_api_dll, find_steam_path, is_steam_running

console = Console()


def _status_table(orch: Orchestrator) -> Table:
    st = orch.status
    table = Table(title="Steam Card Idle", expand=True)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Phase", st.phase.value)
    table.add_row("Status", st.message or "—")
    table.add_row("Cards left", str(st.total_remaining))
    table.add_row("Games queued", str(len(st.badges)))
    table.add_row(
        "Now",
        f"{st.current.name} [{st.current.app_id}] ({st.current.remaining})"
        if st.current
        else ", ".join(str(i) for i in st.active_ids) or "—",
    )
    if st.error:
        table.add_row("Error", st.error)
    return table


def cmd_setup(args: argparse.Namespace) -> int:
    ensure_dirs()
    cfg = AppConfig.load()
    if args.sessionid:
        cfg.sessionid = args.sessionid
    if args.login_secure:
        cfg.steam_login_secure = args.login_secure
    if args.no_auto_cookies:
        cfg.auto_browser_cookies = False
    try:
        if args.login:
            from .session import apply_captured_cookies
            from .steam_login import login_with_steam

            console.print("Opening Steam login window…")
            sessionid, login = login_with_steam()
            session = apply_captured_cookies(cfg, sessionid, login)
        else:
            session = build_session(cfg, force_browser=args.from_browser)
    except SessionError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    cfg.save()
    console.print(f"[green]OK[/green] profile: {session.profile_url}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    cfg = AppConfig.load()
    try:
        session = build_session(cfg)
    except SessionError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    badges = fetch_badges(session, cfg)
    table = Table(title=f"Drops: {total_drops(badges)} cards / {len(badges)} games")
    table.add_column("AppID")
    table.add_column("Game")
    table.add_column("Cards")
    table.add_column("Hours")
    for b in badges:
        table.add_row(str(b.app_id), b.name, str(b.remaining), f"{b.hours:.1f}")
    console.print(table)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    ensure_dirs()
    cfg = AppConfig.load()
    if args.normal:
        cfg.fast_mode = False
    if args.fast:
        cfg.fast_mode = True
    if args.max_games:
        cfg.max_simultaneous = args.max_games
    if args.sort:
        cfg.sort = args.sort

    steam = find_steam_path(cfg.steam_path)
    dll = find_steam_api_dll(steam)
    console.print(f"Steam: {steam or 'not found'}")
    console.print(f"DLL:   {dll or 'not found'}")
    console.print(f"Steam running: {is_steam_running()}")
    if not is_steam_running():
        console.print("[red]Start Steam and sign in.[/red]")
        return 1
    if not dll:
        console.print("[red]Missing steam_api64.dll in native/[/red]")
        return 1

    logs: list[str] = []

    def on_log(msg: str) -> None:
        logs.append(msg)
        console.log(msg)

    orch = Orchestrator(cfg, on_log=on_log)
    orch.start_async()
    try:
        with Live(_status_table(orch), console=console, refresh_per_second=4) as live:
            while True:
                live.update(_status_table(orch))
                if orch.status.phase in (Phase.DONE, Phase.ERROR) and not (
                    orch._thread and orch._thread.is_alive()
                ):
                    break
                time.sleep(0.25)
    except KeyboardInterrupt:
        console.print("\nStopping…")
        orch.stop()
        return 0

    if orch.status.phase == Phase.ERROR:
        return 1
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    cfg = AppConfig.load()
    steam = find_steam_path(cfg.steam_path)
    dll = find_steam_api_dll(steam)
    console.print(f"version: {__version__}")
    console.print(f"steam path: {steam}")
    console.print(f"steam running: {is_steam_running()}")
    console.print(f"steam_api64.dll: {dll}")
    console.print(f"cookies set: {bool(cfg.sessionid and cfg.steam_login_secure)}")
    console.print(f"profile: {cfg.profile_url or '—'}")
    console.print(f"fast_mode: {cfg.fast_mode}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="steam-card-idle",
        description="Steam Card Idle — farm Steam Trading Cards",
    )
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")

    setup = sub.add_parser("setup", help="Save / refresh cookies")
    setup.add_argument("--login", action="store_true", help="Steam login window (recommended)")
    setup.add_argument("--sessionid", default="")
    setup.add_argument("--login-secure", default="")
    setup.add_argument("--from-browser", action="store_true")
    setup.add_argument("--no-auto-cookies", action="store_true")
    setup.set_defaults(func=cmd_setup)

    scan = sub.add_parser("scan", help="Show games with drops")
    scan.set_defaults(func=cmd_scan)

    run = sub.add_parser("run", help="Start farming")
    run.add_argument("--fast", action="store_true", help="Fast Mode (default from config)")
    run.add_argument("--normal", action="store_true", help="One game at a time")
    run.add_argument("--max-games", type=int, default=0)
    run.add_argument("--sort", choices=["mostcards", "leastcards", "default"])
    run.set_defaults(func=cmd_run)

    doctor = sub.add_parser("doctor", help="Environment check")
    doctor.set_defaults(func=cmd_doctor)

    gui = sub.add_parser("gui", help="Open GUI")
    gui.set_defaults(func=lambda _a: _launch_gui())

    return p


def _launch_gui() -> int:
    from .webui import main as gui_main

    gui_main()
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        if argv is None and len(sys.argv) <= 1:
            return _launch_gui()
        parser.print_help()
        return 0
    return int(args.func(args))
