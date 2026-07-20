/* Steam Card Idle — EN/RU strings */

const I18N = {
  en: {
    "loader.loading": "Loading…",
    "login.lede": "Neon trading-card farming — fast, clean, quiet",
    "login.steam": "Sign in with Steam",
    "login.steam_wait": "Waiting for login…",
    "login.alt": "Other sign-in methods",
    "login.alt_hide": "Hide",
    "login.alt_hint": "Cookies · steamcommunity.com",
    "login.browser": "From browser",
    "login.continue": "Continue",
    "main.profile_title": "Open Steam profile",
    "main.games_title": "Game list",
    "main.settings_aria": "Settings",
    "main.plan_title": "Open farm plan",
    "main.metric_games": "games",
    "main.metric_cards": "cards",
    "main.metric_drops": "drops",
    "main.feed_title": "Recent drops",
    "main.copy": "Copy",
    "main.copied": "Copied",
    "main.drops_empty": "Nothing yet.",
    "main.status_ready": "Ready to start",
    "plan.title": "Farm plan",
    "plan.refresh": "Refresh from Steam",
    "plan.all": "All",
    "plan.none": "None",
    "plan.lock_title": "Can't edit the plan while farming",
    "plan.lock_body":
      "Idle is already running on the current plan. Changing games, blacklist, or Fast Mode mid-run can break the wave or start the wrong titles. Stop farming first, then edit freely.",
    "plan.how": "How to farm",
    "plan.fast_sub": "Idle several games at once",
    "plan.max": "Simultaneous",
    "plan.legend": "✓ farm · ⛔ never (blacklist)",
    "plan.hint_empty": "Load the game list — your full farm plan builds here.",
    "plan.hint_fast": "Farming {n} · up to {wave} at once{ban}",
    "plan.hint_solo": "Solo: one at a time from {n} · flush like Fast{ban}",
    "plan.ban_bit": " · ⛔ {n}",
    "plan.save": "Save plan",
    "plan.save_locked": "Stop farming first",
    "plan.saving": "Saving…",
    "plan.loading": "Loading list…",
    "plan.empty": "No games with drops",
    "plan.load_fail": "Couldn't load",
    "plan.stale": "Steam didn't respond — showing cache",
    "plan.chip_fast": "Fast · {n} in plan",
    "plan.chip_fast_cap": "Fast · {n} in plan · {parallel} at once",
    "plan.chip_solo": "Solo · {n} in plan",
    "plan.chip_fast_unk": "Fast Mode",
    "plan.chip_solo_unk": "Solo Mode",
    "plan.locked_tip":
      "Plan locked: stop farming first — changing the list mid-run breaks the idle queue",
    "plan.open_tip": "Open farm plan",
    "plan.ban_on": "Never farm",
    "plan.ban_off": "Remove from blacklist",
    "plan.got": "got",
    "plan.left": "left",
    "settings.title": "Settings",
    "settings.lock_title": "Can't change settings while farming",
    "settings.lock_body":
      "Flush timings, cookies, and queue filters are already used by idle. Changing them mid-run can break the wave or drop tracking. Stop farming, then save settings.",
    "settings.sec_farm": "Farm",
    "settings.sec_flush": "Flush wave",
    "settings.sec_session": "Session",
    "settings.sec_log": "Log",
    "settings.sec_lang": "Language",
    "settings.sec_author": "Author",
    "settings.author_label": "Telegram",
    "settings.repo_label": "GitHub",
    "settings.repo_sum": "Source code & releases",
    "settings.lang": "Interface language",
    "settings.plan_link": "Farm plan",
    "settings.plan_sum": "Fast Mode, limit, and game picks — in one place",
    "settings.f2p": "Skip Free-to-Play",
    "settings.f2p_tip":
      "Many F2P titles don't drop cards without purchases — without this filter the queue fills with duds.",
    "settings.sort": "Queue sort",
    "settings.sort_tip":
      "mostcards — most cards first; leastcards — almost finished; default — Steam badge order.",
    "settings.farm_sec": "Farm until flush (sec)",
    "settings.farm_tip":
      "How long to idle before a flush (Fast and Solo). Steam often credits cards when sessions end. Default 300 s (5 min).",
    "settings.flush_sec": "Flush pause (sec)",
    "settings.flush_tip":
      "Pause after stopping games so Steam can credit drops. Usually 10–20 s.",
    "settings.session_tip":
      "sessionid cookie from steamcommunity.com for badges and inventory.",
    "settings.login_tip":
      "Main Community auth cookie. Stored locally in config.json.",
    "settings.log_hint": "Full debug log for issues. You can copy it all.",
    "settings.log_copy": "Copy log",
    "settings.log_clear": "Clear",
    "settings.log_refresh": "Refresh",
    "settings.save": "Save",
    "settings.save_locked": "Stop farming first",
    "settings.saving": "Saving settings…",
    "settings.logout": "Sign out",
    "settings.logout_tip": "Stop farming first — logout kills the idle session",
    "settings.nav_tip": "Settings",
    "title.settings": "Settings",
    "title.games": "Farm plan",
    "common.back": "Back",
    "common.min": "Minimize",
    "common.close": "Close",
    "common.show": "Show / hide",
    "loader.plan": "Loading game list…",
    "loader.save_plan": "Saving plan…",
    "loader.save_settings": "Saving settings…",
    "loader.logout": "Signing out…",
  },
  ru: {
    "loader.loading": "Загрузка…",
    "login.lede": "Неоновый фарм trading cards — быстро, чисто, без шума",
    "login.steam": "Войти через Steam",
    "login.steam_wait": "Ожидание входа…",
    "login.alt": "Другой способ входа",
    "login.alt_hide": "Скрыть",
    "login.alt_hint": "Cookies · steamcommunity.com",
    "login.browser": "Из браузера",
    "login.continue": "Продолжить",
    "main.profile_title": "Открыть профиль в Steam",
    "main.games_title": "Список игр",
    "main.settings_aria": "Настройки",
    "main.plan_title": "Открыть план фарма",
    "main.metric_games": "игр",
    "main.metric_cards": "карт",
    "main.metric_drops": "дропов",
    "main.feed_title": "Последние дропы",
    "main.copy": "Копировать",
    "main.copied": "Скопировано",
    "main.drops_empty": "Пока пусто.",
    "main.status_ready": "Готов к запуску",
    "plan.title": "План фарма",
    "plan.refresh": "Обновить с Steam",
    "plan.all": "Все",
    "plan.none": "Ничего",
    "plan.lock_title": "План нельзя менять во время фарма",
    "plan.lock_body":
      "Оркестратор уже запустил idle по текущему плану. Смена списка игр, blacklist или Fast Mode на лету может оборвать волну, сбросить очередь или запустить не те игры. Останови фарм — и правь план спокойно.",
    "plan.how": "Как фармить",
    "plan.fast_sub": "Несколько игр в idle сразу",
    "plan.max": "Одновременно",
    "plan.legend": "✓ фармить · ⛔ никогда (blacklist)",
    "plan.hint_empty": "Загрузи список игр — здесь сложится весь план фарма.",
    "plan.hint_fast": "В фарме {n} · сразу до {wave}{ban}",
    "plan.hint_solo": "Solo: по одной из {n} · flush как в Fast{ban}",
    "plan.ban_bit": " · ⛔ {n}",
    "plan.save": "Сохранить план",
    "plan.save_locked": "Сначала останови фарм",
    "plan.saving": "Сохранение…",
    "plan.loading": "Загрузка списка…",
    "plan.empty": "Нет игр с дропами",
    "plan.load_fail": "Не удалось загрузить",
    "plan.stale": "Steam не ответил — показан кэш",
    "plan.chip_fast": "Fast · в плане {n}",
    "plan.chip_fast_cap": "Fast · в плане {n} · сразу по {parallel}",
    "plan.chip_solo": "Solo · в плане {n}",
    "plan.chip_fast_unk": "Fast Mode",
    "plan.chip_solo_unk": "Solo Mode",
    "plan.locked_tip":
      "План заблокирован: сначала останови фарм — смена списка на лету ломает очередь idle",
    "plan.open_tip": "Открыть план фарма",
    "plan.ban_on": "Никогда не фармить",
    "plan.ban_off": "Убрать из blacklist",
    "plan.got": "получено",
    "plan.left": "осталось",
    "settings.title": "Настройки",
    "settings.lock_title": "Настройки нельзя менять во время фарма",
    "settings.lock_body":
      "Flush timings, cookies и фильтры очереди уже используются текущим idle. Смена на лету может сбить волну, сессию или чтение дропов. Останови фарм — потом сохраняй настройки.",
    "settings.sec_farm": "Фарм",
    "settings.sec_flush": "Flush wave",
    "settings.sec_session": "Сессия",
    "settings.sec_log": "Лог",
    "settings.sec_lang": "Язык",
    "settings.sec_author": "Автор",
    "settings.author_label": "Telegram",
    "settings.repo_label": "GitHub",
    "settings.repo_sum": "Исходники и релизы",
    "settings.lang": "Язык интерфейса",
    "settings.plan_link": "План фарма",
    "settings.plan_sum": "Fast Mode, лимит и выбор игр — в одном месте",
    "settings.f2p": "Пропускать Free-to-Play",
    "settings.f2p_tip":
      "У многих F2P карты не падают без покупок — без фильтра очередь забивается пустышками.",
    "settings.sort": "Сортировка очереди",
    "settings.sort_tip":
      "mostcards — больше карт сначала; leastcards — почти дофармленные; default — как на бейджах Steam.",
    "settings.farm_sec": "Фарм до сброса волны (сек)",
    "settings.farm_tip":
      "Сколько секунд idle до flush (и Fast, и Solo). Steam часто зачисляет карты при закрытии сессии. По умолчанию 300 с (5 мин).",
    "settings.flush_sec": "Пауза после сброса (сек)",
    "settings.flush_tip":
      "Пауза после остановки игр, чтобы Steam успел зачислить дропы. Обычно 10–20 с.",
    "settings.session_tip":
      "Cookie sessionid с steamcommunity.com для чтения бейджей и инвентаря.",
    "settings.login_tip":
      "Основная авторизация Community. Хранится локально в config.json.",
    "settings.log_hint": "Полный лог для дебага и issue. Можно копировать целиком.",
    "settings.log_copy": "Копировать лог",
    "settings.log_clear": "Очистить",
    "settings.log_refresh": "Обновить",
    "settings.save": "Сохранить",
    "settings.save_locked": "Сначала останови фарм",
    "settings.saving": "Сохраняю настройки…",
    "settings.logout": "Выйти из аккаунта",
    "settings.logout_tip": "Сначала останови фарм — выход оборвёт сессию idle",
    "settings.nav_tip": "Настройки",
    "title.settings": "Настройки",
    "title.games": "План фарма",
    "common.back": "Назад",
    "common.min": "Свернуть",
    "common.close": "Закрыть",
    "common.show": "Показать / скрыть",
    "loader.plan": "Загружаю список игр…",
    "loader.save_plan": "Сохраняю план…",
    "loader.save_settings": "Сохраняю настройки…",
    "loader.logout": "Выход…",
  },
};

let uiLang = "en";

function t(key, vars) {
  const pack = I18N[uiLang] || I18N.en;
  let s = pack[key] ?? I18N.en[key] ?? key;
  if (vars) {
    Object.keys(vars).forEach((k) => {
      s = s.split(`{${k}}`).join(String(vars[k]));
    });
  }
  return s;
}

function setLang(lang) {
  uiLang = lang === "ru" ? "ru" : "en";
  applyI18n();
}

function applyI18n() {
  document.documentElement.lang = uiLang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (!key) return;
    const attr = el.getAttribute("data-i18n-attr");
    const value = t(key);
    if (attr) el.setAttribute(attr, value);
    else el.textContent = value;
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    if (key) el.innerHTML = t(key);
  });
  document.querySelectorAll("[data-i18n-tip]").forEach((el) => {
    const key = el.getAttribute("data-i18n-tip");
    if (key) el.setAttribute("data-tip", t(key));
  });
}
