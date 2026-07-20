from __future__ import annotations

import sys


def _run_idle_worker(argv: list[str]) -> int:
    """Frozen entry: SteamCardIdle.exe --idle-worker <appid> --dll <path>"""
    import argparse
    from pathlib import Path

    from .idle_worker import run_idle
    from .paths import app_root

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("appid", type=int)
    parser.add_argument("--dll", type=Path, default=None)
    args = parser.parse_args(argv)
    dll = args.dll or (app_root() / "native" / "steam_api64.dll")
    return run_idle(args.appid, dll)


def main() -> int:
    from .session import _strip_socks_env

    _strip_socks_env()

    argv = sys.argv[1:]
    if argv and argv[0] == "--idle-worker":
        return _run_idle_worker(argv[1:])

    from .cli import main as cli_main

    return int(cli_main(argv if argv else None))


if __name__ == "__main__":
    raise SystemExit(main())
