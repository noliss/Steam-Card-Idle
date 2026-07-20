"""Interactive Steam login — opens Edge/Chrome and captures community cookies."""

from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote

from .config import DATA_DIR, ensure_dirs
from .session import SessionError, verify_community_cookies

LOGIN_URL = (
    "https://steamcommunity.com/login/home/"
    "?goto=https%3A%2F%2Fsteamcommunity.com%2Fmy%2F"
)
COMMUNITY_HOME = "https://steamcommunity.com/my/"

LogFn = Callable[[str], None]


def _mask(value: str, keep: int = 6) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "***"
    return f"{value[:keep]}...{value[-keep:]}(len={len(value)})"


def _normalize_login_secure(value: str) -> str:
    return unquote((value or "").strip())


def _pick_community_cookies(cookies: list[dict[str, Any]]) -> tuple[str, str, dict[str, str]]:
    """Prefer cookies scoped to steamcommunity.com. Returns (sessionid, login, debug)."""
    sessionid = ""
    login = ""
    sessionid_fallback = ""
    login_fallback = ""
    sessionid_domain = ""
    login_domain = ""

    for c in cookies:
        name = c.get("name") or ""
        value = (c.get("value") or "").strip()
        domain = (c.get("domain") or "").lower()
        if not value:
            continue
        is_community = "steamcommunity.com" in domain
        lname = name.lower()

        if lname == "sessionid":
            if is_community:
                sessionid = value
                sessionid_domain = domain
            elif not sessionid_fallback:
                sessionid_fallback = value
                if not sessionid_domain:
                    sessionid_domain = domain
        elif lname == "steamloginsecure":
            if is_community:
                login = value
                login_domain = domain
            elif not login_fallback:
                login_fallback = value
                if not login_domain:
                    login_domain = domain

    chosen_session = sessionid or sessionid_fallback
    chosen_login = _normalize_login_secure(login or login_fallback)
    debug = {
        "sessionid_domain": sessionid_domain,
        "login_domain": login_domain,
        "sessionid_from_community": bool(sessionid),
        "login_from_community": bool(login),
        "has_sessionid": bool(chosen_session),
        "has_login": bool(chosen_login),
        "sessionid": _mask(chosen_session),
        "login": _mask(chosen_login),
    }
    return chosen_session, chosen_login, debug


def _url_looks_logged_in(url: str) -> bool:
    u = (url or "").lower()
    if not u:
        return False
    if "steamcommunity.com" in u:
        if "/login" in u:
            return False
        return True
    # Sometimes Steam lands on store first
    if "store.steampowered.com" in u and "/login" not in u:
        return True
    return False


