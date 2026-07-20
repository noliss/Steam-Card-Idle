"""HTML UI shell via pywebview — Python bridge for Steam Card Idle."""

from __future__ import annotations

import base64
import json
import threading
import time
import webbrowser
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

import webview

from . import __version__
from .badges import Badge, fetch_badges, total_drops
from .config import AppConfig, ensure_dirs
from .drops import DropTracker
from .i18n import normalize_lang, t as tr
from .orchestrator import FarmStatus, Orchestrator, Phase
from .session import apply_captured_cookies, build_session, make_http
from .steam_login import login_with_steam
from .steam_paths import find_steam_api_dll, find_steam_path, is_steam_running

WEB_DIR = Path(__file__).resolve().parent / "web"
LOG_MAX = 2000
BADGES_CACHE_TTL_SEC = 90.0


class Bridge:
    def __init__(self) -> None:
        ensure_dirs()
        self.cfg = AppConfig.load()
        self.orch: Orchestrator | None = None
        self._farming = False
        self._busy = False
        self._busy_msg = ""
        self._error = ""
        self._status = tr(self.cfg.language, "ready")
        self._games = "—"
        self._cards = "—"
        self._drops = "0"
        self._drops_text = ""
        self._avatar_data_url = ""
        self._window: webview.Window | None = None
        self._authed = bool(self.cfg.sessionid and self.cfg.steam_login_secure)
        self._log: deque[str] = deque(maxlen=LOG_MAX)
        self._games_cache: list[dict[str, Any]] = []
        self._badges_cache: list[Badge] | None = None
        self._badges_cache_ts: float = 0.0
        self._badges_fetching = False
        self._badges_cv = threading.Condition()
        self._drop_counts: dict[int, int] = {}
        self._load_drop_counts()
        self.log(f"Steam Card Idle v{__version__} started")

    def log(self, msg: str) -> None:
        line = f"{datetime.now().strftime('%H:%M:%S')}  {msg}"
        self._log.append(line)
        if self._window:
            try:
                payload = json.dumps(self.get_log(), ensure_ascii=False)
                self._window.evaluate_js(
                    f"window.applyLog && window.applyLog({payload})"
                )
            except Exception:
                pass

    def get_log(self) -> str:
        return "\n".join(self._log)

    def copy_log(self) -> str:
        text = self.get_log()
        if self._window and text:
            try:
                self._window.evaluate_js(
                    "navigator.clipboard && navigator.clipboard.writeText("
                    + json.dumps(text)
                    + ")"
                )
            except Exception:
                pass
        return text

    def clear_log(self) -> str:
        self._log.clear()
        self.log("Log cleared")
        return self.get_log()

    def _load_drop_counts(self) -> None:
        try:
            hist = DropTracker.load_history()
            counts: dict[int, int] = {}
            for d in hist:
                counts[d.app_id] = counts.get(d.app_id, 0) + max(1, d.count)
            self._drop_counts = counts
        except Exception:
            self._drop_counts = {}

    def _t(self, key: str, **kwargs: Any) -> str:
        return tr(self.cfg.language, key, **kwargs)

    def _cfg_public(self) -> dict[str, Any]:
        return {
            "fast_mode": self.cfg.fast_mode,
            "skip_f2p": self.cfg.skip_f2p,
            "max_simultaneous": self.cfg.max_simultaneous,
            "sort": self.cfg.sort,
            "farm_wave_sec": self.cfg.farm_wave_sec,
            "flush_pause_sec": self.cfg.flush_pause_sec,
            "blacklist": ", ".join(self.cfg.blacklist),
            "sessionid": self.cfg.sessionid,
            "steam_login_secure": self.cfg.steam_login_secure,
            "whitelist_mode": self.cfg.whitelist_mode,
            "whitelist": list(self.cfg.whitelist),
            "language": normalize_lang(self.cfg.language),
        }

    def state(self) -> dict[str, Any]:
        queue_n = self._games if str(self._games).isdigit() else None
        if self.cfg.whitelist_mode:
            banned = {str(x) for x in self.cfg.blacklist}
            queue_n = sum(1 for x in self.cfg.whitelist if str(x) not in banned)
        return {
            "version": __version__,
            "authed": self._authed,
            "persona_name": self.cfg.persona_name or "Steam User",
            "avatar_data_url": self._avatar_data_url,
            "profile_url": self.cfg.profile_url or "",
            "status": self._status,
            "games": self._games,
            "cards": self._cards,
            "drops": self._drops,
            "drops_text": self._drops_text,
            "farming": self._farming,
            "busy": self._busy,
            "busy_msg": self._busy_msg,
            "error": self._error,
            "cfg": self._cfg_public(),
            "log": self.get_log(),
            "plan": {
                "fast_mode": self.cfg.fast_mode,
                "max_simultaneous": self.cfg.max_simultaneous,
                "queue_count": queue_n,
                "whitelist_mode": self.cfg.whitelist_mode,
            },
        }

    def push(self) -> None:
        if not self._window:
            return
        payload = json.dumps(self.state(), ensure_ascii=False)
        try:
            self._window.evaluate_js(f"window.applyState && window.applyState({payload})")
        except Exception:
            pass

    def _set_busy(self, busy: bool, error: str = "", msg: str = "") -> None:
        self._busy = busy
        self._busy_msg = msg if busy else ""
        if error or not busy:
            self._error = error
        self.push()

    def _load_avatar(self, url: str) -> None:
        self._avatar_data_url = ""
        if not url:
            return
        try:
            http = make_http()
            resp = http.get(url, timeout=15)
            resp.raise_for_status()
            b64 = base64.b64encode(resp.content).decode("ascii")
            ctype = resp.headers.get("Content-Type", "image/jpeg").split(";")[0]
            self._avatar_data_url = f"data:{ctype};base64,{b64}"
        except Exception as exc:
            self.log(f"Avatar load failed: {exc}")
            self._avatar_data_url = ""

    def _on_authed(self) -> None:
        self.cfg = AppConfig.load()
        self._authed = True
        self._error = ""
        self._busy = False
        self._busy_msg = ""
        self._invalidate_badges_cache()
        self.log(f"Authed as {self.cfg.persona_name or '?'} ({self.cfg.profile_url})")
        self._load_avatar(self.cfg.avatar_url)
        self._refresh_queue_stats()
        self.push()

    def _invalidate_badges_cache(self) -> None:
        with self._badges_cv:
            self._badges_cache = None
            self._badges_cache_ts = 0.0

    def _badges_cache_fresh(self) -> bool:
        return (
            self._badges_cache is not None
            and (time.time() - self._badges_cache_ts) < BADGES_CACHE_TTL_SEC
        )

    def _fetch_badges_cached(
        self,
        *,
        force: bool = False,
    ) -> tuple[list[Badge], bool, bool]:
        """Return unfiltered badges (from_network, stale).

        Single-flight: concurrent callers wait for one Steam scrape.
        On network failure, returns stale cache if available.
        """
        with self._badges_cv:
            if not force and self._badges_cache_fresh():
                return list(self._badges_cache or []), False, False
            while self._badges_fetching:
                self._badges_cv.wait(timeout=180)
                if not force and self._badges_cache_fresh():
                    return list(self._badges_cache or []), False, False
            if not force and self._badges_cache_fresh():
                return list(self._badges_cache or []), False, False
            self._badges_fetching = True

        try:
            session = build_session(self.cfg)
            badges = fetch_badges(
                session,
                self.cfg,
                honor_whitelist=False,
                honor_blacklist=False,
            )
            with self._badges_cv:
                self._badges_cache = list(badges)
                self._badges_cache_ts = time.time()
            return badges, True, False
        except Exception:
            with self._badges_cv:
                stale = self._badges_cache
            if stale is not None:
                return list(stale), False, True
            raise
        finally:
            with self._badges_cv:
                self._badges_fetching = False
                self._badges_cv.notify_all()

    def _filter_badges_for_farm(self, badges: list[Badge]) -> list[Badge]:
        """Apply whitelist/blacklist the same way as fetch_badges(..., honor=True)."""
        banned = {str(x) for x in self.cfg.blacklist}
        out = [b for b in badges if str(b.app_id) not in banned]
        if self.cfg.whitelist_mode:
            if not self.cfg.whitelist:
                return []
            allowed = {str(x) for x in self.cfg.whitelist}
            out = [b for b in out if str(b.app_id) in allowed]
        return out

    def _games_payload_from_badges(self, badges: list[Badge]) -> list[dict[str, Any]]:
        banned = {str(x) for x in self.cfg.blacklist}
        selected = (
            {str(x) for x in self.cfg.whitelist}
            if self.cfg.whitelist_mode and self.cfg.whitelist
            else None
        )
        live: dict[int, int] = dict(self._drop_counts)
        if self.orch:
            session_counts: dict[int, int] = {}
            for d in self.orch.drops.history:
                session_counts[d.app_id] = session_counts.get(d.app_id, 0) + max(
                    1, d.count
                )
            for aid, cnt in session_counts.items():
                live[aid] = max(live.get(aid, 0), cnt)

        games: list[dict[str, Any]] = []
        for b in badges:
            aid = str(b.app_id)
            is_banned = aid in banned
            if selected is None:
                is_selected = not is_banned
            else:
                is_selected = (not is_banned) and aid in selected
            games.append(
                {
                    "app_id": b.app_id,
                    "name": b.name,
                    "remaining": b.remaining,
                    "obtained": live.get(b.app_id, 0),
                    "hours": b.hours,
                    "selected": is_selected,
                    "blacklisted": is_banned,
                    "icon": (
                        f"https://cdn.cloudflare.steamstatic.com/steam/apps/"
                        f"{b.app_id}/capsule_184x69.jpg"
                    ),
                }
            )
        return games

    def _refresh_queue_stats(self) -> None:
        def work() -> None:
            self._set_busy(True, msg=self._t("queue_refresh"))
            try:
                raw, from_net, stale = self._fetch_badges_cached(force=False)
                badges = self._filter_badges_for_farm(raw)
                self._games = str(len(badges))
                self._cards = str(total_drops(badges))
                if not self._farming:
                    self._status = self._t("ready")
                self._error = ""
                tag = "network" if from_net else ("stale" if stale else "cache")
                self.log(
                    f"Queue ({tag}): {len(badges)} games, "
                    f"{total_drops(badges)} cards remaining"
                )
            except Exception as exc:
                self._status = str(exc)[:120]
                self._games, self._cards = "—", "—"
                self.log(f"Queue refresh error: {exc}")
            finally:
                self._set_busy(False)

        threading.Thread(target=work, daemon=True).start()

    def ready(self) -> dict[str, Any]:
        if self._authed:
            threading.Thread(target=self._boot_resume, daemon=True).start()
        return self.state()

    def get_state(self) -> dict[str, Any]:
        return self.state()

    def open_profile(self) -> bool:
        url = (self.cfg.profile_url or "").rstrip("/")
        if not url:
            self.log("open_profile: no profile_url")
            return False
        steam_url = f"steam://openurl/{url}"
        self.log(f"Open profile: {steam_url}")
        try:
            webbrowser.open(steam_url)
            return True
        except Exception as exc:
            self.log(f"open_profile failed: {exc}")
            try:
                webbrowser.open(url)
                return True
            except Exception:
                return False

    def _boot_resume(self) -> None:
        self._set_busy(True, msg=self._t("checking_session"))
        self._status = self._t("checking_session")
        self.push()
        try:
            session = build_session(self.cfg, force_browser=False)
            self.cfg.persona_name = session.persona_name or self.cfg.persona_name
            self.cfg.avatar_url = session.avatar_url or self.cfg.avatar_url
            self.cfg.profile_url = session.profile_url or self.cfg.profile_url
            self.cfg.save()
            self._on_authed()
        except Exception as exc:
            self._authed = False
            self._set_busy(False, str(exc))
            self._status = self._t("login_needed")
            self.log(f"Session resume failed: {exc}")
            self.push()

    def steam_login(self) -> dict[str, Any]:
        if self._busy:
            return self.state()

        def work() -> None:
            self._set_busy(True, msg=self._t("auth"))
            self._status = self._t("waiting_login")
            self.log("Steam login started")
            self.push()
            try:
                sid, login = login_with_steam(on_log=self.log)
                session = apply_captured_cookies(self.cfg, sid, login)
                self.cfg.persona_name = session.persona_name or self.cfg.persona_name
                self.cfg.avatar_url = session.avatar_url or self.cfg.avatar_url
                self.cfg.save()
                self._on_authed()
            except Exception as exc:
                self.log(f"Steam login error: {exc}")
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()
        return self.state()

    def browser_cookies(self) -> dict[str, Any]:
        if self._busy:
            return self.state()

        def work() -> None:
            self._set_busy(True, msg=self._t("reading_cookies"))
            self._status = self._t("reading_cookies")
            self.log("Reading browser cookies")
            self.push()
            try:
                self.cfg.auto_browser_cookies = True
                session = build_session(self.cfg, force_browser=True)
                self.cfg.persona_name = session.persona_name or self.cfg.persona_name
                self.cfg.avatar_url = session.avatar_url or self.cfg.avatar_url
                self.cfg.save()
                self._on_authed()
            except Exception as exc:
                self.log(f"Browser cookies error: {exc}")
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()
        return self.state()

    def cookie_login(self, sessionid: str, steam_login_secure: str) -> dict[str, Any]:
        if self._busy:
            return self.state()

        def work() -> None:
            self._set_busy(True, msg=self._t("checking_cookies"))
            self._status = self._t("checking_cookies")
            self.log("Manual cookie login")
            self.push()
            try:
                self.cfg.sessionid = (sessionid or "").strip()
                self.cfg.steam_login_secure = (steam_login_secure or "").strip()
                self.cfg.auto_browser_cookies = False
                session = build_session(self.cfg, force_browser=False)
                self.cfg.persona_name = session.persona_name or self.cfg.persona_name
                self.cfg.avatar_url = session.avatar_url or self.cfg.avatar_url
                self.cfg.save()
                self._on_authed()
            except Exception as exc:
                self.log(f"Cookie login error: {exc}")
                self._set_busy(False, str(exc))

        threading.Thread(target=work, daemon=True).start()
        return self.state()

    def list_games(self, force: Any = False) -> dict[str, Any]:
        """All farmable badges + selection + blacklist flags + farm mode.

        Uses a short TTL cache and single-flight so tab switching does not
        hammer steamcommunity.com. Pass force=True to refresh from Steam.
        """
        do_force = bool(force)
        with self._badges_cv:
            cache_hit = not do_force and self._badges_cache_fresh()
        if not cache_hit:
            self._set_busy(True, msg=self._t("loading_games"))
        try:
            badges, from_net, stale = self._fetch_badges_cached(force=do_force)
            games = self._games_payload_from_badges(badges)
            self._games_cache = games
            tag = "network" if from_net else ("stale" if stale else "cache")
            self.log(f"Games list ({tag}): {len(games)}")
            out: dict[str, Any] = {
                "ok": True,
                "games": games,
                "whitelist_mode": self.cfg.whitelist_mode,
                "fast_mode": self.cfg.fast_mode,
                "max_simultaneous": self.cfg.max_simultaneous,
                "blacklist": list(self.cfg.blacklist),
                "cached": not from_net,
                "stale": stale,
            }
            if stale:
                out["warning"] = (
                    "Steam не ответил вовремя — показан предыдущий список."
                )
            return out
        except Exception as exc:
            self.log(f"list_games error: {exc}")
            return {
                "ok": False,
                "error": str(exc),
                "games": self._games_cache,
                "fast_mode": self.cfg.fast_mode,
                "max_simultaneous": self.cfg.max_simultaneous,
            }
        finally:
            if not cache_hit:
                self._set_busy(False)

    def save_farm_plan(self, payload: Any = None) -> dict[str, Any]:
        """Save selection + blacklist + Fast Mode + concurrency together."""
        if self._farming:
            self.log("Farm plan locked while farming")
            out = self.state()
            out["ok"] = False
            out["error"] = self._t("plan_locked")
            return out

        data: dict[str, Any]
        if isinstance(payload, list):
            data = {"app_ids": payload}
        else:
            data = dict(payload or {})

        app_ids = data.get("app_ids") or []
        ids = [str(x).strip() for x in app_ids if str(x).strip().isdigit()]

        if "blacklist" in data:
            raw_bl = data.get("blacklist") or []
            if isinstance(raw_bl, str):
                bl = [x.strip() for x in raw_bl.split(",") if x.strip().isdigit()]
            else:
                bl = [str(x).strip() for x in raw_bl if str(x).strip().isdigit()]
            self.cfg.blacklist = bl
            banned = set(bl)
            ids = [i for i in ids if i not in banned]

        farmable = {
            str(g["app_id"])
            for g in self._games_cache
            if str(g["app_id"]) not in set(self.cfg.blacklist)
        } if self._games_cache else set()

        if "fast_mode" in data:
            self.cfg.fast_mode = bool(data.get("fast_mode"))
        if "max_simultaneous" in data:
            try:
                self.cfg.max_simultaneous = max(
                    1, min(32, int(data.get("max_simultaneous")))
                )
            except (TypeError, ValueError):
                pass

        if farmable and set(ids) == farmable:
            self.cfg.whitelist_mode = False
            self.cfg.whitelist = []
            self.log("Farm plan: all non-blacklisted games")
        else:
            self.cfg.whitelist_mode = True
            self.cfg.whitelist = ids
            self.log(f"Farm plan: {len(ids)} games, blacklist={len(self.cfg.blacklist)}")

        mode = "Fast" if self.cfg.fast_mode else "Solo"
        self.log(
            f"Farm plan mode={mode} max={self.cfg.max_simultaneous} "
            f"selected={len(ids) if self.cfg.whitelist_mode else 'all'} "
            f"banned={len(self.cfg.blacklist)}"
        )
        self.cfg.save()
        self._refresh_queue_stats()
        self.push()
        return self.state()

    def toggle_farm(self) -> dict[str, Any]:
        if self._farming:
            self._stop_farm()
        else:
            self._start_farm()
        return self.state()

    def _start_farm(self) -> None:
        if not is_steam_running():
            self._status = self._t("steam_not_running")
            self.log(self._status)
            self.push()
            return
        if not find_steam_api_dll(find_steam_path(self.cfg.steam_path)):
            self._status = self._t("dll_missing")
            self._error = self._status
            self.log(self._status)
            self.push()
            return

        def on_status(st: FarmStatus) -> None:
            games = str(len(st.active_ids) or len(st.badges))
            if st.phase == Phase.FAST_MULTI:
                games = str(len(st.active_ids))
            self._games = games
            self._cards = str(st.total_remaining)
            self._drops = str(st.session_drops)
            self._status = st.message or st.phase.value
            if st.recent_drops:
                self._drops_text = "\n".join(
                    d.label() for d in reversed(st.recent_drops[-40:])
                )
            if st.phase in (Phase.DONE, Phase.ERROR, Phase.IDLE):
                self._farming = False
            self.push()

        def on_log(msg: str) -> None:
            self.log(msg)

        self.log("Farm start")
        seed: list = []
        with self._badges_cv:
            if self._badges_cache:
                seed = self._filter_badges_for_farm(list(self._badges_cache))
        self.orch = Orchestrator(
            self.cfg,
            on_log=on_log,
            on_status=on_status,
            seed_badges=seed or None,
        )
        self.orch.start_async()
        self._farming = True
        self._status = self._t("farm_start")
        self.push()

    def _stop_farm(self) -> None:
        self.log("Farm stop")
        if self.orch:
            try:
                self.orch.drops.save()
            except Exception:
                pass
            self.orch.stop()
            self._load_drop_counts()
        self._farming = False
        self._status = self._t("farm_stop")
        self.push()

    def copy_drops(self) -> str:
        text = self._drops_text or ""
        if self._window and text:
            try:
                self._window.evaluate_js(
                    "navigator.clipboard && navigator.clipboard.writeText("
                    + json.dumps(text)
                    + ")"
                )
            except Exception:
                pass
        return text

    def set_language(self, lang: str = "en") -> dict[str, Any]:
        self.cfg.language = normalize_lang(lang)
        self.cfg.save()
        self.push()
        return {"ok": True, "language": self.cfg.language, **self.state()}

    def save_settings(self, cfg: dict[str, Any]) -> dict[str, Any]:
        if self._farming:
            self.log("Settings locked while farming")
            out = self.state()
            out["ok"] = False
            out["error"] = self._t("settings_locked")
            return out

        self.cfg.skip_f2p = bool(cfg.get("skip_f2p", self.cfg.skip_f2p))
        self.cfg.sort = str(cfg.get("sort") or self.cfg.sort)
        if "language" in cfg:
            self.cfg.language = normalize_lang(str(cfg.get("language") or "en"))
        try:
            self.cfg.farm_wave_sec = max(120, int(cfg.get("farm_wave_sec", self.cfg.farm_wave_sec)))
        except (TypeError, ValueError):
            pass
        try:
            self.cfg.flush_pause_sec = max(
                5, int(cfg.get("flush_pause_sec", self.cfg.flush_pause_sec))
            )
        except (TypeError, ValueError):
            pass
        if "sessionid" in cfg:
            self.cfg.sessionid = str(cfg.get("sessionid") or "").strip()
        if "steam_login_secure" in cfg:
            self.cfg.steam_login_secure = str(cfg.get("steam_login_secure") or "").strip()
        self.cfg.save()
        self.log("Settings saved")
        self.push()
        return self.state()

    def logout(self) -> dict[str, Any]:
        if self._farming:
            self.log("Logout blocked while farming")
            out = self.state()
            out["ok"] = False
            out["error"] = self._t("logout_locked")
            return out

        self.log("Logout")
        if self.orch:
            self.orch.stop()
            self.orch = None
        self._farming = False
        self._invalidate_badges_cache()
        self._games_cache = []
        self.cfg.sessionid = ""
        self.cfg.steam_login_secure = ""
        self.cfg.persona_name = ""
        self.cfg.avatar_url = ""
        self.cfg.profile_url = ""
        self.cfg.save()
        self._authed = False
        self._avatar_data_url = ""
        self._games = self._cards = "—"
        self._drops = "0"
        self._drops_text = ""
        self._status = self._t("login_needed")
        self._error = ""
        self.push()
        return self.state()

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def close_app(self) -> None:
        if self.orch:
            self.orch.stop()
        if self._window:
            self._window.destroy()


def main() -> None:
    from .paths import resource_root
    from .session import _strip_socks_env

    _strip_socks_env()
    bridge = Bridge()
    index = (WEB_DIR / "index.html").as_uri()
    icon = resource_root() / "assets" / "icon.ico"
    window = webview.create_window(
        title="Steam Card Idle",
        url=index,
        js_api=bridge,
        width=460,
        height=680,
        min_size=(400, 560),
        background_color="#05070a",
        frameless=True,
        easy_drag=False,
        text_select=True,
    )
    bridge._window = window
    start_kw: dict = {"debug": False}
    if icon.is_file():
        start_kw["icon"] = str(icon)
    webview.start(**start_kw)


if __name__ == "__main__":
    main()
