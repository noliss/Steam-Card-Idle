/* Steam Card Idle — web UI ↔ pywebview bridge */

const $ = (sel) => document.querySelector(sel);

const ui = {
  views: {
    login: $("#view-login"),
    main: $("#view-main"),
    settings: $("#view-settings"),
    games: $("#view-games"),
  },
  winTitle: $("#win-title"),
  version: $("#version"),
  loginError: $("#login-error"),
  altPanel: $("#alt-panel"),
  btnSteam: $("#btn-steam"),
  btnAlt: $("#btn-alt-toggle"),
  btnBrowser: $("#btn-browser"),
  btnCookie: $("#btn-cookie-save"),
  loginSession: $("#login-sessionid"),
  loginSecure: $("#login-secure"),
  persona: $("#persona"),
  avatar: $("#avatar"),
  btnFarm: $("#btn-farm"),
  pulse: $("#pulse"),
  status: $("#status-text"),
  planChip: $("#plan-chip"),
  mGames: $("#m-games"),
  mCards: $("#m-cards"),
  mDrops: $("#m-drops"),
  drops: $("#drops-list"),
  btnCopy: $("#btn-copy"),
  btnGames: $("#btn-games"),
  btnSettings: $("#btn-settings"),
  btnBack: $("#btn-back"),
  btnOpenPlan: $("#btn-open-plan"),
  settingsPlanSummary: $("#settings-plan-summary"),
  btnGamesBack: $("#btn-games-back"),
  btnGamesRefresh: $("#btn-games-refresh"),
  btnGamesAll: $("#btn-games-all"),
  btnGamesNone: $("#btn-games-none"),
  btnGamesSave: $("#btn-games-save"),
  gamesList: $("#games-list"),
  gamesEmpty: $("#games-empty"),
  planFast: $("#plan-fast"),
  planMax: $("#plan-max"),
  planMaxWrap: $("#plan-max-wrap"),
  planHint: $("#plan-hint"),
  planLock: $("#plan-lock"),
  settingsLock: $("#settings-lock"),
  btnSave: $("#btn-save"),
  btnLogout: $("#btn-logout"),
  btnMin: $("#btn-min"),
  btnClose: $("#btn-close"),
  logBox: $("#log-box"),
  btnLogCopy: $("#btn-log-copy"),
  btnLogClear: $("#btn-log-clear"),
  btnLogRefresh: $("#btn-log-refresh"),
  loader: $("#global-loader"),
  loaderText: $("#loader-text"),
  cfg: {
    lang: $("#cfg-lang"),
    f2p: $("#cfg-f2p"),
    sort: $("#cfg-sort"),
    farm: $("#cfg-farm"),
    flush: $("#cfg-flush"),
    session: $("#cfg-session"),
    login: $("#cfg-login"),
  },
};

let currentView = "login";
let altOpen = false;
let lastMetrics = { games: "", cards: "", drops: "" };
let bootDone = false;
let gamesData = [];
let lastPlan = { fast_mode: true, max_simultaneous: 20, queue_count: null };
let remoteBusy = false;
let remoteBusyText = "";
let localBusy = 0;
let localBusyText = "";
let isFarming = false;

function refreshLoader() {
  if (!ui.loader) return;
  const on = remoteBusy || localBusy > 0;
  ui.loader.hidden = !on;
  if (on) {
    ui.loaderText.textContent =
      localBusy > 0 ? localBusyText : remoteBusyText || t("loader.loading");
  }
}

function beginLocalBusy(text) {
  localBusy += 1;
  localBusyText = text || t("loader.loading");
  refreshLoader();
}

function endLocalBusy() {
  localBusy = Math.max(0, localBusy - 1);
  refreshLoader();
}

async function withLoader(text, fn) {
  beginLocalBusy(text);
  try {
    return await fn();
  } finally {
    endLocalBusy();
  }
}

function api() {
  return window.pywebview && window.pywebview.api;
}

function showView(name) {
  if (name === currentView) return;
  const prev = ui.views[currentView];
  const next = ui.views[name];
  if (prev) {
    prev.classList.add("is-leaving");
    prev.classList.remove("is-active");
    setTimeout(() => prev.classList.remove("is-leaving"), 220);
  }
  currentView = name;
  next.classList.add("is-active");
  const titles = {
    settings: t("title.settings"),
    games: t("title.games"),
    login: "Steam Card Idle",
    main: "Steam Card Idle",
  };
  ui.winTitle.textContent = titles[name] || "Steam Card Idle";
}

