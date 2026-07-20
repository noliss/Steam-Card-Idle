from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import requests

from .config import AppConfig

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
)


def _strip_socks_env() -> None:
    """Avoid 'Missing dependencies for SOCKS support' when OS sets socks:// proxies."""
    for key in list(os.environ):
        if "proxy" not in key.lower():
            continue
        val = (os.environ.get(key) or "").lower()
        if val.startswith("socks"):
            os.environ.pop(key, None)


def make_http() -> requests.Session:
    """requests.Session that ignores broken system SOCKS proxies."""
    _strip_socks_env()
    http = requests.Session()
    http.trust_env = False
    http.headers.update({"User-Agent": USER_AGENT})
    return http


def request_get(
    http: requests.Session,
    url: str,
    *,
    timeout: float | tuple[float, float] = (8, 35),
    retries: int = 3,
    backoff: float = 0.8,
    **kwargs,
) -> requests.Response:
    """GET with retries on timeouts / transient network errors."""
    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            resp = http.get(url, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except (
            requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.ChunkedEncodingError,
        ) as exc:
            last_exc = exc
            if attempt + 1 >= retries:
                break
            time.sleep(backoff * (attempt + 1))
        except requests.exceptions.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                last_exc = exc
                time.sleep(backoff * (attempt + 1) * 1.5)
                continue
            raise
    assert last_exc is not None
    raise last_exc


def normalize_login_secure(value: str) -> str:
    """Use decoded steamid||token form — avoids requests corrupting %7C%7C → %257C."""
    value = (value or "").strip()
    if not value:
        return value
    return unquote(value)


@dataclass
class SteamSession:
    sessionid: str
    steam_login_secure: str
    profile_url: str = ""
    steam_id64: str = ""
    persona_name: str = ""
    avatar_url: str = ""
    offline: bool = False

    def cookies(self) -> dict[str, str]:
        return {
            "sessionid": self.sessionid,
            "steamLoginSecure": self.steam_login_secure,
        }

    def apply_to(self, http: requests.Session) -> None:
        login = normalize_login_secure(self.steam_login_secure)
        # Direct Cookie header — jar re-encoding breaks steamLoginSecure (%7C → %257C).
        http.cookies.clear()
        cookie_header = f"sessionid={self.sessionid}; steamLoginSecure={login}"
        http.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cookie": cookie_header,
            }
        )

        original_send = http.send

        def send_with_cookie(request: requests.PreparedRequest, **kwargs):
            request.headers["Cookie"] = cookie_header
            return original_send(request, **kwargs)

        http.send = send_with_cookie  # type: ignore[method-assign]


class SessionError(RuntimeError):
    pass


def load_browser_cookies() -> tuple[str, str]:
    """Try to pull Steam community cookies from a logged-in browser."""
    try:
        import browser_cookie3
    except ImportError as exc:
        raise SessionError("browser-cookie3 is not installed") from exc

    loaders = [
        getattr(browser_cookie3, "chrome", None),
        getattr(browser_cookie3, "edge", None),
        getattr(browser_cookie3, "firefox", None),
        getattr(browser_cookie3, "brave", None),
        getattr(browser_cookie3, "opera", None),
    ]

    sessionid = ""
    login = ""
    for loader in loaders:
        if loader is None:
            continue
        try:
            jar = loader(domain_name="steamcommunity.com")
        except Exception:
            continue
        for cookie in jar:
            if cookie.name == "sessionid" and cookie.value:
                sessionid = cookie.value
            elif cookie.name == "steamLoginSecure" and cookie.value:
                login = cookie.value
        if sessionid and login:
            return sessionid, normalize_login_secure(login)

    raise SessionError(
        "Could not read cookies from the browser. "
        "Sign in on steamcommunity.com in Chrome/Edge and try again, "
        "or paste sessionid + steamLoginSecure manually."
    )


