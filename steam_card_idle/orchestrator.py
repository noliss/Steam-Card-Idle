from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .badges import Badge, fetch_badges, refresh_badge, total_drops
from .config import AppConfig
from .drops import CardDrop, DropTracker
from .idle_manager import IdleManager
from .inventory import fetch_trading_cards
from .session import SteamSession, build_session
from .steam_paths import is_steam_running


class Phase(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    FAST_MULTI = "fast_multi"
    FLUSH = "flush"
    NORMAL = "normal"
    DONE = "done"
    ERROR = "error"
    PAUSED = "paused"


LogFn = Callable[[str], None]
StatusFn = Callable[["FarmStatus"], None]


@dataclass
class FarmStatus:
    phase: Phase = Phase.IDLE
    message: str = ""
    badges: list[Badge] = field(default_factory=list)
    active_ids: list[int] = field(default_factory=list)
    current: Badge | None = None
    total_remaining: int = 0
    error: str = ""
    recent_drops: list[CardDrop] = field(default_factory=list)
    session_drops: int = 0


class Orchestrator:
    """Badge scan + idle loop with stable Fast Mode (no constant game switching)."""

    def __init__(
        self,
        cfg: AppConfig,
        on_log: LogFn | None = None,
        on_status: StatusFn | None = None,
        seed_badges: list[Badge] | None = None,
    ) -> None:
        self.cfg = cfg
        self.on_log = on_log or (lambda _m: None)
        self.on_status = on_status or (lambda _s: None)
        self.session: SteamSession | None = None
        self.manager = IdleManager(steam_path=cfg.steam_path)
        self.drops = DropTracker()
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = FarmStatus()
        self._skip_current = False
        self._seed_badges = list(seed_badges) if seed_badges else []

    def log(self, msg: str) -> None:
        self.on_log(msg)

    def emit(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self.status, key, value)
        self.status.total_remaining = total_drops(self.status.badges)
        self.status.active_ids = self.manager.running_ids()
        self.status.recent_drops = list(self.drops.history)
        self.status.session_drops = self.drops.session_total
        self.on_status(self.status)

    def _note_drops(self, badges: list[Badge]) -> list[CardDrop]:
        found = self.drops.update(badges)
        return self._log_new_drops(found)

    def _note_inventory_drops(self) -> list[CardDrop]:
        assert self.session
        try:
            cards = fetch_trading_cards(self.session)
        except Exception as exc:
            self.log(f"Инвентарь: не удалось прочитать ({exc})")
            return []
        if not self.drops.inventory_primed:
            self.drops.seed_inventory(cards)
            self.log(f"Инвентарь: база {len(cards)} trading cards (новые будут в дропах)")
            return []
        found = self.drops.update_inventory(cards)
        return self._log_new_drops(found)

    def _log_new_drops(self, found: list[CardDrop]) -> list[CardDrop]:
        for drop in found:
            if drop.card_name:
                self.log(f"🎴 DROP: {drop.game} — {drop.card_name}")
            else:
                self.log(
                    f"🎴 DROP +{drop.count}: {drop.game} "
                    f"(осталось {drop.remaining_after})"
                )
        if found:
            try:
                self.drops.save()
            except Exception:
                pass
        return found

    def start_async(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._pause.clear()
        self._thread = threading.Thread(target=self.run, name="farmer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._pause.clear()
        self.manager.stop_all()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=8)
        self.emit(phase=Phase.IDLE, message="Остановлено")

    def pause(self) -> None:
        self._pause.set()
        self.manager.stop_all()
        self.emit(phase=Phase.PAUSED, message="Пауза")

    def resume(self) -> None:
        self._pause.clear()

    def skip(self) -> None:
        self._skip_current = True

    def run(self) -> None:
        try:
            self._run_inner()
        except Exception as exc:
            self.log(f"Ошибка: {exc}")
            self.emit(phase=Phase.ERROR, error=str(exc), message=str(exc))
            self.manager.stop_all()

    def _run_inner(self) -> None:
        if not is_steam_running():
            raise RuntimeError("Steam не запущен. Открой Steam и залогинься.")

        self.emit(phase=Phase.LOADING, message="Авторизация…")
        self.session = build_session(self.cfg, allow_offline=True)
        if self.session.offline:
            self.log(
                "Steam community не ответил — продолжаю с сохранённым профилем"
            )
        self.log(f"Профиль: {self.session.profile_url}")

        self.manager.ensure_ready()
        self.emit(phase=Phase.LOADING, message="Читаю badges…")
        badges: list[Badge] = []
        if self.session.offline and self._seed_badges:
            badges = list(self._seed_badges)
            self.log(f"Offline start — кэш UI ({len(badges)} игр)")
        else:
            try:
                badges = fetch_badges(self.session, self.cfg)
            except Exception as exc:
                if self._seed_badges:
                    badges = list(self._seed_badges)
                    self.log(
                        f"Badges с Steam недоступны ({exc}) — "
                        f"стартую с кэша UI ({len(badges)} игр)"
                    )
                else:
                    raise
        self.drops = DropTracker()
        self.drops.seed(badges)
        self.emit(badges=badges, message=f"Найдено игр с дропами: {len(badges)}")
        self.log(f"Игр с дропами: {len(badges)} (карт: {total_drops(badges)})")
        self.log("Отслеживание дропов: инвентарь Steam (основные) + badges")
        try:
            inv = fetch_trading_cards(self.session)
            self.drops.seed_inventory(inv)
            self.log(f"Инвентарь: снята база из {len(inv)} карт")
        except Exception as exc:
            self.log(f"Инвентарь недоступен на старте ({exc}) — fallback на badges")

        if not badges:
            self.emit(phase=Phase.DONE, message="Карты закончились — idling complete")
            self.log("Idling complete")
            return

        if self.cfg.fast_mode:
            self._fast_loop(badges)
        else:
            self._normal_loop(badges)

        if not self._stop.is_set():
            self.emit(phase=Phase.DONE, message="Idling complete")
            self.log("Idling complete")

    def _wait(self, seconds: float) -> bool:
        """Sleep interruptibly. Returns False if stop requested."""
        end = time.time() + seconds
        while time.time() < end:
            if self._stop.is_set():
                return False
            while self._pause.is_set() and not self._stop.is_set():
                time.sleep(0.2)
            if self._skip_current:
                return True
            time.sleep(min(0.25, max(0.0, end - time.time())))
        return not self._stop.is_set()

    def _flush_pause(self, seconds: float) -> None:
        """Pause that is NOT cut short by Stop — Steam needs sessions to fully end."""
        end = time.time() + seconds
        while time.time() < end:
            time.sleep(min(0.25, max(0.0, end - time.time())))

    def _normal_loop(self, badges: list[Badge]) -> None:
        queue = list(badges)
        while queue and not self._stop.is_set():
            badge = queue[0]
            self._skip_current = False
            self.emit(
                phase=Phase.NORMAL,
                current=badge,
                badges=queue,
                message=f"Idle: {badge.name} ({badge.remaining} карт)",
            )
            self.log(f"-> {badge.name} [{badge.app_id}] remaining={badge.remaining}")
            try:
                self.manager.stop_all()
                self.manager.start(badge.app_id)
            except Exception as exc:
                self.log(f"Пропуск {badge.app_id}: {exc}")
                queue.pop(0)
                continue

            interval = (
                self.cfg.check_interval_last_card_sec
                if badge.remaining == 1
                else self.cfg.check_interval_sec
            )
            while not self._stop.is_set():
                if not self._wait(interval):
                    break
                if self._skip_current:
                    self.log(f"Skip {badge.name}")
                    self.manager.stop(badge.app_id)
                    queue.pop(0)
                    break
                assert self.session
                refresh_badge(self.session, badge)
                self._note_drops(queue)
                self.emit(current=badge, badges=queue)
                self.log(f"  check {badge.name}: {badge.remaining} left")
                if badge.remaining == 0:
                    self.manager.stop(badge.app_id)
                    queue.pop(0)
                    break
                interval = (
                    self.cfg.check_interval_last_card_sec
                    if badge.remaining == 1
                    else self.cfg.check_interval_sec
                )

            if not queue and not self._stop.is_set():
                assert self.session
                queue = fetch_badges(self.session, self.cfg)
                self.emit(badges=queue)

        self.manager.stop_all()

    def _fast_loop(self, badges: list[Badge]) -> None:
        """
        Farm → Flush → Collect cycle.

        Steam usually credits trading-card drops only after game sessions end.
        So we idle a wave, stop everything briefly (like pressing Stop), read
        inventory, then start the next wave. Elegant and matches observed behavior.
        """
        assert self.session
        max_n = max(1, min(self.cfg.max_simultaneous, 32))
        active: dict[int, Badge] = {}
        farm_sec = max(60, int(getattr(self.cfg, "farm_wave_sec", 120) or 120))
        flush_sec = max(8, int(getattr(self.cfg, "flush_pause_sec", 15) or 15))

        def wave_cap(queue: list[Badge]) -> int:
            """Games we actually try to run this wave (not the raw concurrency setting)."""
            eligible = sum(
                1
                for b in queue
                if b.remaining > 0 and b.app_id not in self.manager._failed
            )
            if eligible <= 0:
                return 0
            return min(max_n, eligible)

        def sync_starts(queue: list[Badge]) -> None:
            nonlocal active
            alive = set(self.manager.running_ids())
            for app_id in list(active):
                badge = next((b for b in queue if b.app_id == app_id), None)
                if app_id not in alive:
                    self.log(f"Worker dead/stale {app_id} — убираю из active")
                    active.pop(app_id, None)
                    continue
                if badge is None or badge.remaining == 0:
                    self.log(f"Stop drained/missing {app_id}")
                    self.manager.stop(app_id)
                    active.pop(app_id, None)

            attempts = 0
            for badge in queue:
                if len(active) >= max_n:
                    break
                if badge.app_id in active or badge.remaining == 0:
                    continue
                if badge.app_id in self.manager._failed:
                    continue
                attempts += 1
                if attempts > max_n * 2 and not active:
                    self.log("Слишком много ошибок запуска idle — стоп попыток.")
                    break
                try:
                    self.manager.start(badge.app_id)
                    active[badge.app_id] = badge
                    self.log(
                        f"Start idle {badge.name} [{badge.app_id}] "
                        f"cards={badge.remaining}"
                    )
                    time.sleep(0.45)
                except Exception as exc:
                    self.log(f"Не удалось idle {badge.app_id}: {exc}")

            running = self.manager.running_ids()
            for app_id in list(active):
                if app_id not in running:
                    self.log(f"Worker died: {app_id}")
                    active.pop(app_id, None)

        def flush_and_collect(queue: list[Badge]) -> list[CardDrop]:
            """Stop all sessions, wait for Steam to credit drops, read inventory."""
            nonlocal active
            self.log(
                f"Flush wave: останавливаю {len(active)} игр на {flush_sec}с "
                "(Steam засчитывает карты после закрытия сессий)"
            )
            self.emit(
                phase=Phase.FLUSH,
                badges=queue,
                message=f"Flush: пауза {flush_sec}с — зачисление дропов…",
            )
            self.manager.stop_all()
            active.clear()

            # Uninterruptible: Steam often credits cards only after sessions fully end
            self._flush_pause(flush_sec)

            new_drops = self._note_inventory_drops()
            if not new_drops:
                self._flush_pause(5)
                more = self._note_inventory_drops()
                new_drops.extend(more)

            if new_drops:
                self.log(
                    f"Flush: +{sum(d.count for d in new_drops)} карт "
                    f"(всего за сессию {self.drops.session_total})"
                )
            else:
                self.log("Flush: новых карт в инвентаре нет")

            self.emit(
                phase=Phase.FLUSH,
                badges=queue,
                message=(
                    f"Flush done · 🎴 {self.drops.session_total}"
                    + (
                        f" · +{sum(d.count for d in new_drops)}"
                        if new_drops
                        else ""
                    )
                ),
            )
            return new_drops

        queue = list(badges)
        wave = 0
        cap = wave_cap(queue)
        self.emit(
            phase=Phase.FAST_MULTI,
            badges=queue,
            message=f"Wave: запуск до {cap} игр…",
        )
        sync_starts(queue)
        cap = wave_cap(queue)
        self.emit(
            phase=Phase.FAST_MULTI,
            badges=queue,
            current=None,
            message=(
                f"Wave #{wave + 1}: idle {len(active)}/{cap} · "
                f"flush через ~{farm_sec // 60} мин"
            ),
        )

        while not self._stop.is_set():
            if not queue:
                break

            self._skip_current = False
            farm_end = time.time() + farm_sec
            while time.time() < farm_end and not self._stop.is_set():
                slice_sec = min(60.0, farm_end - time.time())
                if slice_sec <= 0:
                    break
                if not self._wait(slice_sec):
                    break
                if self._skip_current:
                    break
                left = max(0, int(farm_end - time.time()))
                cap = wave_cap(queue)
                self.emit(
                    phase=Phase.FAST_MULTI,
                    badges=queue,
                    message=(
                        f"Wave #{wave + 1}: idle {len(self.manager.running_ids())}/{cap} · "
                        f"до flush {left // 60}:{left % 60:02d} · "
                        f"🎴 {self.drops.session_total}"
                    ),
                )
                alive = set(self.manager.running_ids())
                for app_id in list(active):
                    if app_id not in alive:
                        active.pop(app_id, None)
                if len(active) < max_n:
                    sync_starts(queue)

            if self._stop.is_set():
                break

            flush_and_collect(queue)

            try:
                queue = fetch_badges(self.session, self.cfg)
                if self.drops.inventory_primed:
                    self.drops.update(queue)
                else:
                    self._note_drops(queue)
                self.log(
                    f"После flush: {len(queue)} игр, {total_drops(queue)} карт remaining"
                )
            except Exception as exc:
                self.log(f"Badge rescan after flush failed: {exc}")

            if not queue:
                break

            wave += 1
            cap = wave_cap(queue)
            self.emit(
                phase=Phase.FAST_MULTI,
                badges=queue,
                message=f"Wave #{wave + 1}: запуск снова…",
            )
            sync_starts(queue)
            cap = wave_cap(queue)
            self.emit(
                phase=Phase.FAST_MULTI,
                badges=queue,
                message=(
                    f"Wave #{wave + 1}: idle {len(active)}/{cap} · "
                    f"🎴 {self.drops.session_total}"
                ),
            )

        if active or self.manager.running_ids():
            self.log("Финальный flush перед выходом…")
            flush_and_collect(queue)

        self.manager.stop_all()
        self.log(f"Сессия завершена. Всего дропов: {self.drops.session_total}")
        try:
            self.drops.save()
        except Exception:
            pass