function fillSettings(cfg) {
  if (!cfg) return;
  if (ui.cfg.lang) ui.cfg.lang.value = cfg.language === "ru" ? "ru" : "en";
  ui.cfg.f2p.checked = !!cfg.skip_f2p;
  ui.cfg.sort.value = cfg.sort || "mostcards";
  ui.cfg.farm.value = cfg.farm_wave_sec ?? 120;
  ui.cfg.flush.value = cfg.flush_pause_sec ?? 15;
  ui.cfg.session.value = cfg.sessionid || "";
  ui.cfg.login.value = cfg.steam_login_secure || "";
}

function collectSettings() {
  return {
    language: ui.cfg.lang ? ui.cfg.lang.value : uiLang,
    skip_f2p: ui.cfg.f2p.checked,
    sort: ui.cfg.sort.value,
    farm_wave_sec: Number(ui.cfg.farm.value || 120),
    flush_pause_sec: Number(ui.cfg.flush.value || 15),
    sessionid: ui.cfg.session.value,
    steam_login_secure: ui.cfg.login.value,
  };
}

function flashMetric(el, value) {
  if (!el) return;
  el.textContent = value;
  const card = el.closest(".metric");
  if (!card) return;
  card.classList.remove("is-flash");
  void card.offsetWidth;
  card.classList.add("is-flash");
}

function formatPlanChip(plan, gamesFallback) {
  const fast = plan?.fast_mode !== false;
  const max = Math.max(1, Number(plan?.max_simultaneous) || 20);
  let queue = plan?.queue_count;
  if (queue == null || queue === "") queue = gamesFallback;
  const n = Number(queue);
  if (!Number.isFinite(n) || n < 0) {
    return fast ? t("plan.chip_fast_unk") : t("plan.chip_solo_unk");
  }
  if (!fast) return t("plan.chip_solo", { n });
  // Show configured cap only when the plan is larger than one wave
  if (n > max) return t("plan.chip_fast_cap", { n, parallel: max });
  return t("plan.chip_fast", { n });
}

function updatePlanChip(plan, gamesFallback) {
  if (!ui.planChip) return;
  lastPlan = { ...lastPlan, ...(plan || {}) };
  ui.planChip.textContent = formatPlanChip(lastPlan, gamesFallback);
  if (ui.settingsPlanSummary) {
    ui.settingsPlanSummary.textContent = formatPlanChip(lastPlan, gamesFallback);
  }
}

function syncPlanControls() {
  const fast = !!ui.planFast.checked;
  ui.planMaxWrap.classList.toggle("is-disabled", !fast);
  updatePlanHint();
}