def resolve_profile(http: requests.Session) -> tuple[str, str, str, str]:
    """Return (profile_url, steam_id64, persona_name, avatar_url)."""
    resp = request_get(
        http,
        "https://steamcommunity.com/my/",
        allow_redirects=True,
        timeout=(12, 40),
        retries=4,
        backoff=1.0,
    )
    url = resp.url.rstrip("/")
    path = urlparse(url).path.lower()
    cookie_hdr = http.headers.get("Cookie", "")
    cookie_hint = f" cookie_header_len={len(cookie_hdr)} final_url={url}"
    if "/login" in path:
        raise SessionError(
            "Cookies invalid — Steam asks for login. "
            "Need cookies from steamcommunity.com (not the store)."
            + cookie_hint
        )

    match = re.search(r"(https://steamcommunity\.com/(?:profiles|id)/[^/?#]+)", url)
    if not match:
        raise SessionError(
            f"Could not resolve profile from URL: {url}.{cookie_hint} "
            f"status={resp.status_code} body_snip={resp.text[:160]!r}"
        )

    profile_url = match.group(1)
    steam_id64 = ""
    persona_name = ""
    avatar_url = ""

    xml = request_get(
        http,
        profile_url + "/?xml=1",
        timeout=(10, 35),
        retries=3,
        backoff=0.8,
    )
    text = xml.text
    sid = re.search(r"<steamID64>(\d+)</steamID64>", text)
    if sid:
        steam_id64 = sid.group(1)
        profile_url = f"https://steamcommunity.com/profiles/{steam_id64}"
    name_m = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]></steamID>", text)
    if not name_m:
        name_m = re.search(r"<steamID>([^<]+)</steamID>", text)
    if name_m:
        persona_name = name_m.group(1).strip()
    av = re.search(r"<avatarFull><!\[CDATA\[(.*?)\]\]></avatarFull>", text)
    if not av:
        av = re.search(r"<avatarFull>([^<]+)</avatarFull>", text)
    if av:
        avatar_url = av.group(1).strip()

    return profile_url, steam_id64, persona_name, avatar_url


def _steam_id_from_profile(profile_url: str) -> str:
    m = re.search(r"/profiles/(\d+)", profile_url or "")
    return m.group(1) if m else ""


def session_from_cfg(cfg: AppConfig, sessionid: str, login: str) -> SteamSession:
    """Build SteamSession using profile fields already stored in config."""
    profile_url = (cfg.profile_url or "").rstrip("/")
    if not profile_url:
        raise SessionError("No saved profile_url for offline session.")
    return SteamSession(
        sessionid=sessionid,
        steam_login_secure=login,
        profile_url=profile_url,
        steam_id64=_steam_id_from_profile(profile_url),
        persona_name=cfg.persona_name or "",
        avatar_url=cfg.avatar_url or "",
    )


def verify_community_cookies(sessionid: str, login: str) -> tuple[str, str]:
    """Return (profile_url, steam_id64) if cookies work for community."""
    http = make_http()
    steam = SteamSession(
        sessionid=sessionid.strip(),
        steam_login_secure=normalize_login_secure(login),
    )
    steam.apply_to(http)
    profile_url, steam_id64, _persona, _avatar = resolve_profile(http)
    return profile_url, steam_id64


def apply_captured_cookies(cfg: AppConfig, sessionid: str, login: str) -> SteamSession:
    """Save freshly captured cookies and resolve the profile URL."""
    cfg.sessionid = sessionid.strip()
    cfg.steam_login_secure = normalize_login_secure(login)
    cfg.auto_browser_cookies = False
    return build_session(cfg, force_browser=False)


def build_session(
    cfg: AppConfig,
    force_browser: bool = False,
    *,
    allow_offline: bool = True,
) -> SteamSession:
    sessionid = cfg.sessionid.strip()
    login = normalize_login_secure(cfg.steam_login_secure)

    if force_browser or (cfg.auto_browser_cookies and (not sessionid or not login)):
        try:
            sessionid, login = load_browser_cookies()
            cfg.sessionid = sessionid
            cfg.steam_login_secure = login
        except SessionError:
            if not sessionid or not login:
                raise

    if not sessionid or not login:
        raise SessionError(
            "No session. Click Sign in with Steam or run: "
            "python -m steam_card_idle setup --login"
        )

    http = make_http()
    steam = SteamSession(sessionid=sessionid, steam_login_secure=login)
    steam.apply_to(http)
    try:
        profile_url, steam_id64, persona_name, avatar_url = resolve_profile(http)
    except (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
    ) as exc:
        if allow_offline and (cfg.profile_url or "").strip():
            offline = session_from_cfg(cfg, sessionid, login)
            offline.offline = True
            cfg.sessionid = sessionid
            cfg.steam_login_secure = login
            cfg.save()
            return offline
        raise SessionError(
            f"Steam Community unavailable ({exc}). "
            "Check network/VPN and try again."
        ) from exc

    steam.profile_url = profile_url
    steam.steam_id64 = steam_id64
    steam.persona_name = persona_name
    steam.avatar_url = avatar_url
    cfg.profile_url = profile_url
    cfg.persona_name = persona_name
    cfg.avatar_url = avatar_url
    cfg.sessionid = sessionid
    cfg.steam_login_secure = login
    cfg.save()
    return steam


def http_client(session: SteamSession) -> requests.Session:
    http = make_http()
    session.apply_to(http)
    return http