def _cookie_summary(cookies: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for c in cookies:
        name = c.get("name") or "?"
        domain = c.get("domain") or "?"
        val = c.get("value") or ""
        parts.append(f"{name}@{domain}[{_mask(val, 4)}]")
    return "; ".join(parts) if parts else "(none)"


def _launch_browser(playwright: Any, log: LogFn) -> Any:
    errors: list[str] = []
    for channel in ("msedge", "chrome", "msedge-beta", "chrome-beta"):
        try:
            log(f"[login] launching browser channel={channel}")
            browser = playwright.chromium.launch(
                channel=channel,
                headless=False,
                args=["--disable-blink-features=AutomationControlled"],
            )
            log(f"[login] browser started: {channel}")
            return browser
        except Exception as exc:
            errors.append(f"{channel}: {exc}")
            log(f"[login] channel {channel} failed: {exc}")

    try:
        log("[login] launching bundled chromium")
        browser = playwright.chromium.launch(headless=False)
        log("[login] browser started: chromium")
        return browser
    except Exception as exc:
        errors.append(f"chromium: {exc}")
        raise SessionError(
            "Не удалось запустить браузер для входа.\n"
            "Нужен установленный Microsoft Edge или Google Chrome.\n"
            + " | ".join(errors[:3])
        ) from exc


def login_with_steam(
    timeout_sec: float = 600.0,
    on_log: LogFn | None = None,
) -> tuple[str, str]:
    """
    Open Steam login in Edge/Chrome and return (sessionid, steamLoginSecure)
    for steamcommunity.com — verified against /my/ before returning.
    """
    ensure_dirs()
    log_path = DATA_DIR / "login_debug.log"
    try:
        log_path.write_text("", encoding="utf-8")
    except Exception:
        pass

    def log(msg: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"{stamp} {msg}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        if on_log:
            try:
                on_log(msg)
            except Exception:
                pass
        try:
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass

    log("[login] === Steam login start ===")
    log(f"[login] debug file: {log_path}")
    log(f"[login] timeout={timeout_sec}s")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        log("[login] playwright not installed")
        raise SessionError(
            "Нужен пакет playwright. Установи: pip install playwright"
        ) from exc

    with sync_playwright() as p:
        browser = _launch_browser(p, log)
        context = browser.new_context(
            viewport={"width": 1040, "height": 720},
            locale="ru-RU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
            ),
        )
        page = context.new_page()
        try:
            log(f"[login] goto {LOGIN_URL}")
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=120_000)
            log(f"[login] page loaded url={page.url}")
        except Exception as exc:
            log(f"[login] initial goto failed: {exc}")
            browser.close()
            raise SessionError(f"Не удалось открыть страницу входа Steam: {exc}") from exc

        deadline = time.time() + timeout_sec
        last_names: list[str] = []
        verified: tuple[str, str] | None = None
        opened_community = False
        last_url = ""
        tick = 0
        verify_fail_count = 0

        try:
            while time.time() < deadline:
                tick += 1
                if not browser.is_connected():
                    log("[login] browser disconnected")
                    break
                try:
                    if page.is_closed():
                        log("[login] page closed by user")
                        break
                    url = page.url or ""
                except Exception as exc:
                    log(f"[login] page.url error: {exc}")
                    break

                if url != last_url:
                    log(f"[login] url changed -> {url}")
                    last_url = url

                logged_in_url = _url_looks_logged_in(url)

                # Always inspect cookies — Steam may keep /login in URL briefly
                try:
                    cookies = context.cookies(["https://steamcommunity.com"])
                except Exception as exc:
                    log(f"[login] cookies(community) error: {exc}")
                    cookies = []
                try:
                    all_cookies = context.cookies()
                except Exception as exc:
                    log(f"[login] cookies(all) error: {exc}")
                    all_cookies = cookies

                sessionid, login, dbg = _pick_community_cookies(cookies)
                if not (sessionid and login):
                    sessionid, login, dbg = _pick_community_cookies(all_cookies)

                last_names = [str(c.get("name", "")) for c in all_cookies if c.get("name")]

                # Heartbeat every ~3s so GUI is never silent
                if tick == 1 or tick % 5 == 0:
                    log(
                        f"[login] tick={tick} logged_in_url={logged_in_url} "
                        f"cookies={len(all_cookies)} "
                        f"sessionid={dbg.get('has_sessionid')}({dbg.get('sessionid_domain')}) "
                        f"loginSecure={dbg.get('has_login')}({dbg.get('login_domain')}) "
                        f"url={url[:120]}"
                    )
                    if tick % 10 == 0 and all_cookies:
                        log(f"[login] cookie dump: {_cookie_summary(all_cookies)}")

                # If we already have both cookies — verify even before URL looks perfect
                if sessionid and login:
                    log(
                        f"[login] candidate cookies ready "
                        f"sessionid={_mask(sessionid)} login={_mask(login)} "
                        f"domains sess={dbg.get('sessionid_domain')} "
                        f"login={dbg.get('login_domain')}"
                    )
                    if not opened_community:
                        opened_community = True
                        try:
                            log(f"[login] opening community home {COMMUNITY_HOME}")
                            page.goto(
                                COMMUNITY_HOME,
                                wait_until="domcontentloaded",
                                timeout=60_000,
                            )
                            page.wait_for_timeout(1500)
                            log(f"[login] after community goto url={page.url}")
                            # refresh cookies after navigation
                            cookies = context.cookies(["https://steamcommunity.com"])
                            sessionid, login, dbg = _pick_community_cookies(cookies)
                            if not (sessionid and login):
                                sessionid, login, dbg = _pick_community_cookies(
                                    context.cookies()
                                )
                            log(
                                f"[login] cookies after community: "
                                f"session={dbg.get('has_sessionid')} "
                                f"login={dbg.get('has_login')} "
                                f"{_mask(sessionid)} / {_mask(login)}"
                            )
                        except Exception as exc:
                            log(f"[login] community goto failed: {exc}")
                            opened_community = False

                    if sessionid and login:
                        try:
                            log("[login] verifying cookies via requests -> /my/")
                            profile_url, steam_id = verify_community_cookies(
                                sessionid, login
                            )
                            log(
                                f"[login] VERIFY OK profile={profile_url} "
                                f"steamid={steam_id}"
                            )
                            verified = (sessionid, login)
                            break
                        except Exception as exc:
                            verify_fail_count += 1
                            log(f"[login] VERIFY FAIL #{verify_fail_count}: {exc}")
                            alt = _normalize_login_secure(unquote(login))
                            if alt != login:
                                try:
                                    log("[login] retry verify with normalized login")
                                    profile_url, steam_id = verify_community_cookies(
                                        sessionid, alt
                                    )
                                    log(
                                        f"[login] VERIFY OK (alt) profile={profile_url} "
                                        f"steamid={steam_id}"
                                    )
                                    verified = (sessionid, alt)
                                    break
                                except Exception as exc2:
                                    log(f"[login] VERIFY FAIL (alt): {exc2}")
                            if verify_fail_count >= 8:
                                log(
                                    "[login] too many verify failures — "
                                    "will keep waiting for fresher cookies"
                                )
                                verify_fail_count = 0
                            time.sleep(1.2)
                            continue

                # URL looks logged in but cookies incomplete — nudge to /my/
                if logged_in_url and not (sessionid and login) and not opened_community:
                    opened_community = True
                    try:
                        log("[login] url looks logged-in, nudging /my/ for cookies")
                        page.goto(
                            COMMUNITY_HOME,
                            wait_until="domcontentloaded",
                            timeout=60_000,
                        )
                        page.wait_for_timeout(1500)
                        log(f"[login] nudge done url={page.url}")
                    except Exception as exc:
                        log(f"[login] nudge failed: {exc}")
                        opened_community = False

                time.sleep(0.6)
        except Exception as exc:
            log(f"[login] loop crashed: {exc}")
            log(traceback.format_exc())
            raise
        finally:
            try:
                if browser.is_connected():
                    log("[login] closing browser")
                    browser.close()
            except Exception as exc:
                log(f"[login] browser close error: {exc}")

    if verified:
        log("[login] === Steam login success ===")
        return verified

    hint = (
        f" Seen cookies: {', '.join(last_names[:20])}."
        if last_names
        else " No cookies seen."
    )
    log(f"[login] === Steam login FAILED ==={hint}")
    log(f"[login] full log saved: {log_path}")
    raise SessionError(
        "Could not capture valid steamcommunity.com cookies after login."
        + hint
        + f" See log: {log_path}"
    )


def login_with_steam_subprocess(timeout_sec: float = 600.0) -> tuple[str, str]:
    import os
    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "steam_card_idle.steam_login",
        "--capture",
        "--timeout",
        str(int(timeout_sec)),
    ]
    root = Path(__file__).resolve().parent.parent
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec + 30,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        raise SessionError("Steam login timed out.") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    payload = None
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

    if not payload or not payload.get("ok"):
        err = (payload or {}).get("error") or stderr or stdout or f"exit {proc.returncode}"
        raise SessionError(f"Login failed: {err}")

    return str(payload["sessionid"]), str(payload["steam_login_secure"])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--capture" not in argv:
        print(
            "Usage: python -m steam_card_idle.steam_login --capture [--timeout 600]",
            file=sys.stderr,
        )
        return 2

    timeout = 600.0
    if "--timeout" in argv:
        i = argv.index("--timeout")
        if i + 1 < len(argv):
            timeout = float(argv[i + 1])

    try:
        sessionid, login = login_with_steam(timeout_sec=timeout)
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True),
            flush=True,
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "sessionid": sessionid,
                "steam_login_secure": login,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
