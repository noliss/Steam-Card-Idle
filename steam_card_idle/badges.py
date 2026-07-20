from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

from .config import DATA_DIR, AppConfig, ensure_dirs
from .session import SteamSession, http_client, request_get

# Known no-drop / noise app IDs
SKIP_APP_IDS = {
    "368020",
    "335590",
    "582660",  # Black Desert — cards only after real-money spend
}

F2P_CACHE = DATA_DIR / "f2p_cache.json"


@dataclass
class Badge:
    app_id: int
    name: str
    remaining: int
    hours: float = 0.0

    @property
    def app_id_str(self) -> str:
        return str(self.app_id)


def _parse_number(text: str) -> str:
    match = re.search(r"[0-9]+(?:[.,][0-9]+)?", text.replace("\xa0", " "))
    return match.group(0) if match else ""


def _page_count(soup: BeautifulSoup) -> int:
    pages = {"1"}
    for link in soup.select("a.pagelink"):
        href = link.get("href") or ""
        m = re.search(r"[?&]p=(\d+)", href)
        if m:
            pages.add(m.group(1))
    return max(int(p) for p in pages)


def _parse_badge_row(row, blacklist: set[str]) -> Badge | None:
    overlay = row.select_one("a.badge_row_overlay")
    if not overlay or not overlay.get("href"):
        return None
    href = overlay["href"]
    if "border=1" in href:
        return None
    m = re.search(r"gamecards/(\d+)/", href)
    if not m:
        return None
    app_id = m.group(1)
    if app_id in blacklist or app_id in SKIP_APP_IDS:
        return None

    hours_node = row.select_one("div.badge_title_stats_playtime")
    hours_raw = _parse_number(hours_node.get_text(" ", strip=True)) if hours_node else ""
    hours = float(hours_raw.replace(",", ".")) if hours_raw else 0.0

    name_node = row.select_one("div.badge_title")
    name = "Unknown"
    if name_node:
        texts = [t.strip() for t in name_node.find_all(string=True, recursive=False)]
        name = next((t for t in texts if t), name_node.get_text(" ", strip=True))
        name = re.sub(r"\s+", " ", name).strip()
        name = re.split(r"\s{2,}|\t", name)[0].strip()

    card_node = row.select_one("span.progress_info_bold")
    cards_raw = _parse_number(card_node.get_text(" ", strip=True)) if card_node else ""
    remaining = int(cards_raw) if cards_raw else 0
    if remaining <= 0:
        return None

    return Badge(app_id=int(app_id), name=unquote(name), remaining=remaining, hours=hours)


def fetch_badges(
    session: SteamSession,
    cfg: AppConfig,
    *,
    honor_whitelist: bool = True,
    honor_blacklist: bool = True,
) -> list[Badge]:
    """Scrape badge pages. Optional whitelist/blacklist filtering."""
    http = http_client(session)
    profile = (cfg.profile_url or session.profile_url).rstrip("/")
    if not profile:
        raise RuntimeError("profile_url is empty — set up the session first.")

    blacklist = {str(x) for x in cfg.blacklist} if honor_blacklist else set()
    by_id: dict[int, Badge] = {}

    total_pages = 1
    page = 1
    while page <= total_pages:
        url = f"{profile}/badges/?p={page}"
        resp = request_get(http, url, timeout=(8, 40), retries=3)
        if "login" in resp.url.lower() and "badges" not in resp.url.lower():
            raise RuntimeError("Session expired — refresh cookies.")

        soup = BeautifulSoup(resp.text, "lxml")
        if page == 1:
            total_pages = _page_count(soup)

        rows = soup.select("div.badge_row.is_link")
        for row in rows:
            badge = _parse_badge_row(row, blacklist)
            if badge:
                by_id[badge.app_id] = badge
        page += 1

    badges = list(by_id.values())
    if getattr(cfg, "skip_f2p", True):
        badges = _filter_f2p(http, badges)

    if honor_whitelist and cfg.whitelist_mode:
        if not cfg.whitelist:
            badges = []
        else:
            allowed = {str(x) for x in cfg.whitelist}
            badges = [b for b in badges if str(b.app_id) in allowed]

    return _sort(badges, cfg.sort)


def _filter_f2p(http: requests.Session, badges: list[Badge]) -> list[Badge]:
    """Drop Free-to-Play titles (card drops usually need store spend)."""
    ensure_dirs()
    cache: dict[str, bool] = {}
    if F2P_CACHE.exists():
        try:
            cache = json.loads(F2P_CACHE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    kept: list[Badge] = []
    changed = False
    for badge in badges:
        key = str(badge.app_id)
        if key in SKIP_APP_IDS:
            continue
        if key not in cache:
            try:
                resp = request_get(
                    http,
                    "https://store.steampowered.com/api/appdetails",
                    params={"appids": key, "filters": "basic"},
                    timeout=(6, 20),
                    retries=2,
                )
                payload = resp.json().get(key, {})
                is_free = bool(
                    payload.get("success")
                    and payload.get("data", {}).get("is_free")
                )
            except Exception:
                is_free = False
            cache[key] = is_free
            changed = True
            time.sleep(0.25)
        if cache.get(key):
            continue
        kept.append(badge)

    if changed:
        try:
            F2P_CACHE.write_text(
                json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception:
            pass
    return kept


def refresh_badge(session: SteamSession, badge: Badge) -> Badge:
    """Re-check remaining drops for one game via its gamecards page."""
    http = http_client(session)
    profile = session.profile_url.rstrip("/")
    url = f"{profile}/gamecards/{badge.app_id}"
    resp = request_get(http, url, timeout=(8, 40), retries=3)
    soup = BeautifulSoup(resp.text, "lxml")

    hours_node = soup.select_one("div.badge_title_stats_playtime")
    hours_raw = _parse_number(hours_node.get_text(" ", strip=True)) if hours_node else ""
    hours = float(hours_raw.replace(",", ".")) if hours_raw else badge.hours

    card_node = None
    if hours_node and hours_node.parent:
        card_node = hours_node.parent.select_one("span.progress_info_bold")
    if card_node is None:
        card_node = soup.select_one("span.progress_info_bold")
    cards_raw = _parse_number(card_node.get_text(" ", strip=True)) if card_node else ""
    remaining = int(cards_raw) if cards_raw else 0

    badge.remaining = remaining
    badge.hours = hours
    return badge


def _sort(badges: list[Badge], method: str) -> list[Badge]:
    if method == "mostcards":
        return sorted(badges, key=lambda b: b.remaining, reverse=True)
    if method == "leastcards":
        return sorted(badges, key=lambda b: b.remaining)
    return badges


def total_drops(badges: Iterable[Badge]) -> int:
    return sum(max(0, b.remaining) for b in badges)