function setPlanLocked(locked) {
  isFarming = !!locked;
  const gamesView = ui.views.games;
  if (gamesView) gamesView.classList.toggle("is-plan-locked", isFarming);
  if (ui.planLock) ui.planLock.hidden = !isFarming;

  const settingsView = ui.views.settings;
  if (settingsView) settingsView.classList.toggle("is-settings-locked", isFarming);
  if (ui.settingsLock) ui.settingsLock.hidden = !isFarming;

  if (ui.planFast) ui.planFast.disabled = isFarming;
  if (ui.planMax) ui.planMax.disabled = isFarming;
  if (ui.btnGamesRefresh) ui.btnGamesRefresh.disabled = isFarming;
  if (ui.btnGamesAll) ui.btnGamesAll.disabled = isFarming;
  if (ui.btnGamesNone) ui.btnGamesNone.disabled = isFarming;
  if (ui.btnGamesSave) {
    ui.btnGamesSave.disabled = isFarming;
    ui.btnGamesSave.classList.toggle("is-disabled", isFarming);
    const label = ui.btnGamesSave.querySelector(".btn__label");
    if (label) {
      label.textContent = isFarming ? t("plan.save_locked") : t("plan.save");
    }
  }

  const cfgFields = [
    ui.cfg.f2p,
    ui.cfg.sort,
    ui.cfg.farm,
    ui.cfg.flush,
    ui.cfg.session,
    ui.cfg.login,
  ];
  cfgFields.forEach((el) => {
    if (el) el.disabled = isFarming;
  });
  if (ui.btnSave) {
    ui.btnSave.disabled = isFarming;
    ui.btnSave.classList.toggle("is-disabled", isFarming);
    const label = ui.btnSave.querySelector(".btn__label");
    if (label) {
      label.textContent = isFarming ? t("settings.save_locked") : t("settings.save");
    }
  }
  if (ui.btnLogout) {
    ui.btnLogout.disabled = isFarming;
    ui.btnLogout.classList.toggle("is-disabled", isFarming);
    ui.btnLogout.title = isFarming ? t("settings.logout_tip") : "";
  }

  ui.gamesList.querySelectorAll("input[data-app]").forEach((el) => {
    const row = el.closest(".game-row");
    const banned = row && row.classList.contains("is-banned");
    el.disabled = isFarming || banned;
  });
  ui.gamesList.querySelectorAll(".ban-btn").forEach((el) => {
    el.disabled = isFarming;
  });

  const tip = isFarming ? t("plan.locked_tip") : t("plan.open_tip");
  if (ui.planChip) ui.planChip.title = tip;
  if (ui.btnGames) ui.btnGames.title = tip;
  if (ui.btnOpenPlan) ui.btnOpenPlan.title = tip;
  if (ui.btnSettings) {
    ui.btnSettings.title = isFarming
      ? t("settings.lock_title")
      : t("settings.nav_tip");
  }
}

function updatePlanHint() {
  const banned = blacklistedAppIds().length;
  const selected = selectedAppIds().length;
  const total = gamesData.length;
  const farmable = Math.max(0, total - banned);
  const fast = !!ui.planFast.checked;
  const max = Math.max(1, Math.min(32, Number(ui.planMax.value || 20)));
  const queue = selected || farmable;
  if (!total) {
    ui.planHint.innerHTML = t("plan.hint_empty");
    return;
  }
  const banBit = banned ? t("plan.ban_bit", { n: banned }) : "";
  if (fast) {
    const wave = Math.min(max, queue || 0);
    ui.planHint.innerHTML = t("plan.hint_fast", {
      n: selected || farmable,
      wave,
      ban: banBit,
    });
  } else {
    ui.planHint.innerHTML = t("plan.hint_solo", {
      n: selected || farmable,
      ban: banBit,
    });
  }
}

function renderGames(games) {
  gamesData = games || [];
  ui.gamesList.querySelectorAll(".game-row").forEach((n) => n.remove());
  if (!gamesData.length) {
    ui.gamesEmpty.hidden = false;
    ui.gamesEmpty.textContent = t("plan.empty");
    updatePlanHint();
    return;
  }
  ui.gamesEmpty.hidden = true;
  const frag = document.createDocumentFragment();
  gamesData.forEach((g) => {
    const banned = !!g.blacklisted;
    const row = document.createElement("div");
    row.className =
      "game-row" +
      (g.selected && !banned ? "" : " is-off") +
      (banned ? " is-banned" : "");
    row.innerHTML = `
      <input type="checkbox" data-app="${g.app_id}" ${
        g.selected && !banned ? "checked" : ""
      } ${banned ? "disabled" : ""} />
      <img class="game-row__art" src="${g.icon}" alt="" loading="lazy"
           onerror="this.style.opacity=0.25" />
      <div class="game-row__meta">
        <div class="game-row__name" title="${escapeHtml(g.name)}">${escapeHtml(g.name)}</div>
        <div class="game-row__stats">
          <span class="got">${t("plan.got")} <b>${g.obtained}</b></span>
          <span>${t("plan.left")} <b>${g.remaining}</b></span>
          ${banned ? '<span class="ban-tag">blacklist</span>' : ""}
        </div>
      </div>
      <button type="button" class="ban-btn ${banned ? "is-on" : ""}" data-ban="${g.app_id}"
        title="${banned ? t("plan.ban_off") : t("plan.ban_on")}">⛔</button>`;
    const cb = row.querySelector("input");
    cb.addEventListener("change", () => {
      if (isFarming) {
        cb.checked = !cb.checked;
        return;
      }
      row.classList.toggle("is-off", !cb.checked);
      updatePlanHint();
    });
    row.querySelector(".ban-btn").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleBan(String(g.app_id), row);
    });
    frag.appendChild(row);
  });
  ui.gamesList.appendChild(frag);
  updatePlanHint();
  setPlanLocked(isFarming);
}

