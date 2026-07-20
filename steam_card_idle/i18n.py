"""UI / status message catalogs (en default)."""

from __future__ import annotations

from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "ready": "Ready to start",
        "login_needed": "Sign in to continue",
        "waiting_login": "Waiting for Steam login…",
        "checking_session": "Checking saved session…",
        "reading_cookies": "Reading browser cookies…",
        "checking_cookies": "Checking cookies…",
        "queue_refresh": "Updating queue…",
        "loading_games": "Loading game list…",
        "saving_plan": "Saving plan…",
        "saving_settings": "Saving settings…",
        "logout": "Signing out…",
        "farm_start": "Starting…",
        "farm_stop": "Stopped",
        "steam_not_running": "Start the Steam client first",
        "dll_missing": (
            "Missing steam_api64.dll in native/ — download the full release "
            "or put the DLL into the native/ folder"
        ),
        "plan_locked": (
            "Can't change the farm plan while farming: idle already follows "
            "the current queue. Change games/blacklist/Fast Mode mid-run can "
            "break the wave. Stop first."
        ),
        "settings_locked": (
            "Can't change settings while farming: flush/cookies/filters are "
            "in use by idle. Stop first."
        ),
        "logout_locked": "Stop farming first — logout would kill the idle session.",
        "auth": "Signing in…",
        "reading_badges": "Reading badges…",
    },
    "ru": {
        "ready": "Готов к запуску",
        "login_needed": "Войди, чтобы продолжить",
        "waiting_login": "Ожидание входа…",
        "checking_session": "Проверка сохранённой сессии…",
        "reading_cookies": "Читаю cookies браузера…",
        "checking_cookies": "Проверка cookies…",
        "queue_refresh": "Обновляю очередь…",
        "loading_games": "Загружаю список игр…",
        "saving_plan": "Сохраняю план…",
        "saving_settings": "Сохраняю настройки…",
        "logout": "Выход…",
        # Farm / session activity strings stay English (same as logs & orchestrator).
        "farm_start": "Starting…",
        "farm_stop": "Stopped",
        "steam_not_running": "Start the Steam client first",
        "dll_missing": (
            "Missing steam_api64.dll in native/ — download the full release "
            "or put the DLL into the native/ folder"
        ),
        "plan_locked": (
            "Can't change the farm plan while farming: idle already follows "
            "the current queue. Change games/blacklist/Fast Mode mid-run can "
            "break the wave. Stop first."
        ),
        "settings_locked": (
            "Can't change settings while farming: flush/cookies/filters are "
            "in use by idle. Stop first."
        ),
        "logout_locked": "Stop farming first — logout would kill the idle session.",
        "auth": "Signing in…",
        "reading_badges": "Reading badges…",
    },
}


def normalize_lang(lang: str | None) -> str:
    value = (lang or "en").strip().lower()
    return value if value in MESSAGES else "en"


def t(lang: str | None, key: str, **kwargs: Any) -> str:
    pack = MESSAGES[normalize_lang(lang)]
    text = pack.get(key) or MESSAGES["en"].get(key) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
