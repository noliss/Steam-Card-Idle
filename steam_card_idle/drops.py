"""Track trading-card drops via inventory + badge remaining counts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .badges import Badge
from .config import DATA_DIR, ensure_dirs
from .inventory import InventoryCard


@dataclass
class CardDrop:
    time: str
    app_id: int
    game: str
    count: int
    remaining_after: int
    card_name: str = ""
    source: str = "badge"  # badge | inventory
    market_hash_name: str = ""

    def label(self) -> str:
        if self.card_name:
            return f"{self.time}  ·  {self.game}  ·  {self.card_name}"
        plural = "карта" if self.count == 1 else ("карты" if self.count < 5 else "карт")
        return (
            f"{self.time}  ·  {self.game}  ·  +{self.count} {plural} "
            f"(осталось {self.remaining_after})"
        )


@dataclass
class DropTracker:
    """Detect drops from inventory asset diffs (primary) and badge remaining."""

    previous: dict[int, int] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    seen_assets: set[str] = field(default_factory=set)
    history: list[CardDrop] = field(default_factory=list)
    session_total: int = 0
    primed: bool = False
    inventory_primed: bool = False

    def seed(self, badges: list[Badge]) -> None:
        self.previous = {b.app_id: max(0, b.remaining) for b in badges}
        self.names = {b.app_id: b.name for b in badges}
        self.primed = True

    def seed_inventory(self, cards: list[InventoryCard]) -> None:
        self.seen_assets = {c.asset_id for c in cards if c.asset_id}
        self.inventory_primed = True

    def update_inventory(self, cards: list[InventoryCard]) -> list[CardDrop]:
        """Primary detector — new trading-card asset IDs in inventory."""
        if not self.inventory_primed:
            self.seed_inventory(cards)
            return []

        found: list[CardDrop] = []
        now = datetime.now().strftime("%H:%M:%S")
        current_ids = {c.asset_id for c in cards if c.asset_id}
        by_id = {c.asset_id: c for c in cards if c.asset_id}

        for asset_id in current_ids - self.seen_assets:
            card = by_id[asset_id]
            found.append(
                CardDrop(
                    time=now,
                    app_id=card.app_id,
                    game=card.game,
                    count=1,
                    remaining_after=-1,
                    card_name=card.name,
                    source="inventory",
                    market_hash_name=card.market_hash_name,
                )
            )

        for drop in found:
            self.history.append(drop)
            self.session_total += drop.count

        if len(self.history) > 200:
            self.history = self.history[-200:]

        self.seen_assets = current_ids
        return found

    def update(self, badges: list[Badge]) -> list[CardDrop]:
        """Secondary — badge remaining decreased (lags behind inventory)."""
        if not self.primed:
            self.seed(badges)
            return []

        found: list[CardDrop] = []
        now = datetime.now().strftime("%H:%M:%S")
        current = {b.app_id: max(0, b.remaining) for b in badges}
        for b in badges:
            self.names[b.app_id] = b.name

        for app_id, prev in list(self.previous.items()):
            if app_id not in current and prev > 0:
                found.append(
                    CardDrop(
                        time=now,
                        app_id=app_id,
                        game=self.names.get(app_id, f"App {app_id}"),
                        count=prev,
                        remaining_after=0,
                        source="badge",
                    )
                )

        for app_id, rem in current.items():
            prev = self.previous.get(app_id)
            if prev is None:
                continue
            if rem < prev:
                found.append(
                    CardDrop(
                        time=now,
                        app_id=app_id,
                        game=self.names.get(app_id, f"App {app_id}"),
                        count=prev - rem,
                        remaining_after=rem,
                        source="badge",
                    )
                )

        if self.inventory_primed:
            self.previous = current
            return []

        for drop in found:
            self.history.append(drop)
            self.session_total += drop.count

        if len(self.history) > 200:
            self.history = self.history[-200:]

        self.previous = current
        return found

    def save(self, path: Path | None = None) -> None:
        ensure_dirs()
        target = path or (DATA_DIR / "drops_session.json")
        payload = {
            "session_total": self.session_total,
            "history": [asdict(d) for d in self.history[-100:]],
        }
        target.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    @classmethod
    def load_history(cls, path: Path | None = None) -> list[CardDrop]:
        target = path or (DATA_DIR / "drops_session.json")
        if not target.exists():
            return []
        try:
            raw = json.loads(target.read_text(encoding="utf-8"))
            out: list[CardDrop] = []
            for item in raw.get("history") or []:
                out.append(
                    CardDrop(
                        time=str(item.get("time") or ""),
                        app_id=int(item.get("app_id") or 0),
                        game=str(item.get("game") or ""),
                        count=int(item.get("count") or 1),
                        remaining_after=int(item.get("remaining_after") or -1),
                        card_name=str(item.get("card_name") or ""),
                        source=str(item.get("source") or "badge"),
                        market_hash_name=str(item.get("market_hash_name") or ""),
                    )
                )
            return out
        except Exception:
            return []