function toggleBan(appId, row) {
  if (isFarming) return;
  const btn = row.querySelector(".ban-btn");
  const cb = row.querySelector("input");
  const on = !btn.classList.contains("is-on");
  btn.classList.toggle("is-on", on);
  row.classList.toggle("is-banned", on);
  cb.disabled = on;
  if (on) {
    cb.checked = false;
    row.classList.add("is-off");
    let tag = row.querySelector(".ban-tag");
    if (!tag) {
      tag = document.createElement("span");
      tag.className = "ban-tag";
      tag.textContent = "blacklist";
      row.querySelector(".game-row__stats").appendChild(tag);
    }
    btn.title = t("plan.ban_off");
  } else {
    const tag = row.querySelector(".ban-tag");
    if (tag) tag.remove();
    btn.title = t("plan.ban_on");
  }
  updatePlanHint();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function selectedAppIds() {
  return [...ui.gamesList.querySelectorAll("input[data-app]:checked:not(:disabled)")].map(
    (el) => el.getAttribute("data-app")
  );
}

function blacklistedAppIds() {
  return [...ui.gamesList.querySelectorAll(".ban-btn.is-on")].map((el) =>
    el.getAttribute("data-ban")
  );
}

window.applyLog = function applyLog(text) {
  if (ui.logBox) ui.logBox.textContent = text || "—";
};

window.applyState = function applyState(state) {
  if (!state) return;

  ui.version.textContent = `v${state.version || "—"}`;

  const steamLabel = ui.btnSteam.querySelector(".btn__label") || ui.btnSteam;
  if (state.busy) {
    ui.btnSteam.disabled = true;
    steamLabel.textContent = t("login.steam_wait");
    ui.btnBrowser.disabled = true;
    ui.btnCookie.disabled = true;
  } else {
    ui.btnSteam.disabled = false;
    steamLabel.textContent = t("login.steam");
    ui.btnBrowser.disabled = false;
    ui.btnCookie.disabled = false;
  }

  if (state.error) {
    ui.loginError.hidden = false;
    ui.loginError.textContent = state.error;
  } else {
    ui.loginError.hidden = true;
    ui.loginError.textContent = "";
  }

  ui.persona.textContent = state.persona_name || "Steam User";
  if (state.avatar_data_url) {
    ui.avatar.style.backgroundImage = `url("${state.avatar_data_url}")`;
  } else {
    ui.avatar.style.backgroundImage = "";
  }

  fillSettings(state.cfg);
  if (state.cfg && state.cfg.language) {
    setLang(state.cfg.language);
  } else {
    applyI18n();
  }
  if (ui.btnAlt) {
    ui.btnAlt.textContent = altOpen ? t("login.alt_hide") : t("login.alt");
  }

  // Dynamic fields after i18n — status must not be overwritten by data-i18n defaults.
  ui.status.textContent = state.status || t("main.status_ready");

  const g = String(state.games ?? "—");
  const c = String(state.cards ?? "—");
  const d = String(state.drops ?? "0");
  if (g !== lastMetrics.games) flashMetric(ui.mGames, g);
  else ui.mGames.textContent = g;
  if (c !== lastMetrics.cards) flashMetric(ui.mCards, c);
  else ui.mCards.textContent = c;
  if (d !== lastMetrics.drops) flashMetric(ui.mDrops, d);
  else ui.mDrops.textContent = d;
  lastMetrics = { games: g, cards: c, drops: d };

  ui.drops.textContent = state.drops_text || t("main.drops_empty");
  if (state.log != null) window.applyLog(state.log);

  const farmLabel = ui.btnFarm.querySelector(".btn__label") || ui.btnFarm;
  if (state.farming) {
    farmLabel.textContent = "STOP";
    ui.btnFarm.classList.add("is-stop", "is-live");
    ui.pulse.classList.add("is-live");
  } else {
    farmLabel.textContent = "START";
    ui.btnFarm.classList.remove("is-stop", "is-live");
    ui.pulse.classList.remove("is-live");
  }

  updatePlanChip(state.plan || state.cfg, g);
  setPlanLocked(!!state.farming);

  remoteBusy = !!state.busy;
  remoteBusyText = state.busy_msg || state.status || t("loader.loading");
  refreshLoader();

  if (state.authed) {
    if (currentView === "login") showView("main");
  } else if (currentView !== "login") {
    showView("login");
  }
};

async function call(name, ...args) {
  const a = api();
  if (!a || !a[name]) return null;
  return a[name](...args);
}

async function openGames(force = false) {
  showView("games");
  setPlanLocked(isFarming);
  if (isFarming) force = false;
  const hasLocal = gamesData.length > 0;

  if (hasLocal && !force) {
    renderGames(gamesData);
    ui.planFast.checked = lastPlan.fast_mode !== false;
    ui.planMax.value = lastPlan.max_simultaneous ?? 20;
    syncPlanControls();
    try {
      const res = await call("list_games", false);
      if (res && res.ok) {
        lastPlan.fast_mode = !!res.fast_mode;
        lastPlan.max_simultaneous = res.max_simultaneous ?? 20;
        ui.planFast.checked = !!res.fast_mode;
        ui.planMax.value = res.max_simultaneous ?? 20;
        syncPlanControls();
        renderGames(res.games);
      }
    } catch (_) {}
    return;
  }

  ui.gamesEmpty.hidden = false;
  ui.gamesEmpty.textContent = t("plan.loading");
  if (!hasLocal) {
    ui.gamesList.querySelectorAll(".game-row").forEach((n) => n.remove());
  }
  const res = await withLoader(t("loader.plan"), () =>
    call("list_games", !!force)
  );
  if (!res || !res.ok) {
    if (res && res.games && res.games.length) {
      lastPlan.fast_mode = res.fast_mode !== false;
      lastPlan.max_simultaneous = res.max_simultaneous ?? 20;
      ui.planFast.checked = lastPlan.fast_mode;
      ui.planMax.value = lastPlan.max_simultaneous;
      syncPlanControls();
      renderGames(res.games);
      ui.gamesEmpty.hidden = false;
      ui.gamesEmpty.textContent = (res && res.error) || t("plan.stale");
      return;
    }
    ui.gamesEmpty.textContent = (res && res.error) || t("plan.load_fail");
    ui.gamesEmpty.hidden = false;
    ui.planFast.checked = lastPlan.fast_mode !== false;
    ui.planMax.value = lastPlan.max_simultaneous ?? 20;
    syncPlanControls();
    return;
  }
  lastPlan.fast_mode = !!res.fast_mode;
  lastPlan.max_simultaneous = res.max_simultaneous ?? 20;
  ui.planFast.checked = !!res.fast_mode;
  ui.planMax.value = res.max_simultaneous ?? 20;
  syncPlanControls();
  renderGames(res.games);
}

function bind() {
  ui.btnMin.addEventListener("click", () => call("minimize"));
  ui.btnClose.addEventListener("click", () => call("close_app"));

  ui.btnSteam.addEventListener("click", () => call("steam_login"));
  ui.btnAlt.addEventListener("click", () => {
    altOpen = !altOpen;
    ui.altPanel.hidden = !altOpen;
    ui.btnAlt.textContent = altOpen ? t("login.alt_hide") : t("login.alt");
  });
  ui.btnBrowser.addEventListener("click", () => call("browser_cookies"));
  ui.btnCookie.addEventListener("click", () =>
    call("cookie_login", ui.loginSession.value, ui.loginSecure.value)
  );

  ui.avatar.addEventListener("click", () => call("open_profile"));
  ui.btnFarm.addEventListener("click", () => call("toggle_farm"));
  ui.btnCopy.addEventListener("click", async () => {
    const text = await call("copy_drops");
    if (text && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {}
    }
    ui.btnCopy.classList.add("is-copied");
    ui.btnCopy.textContent = t("main.copied");
    setTimeout(() => {
      ui.btnCopy.classList.remove("is-copied");
      ui.btnCopy.textContent = t("main.copy");
    }, 1200);
  });
  ui.btnGames.addEventListener("click", () => openGames(false));
  if (ui.btnOpenPlan) ui.btnOpenPlan.addEventListener("click", () => openGames(false));
  ui.btnGamesBack.addEventListener("click", () => showView("main"));
  if (ui.btnGamesRefresh) {
    ui.btnGamesRefresh.addEventListener("click", () => openGames(true));
  }
  ui.planChip.addEventListener("click", () => openGames(false));
  ui.planFast.addEventListener("change", syncPlanControls);
  ui.planMax.addEventListener("input", updatePlanHint);

  ui.btnGamesAll.addEventListener("click", () => {
    if (isFarming) return;
    ui.gamesList.querySelectorAll("input[data-app]:not(:disabled)").forEach((el) => {
      el.checked = true;
      el.closest(".game-row").classList.remove("is-off");
    });
    updatePlanHint();
  });
  ui.btnGamesNone.addEventListener("click", () => {
    if (isFarming) return;
    ui.gamesList.querySelectorAll("input[data-app]:not(:disabled)").forEach((el) => {
      el.checked = false;
      el.closest(".game-row").classList.add("is-off");
    });
    updatePlanHint();
  });
  ui.btnGamesSave.addEventListener("click", async () => {
    if (isFarming) return;
    const label = ui.btnGamesSave.querySelector(".btn__label");
    if (label) label.textContent = t("plan.saving");
    await withLoader(t("loader.save_plan"), () =>
      call("save_farm_plan", {
        app_ids: selectedAppIds(),
        blacklist: blacklistedAppIds(),
        fast_mode: !!ui.planFast.checked,
        max_simultaneous: Number(ui.planMax.value || 20),
      })
    );
    if (label) label.textContent = t("plan.save");
    showView("main");
  });

  ui.btnSettings.addEventListener("click", async () => {
    showView("settings");
    const log = await call("get_log");
    if (log != null) window.applyLog(log);
  });
  ui.btnBack.addEventListener("click", () => showView("main"));
  ui.btnSave.addEventListener("click", async () => {
    if (isFarming) return;
    await withLoader(t("loader.save_settings"), () =>
      call("save_settings", collectSettings())
    );
    showView("main");
  });
  ui.btnLogout.addEventListener("click", () => {
    if (isFarming) return;
    withLoader(t("loader.logout"), () => call("logout"));
  });

  if (ui.cfg.lang) {
    ui.cfg.lang.addEventListener("change", async () => {
      const lang = ui.cfg.lang.value === "ru" ? "ru" : "en";
      setLang(lang);
      updatePlanChip(lastPlan, lastMetrics.games);
      updatePlanHint();
      setPlanLocked(isFarming);
      await call("set_language", lang);
    });
  }

  ui.btnLogCopy.addEventListener("click", async () => {
    await call("copy_log");
    ui.btnLogCopy.textContent = t("main.copied");
    setTimeout(() => (ui.btnLogCopy.textContent = t("settings.log_copy")), 1200);
  });
  ui.btnLogClear.addEventListener("click", async () => {
    const log = await call("clear_log");
    window.applyLog(log);
  });
  ui.btnLogRefresh.addEventListener("click", async () => {
    const log = await call("get_log");
    window.applyLog(log);
  });

  document.querySelectorAll(".secret__toggle").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const id = btn.getAttribute("data-for");
      const input = id ? document.getElementById(id) : null;
      const wrap = btn.closest(".secret");
      if (!input || !wrap) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      wrap.classList.toggle("is-revealed", show);
      const eye = btn.querySelector(".icon-eye");
      const eyeOff = btn.querySelector(".icon-eye-off");
      if (eye) eye.hidden = show;
      if (eyeOff) eyeOff.hidden = !show;
      btn.setAttribute("aria-label", show ? t("login.alt_hide") : t("common.show"));
    });
  });
}

async function boot() {
  if (bootDone) return;
  bootDone = true;
  setLang("en");
  bind();
  beginLocalBusy(t("loader.loading"));
  try {
    for (let i = 0; i < 50; i++) {
      if (api()) break;
      await new Promise((r) => setTimeout(r, 50));
    }
    const state = (await call("ready")) || (await call("get_state"));
    if (state) window.applyState(state);
  } finally {
    endLocalBusy();
  }
}

window.addEventListener("pywebviewready", boot);
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => setTimeout(boot, 80));
} else {
  setTimeout(boot, 80);
}
