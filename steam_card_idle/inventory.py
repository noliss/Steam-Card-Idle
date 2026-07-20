"""Steam Community inventory helpers (context 753 = Steam items / trading cards)."""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

from .session import SteamSession, http_client, request_get


@dataclass(frozen=True)
class InventoryCard:
    asset_id: str
    class_id: str
    instance_id: str
    name: str
    game: str
    app_id: int  # game appid if parseable, else 0
    market_hash_name: str


def _parse_game_app_id(market_hash_name: str, tags: list[dict]) -> tuple[str, int]:
    """Best-effort game title + appid from card description."""
    app_id = 0
    game = ""
    for tag in tags:
        if tag.get("category") == "Game":
            game = tag.get("name") or tag.get("localized_tag_name") or ""
            internal = tag.get("internal_name") or ""
            m = re.search(r"app_(\d+)", internal)
            if m:
                app_id = int(m.group(1))
            break
    if not game and " - " in market_hash_name:
        game = market_hash_name.rsplit(" - ", 1)[0]
        game = re.sub(r"-Foil$", "", game).strip()
    return game or "Steam", app_id


def _is_trading_card(desc: dict) -> bool:
    for tag in desc.get("tags") or []:
        if tag.get("category") == "item_class":
            internal = (tag.get("internal_name") or "").lower()
            if internal == "item_class_2":
                return True
    typ = (desc.get("type") or "").lower()
    return "trading card" in typ or "торговая карточка" in typ


def fetch_trading_cards(session: SteamSession, *, count: int = 2500) -> list[InventoryCard]:
    """
    Load Steam inventory (app 753, context 6) and return trading cards.
    Requires steam_id64 and a valid community session (private inv OK with cookies).
    """
    steam_id = session.steam_id64
    if not steam_id:
        m = re.search(r"/profiles/(\d+)", session.profile_url or "")
        if m:
            steam_id = m.group(1)
    if not steam_id:
        raise RuntimeError("Нет steam_id64 — нельзя прочитать инвентарь.")

    http = http_client(session)
    url = f"https://steamcommunity.com/inventory/{steam_id}/753/6"
    cards: list[InventoryCard] = []
    start_assetid: str | None = None

    while True:
        params: dict[str, str | int] = {"l": "english", "count": min(count, 2000)}
        if start_assetid:
            params["start_assetid"] = start_assetid

        try:
            resp = request_get(
                http,
                url,
                params=params,
                timeout=(10, 45),
                retries=3,
                backoff=1.0,
            )
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status == 403:
                raise RuntimeError(
                    "Инвентарь недоступен (403). Сделай инвентарь видимым для себя "
                    "(Profile → Inventory → Private всё ещё читается с cookies; "
                    "проверь сессию)."
                ) from exc
            raise
        data = resp.json()
        if not data:
            raise RuntimeError("Инвентарь: пустой ответ")
        if data.get("success") in (0, False) and not data.get("assets"):
            if data.get("total_inventory_count") == 0:
                break
            raise RuntimeError(f"Инвентарь: неожиданный ответ {data!r}"[:240])

        assets = data.get("assets") or []
        descriptions = data.get("descriptions") or []
        desc_map = {
            f"{d.get('classid')}_{d.get('instanceid')}": d for d in descriptions
        }

        for asset in assets:
            class_id = str(asset.get("classid") or "")
            instance_id = str(asset.get("instanceid") or "0")
            asset_id = str(asset.get("assetid") or "")
            desc = desc_map.get(f"{class_id}_{instance_id}") or {}
            if not _is_trading_card(desc):
                continue
            market = desc.get("market_hash_name") or desc.get("name") or "Card"
            name = desc.get("name") or market
            tags = desc.get("tags") or []
            game, app_id = _parse_game_app_id(market, tags)
            cards.append(
                InventoryCard(
                    asset_id=asset_id,
                    class_id=class_id,
                    instance_id=instance_id,
                    name=name,
                    game=game,
                    app_id=app_id,
                    market_hash_name=market,
                )
            )

        if not data.get("more_items"):
            break
        start_assetid = str(data.get("last_assetid") or "")
        if not start_assetid:
            break

    return cards
