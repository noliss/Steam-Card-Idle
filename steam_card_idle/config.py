from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import app_root

ROOT = app_root()
CONFIG_PATH = ROOT / "config.json"
NATIVE_DIR = ROOT / "native"
DATA_DIR = ROOT / "data"
WORKERS_DIR = DATA_DIR / "workers"


@dataclass
class AppConfig:
    sessionid: str = ""
    steam_login_secure: str = ""
    profile_url: str = ""
    persona_name: str = ""
    avatar_url: str = ""
    blacklist: list[str] = field(default_factory=list)
    whitelist: list[str] = field(default_factory=list)
    whitelist_mode: bool = False
    sort: str = "mostcards"  # mostcards | leastcards | default
    fast_mode: bool = True
    max_simultaneous: int = 20
    check_interval_sec: int = 900
    check_interval_last_card_sec: int = 300
    skip_f2p: bool = True
    farm_wave_sec: int = 300
    flush_pause_sec: int = 15
    auto_browser_cookies: bool = True
    steam_path: str = ""
    language: str = "en"

    def save(self, path: Path | None = None) -> None:
        target = path or CONFIG_PATH
        target.write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path | None = None) -> AppConfig:
        target = path or CONFIG_PATH
        if not target.exists():
            cfg = cls()
            cfg.save(target)
            return cfg
        raw: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in raw.items() if k in known})


def ensure_dirs() -> None:
    # Re-bind in case frozen path resolved after import edge-cases
    global ROOT, CONFIG_PATH, NATIVE_DIR, DATA_DIR, WORKERS_DIR
    ROOT = app_root()
    CONFIG_PATH = ROOT / "config.json"
    NATIVE_DIR = ROOT / "native"
    DATA_DIR = ROOT / "data"
    WORKERS_DIR = DATA_DIR / "workers"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORKERS_DIR.mkdir(parents=True, exist_ok=True)
    NATIVE_DIR.mkdir(parents=True, exist_ok=True)
