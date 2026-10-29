"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const ROWS = ["melee", "ranged", "siege"];
  const ROW_NAMES = {melee: "Ближний бой", ranged: "Дальний бой", siege: "Осада"};
  const ROW_GLYPHS = {melee: "⚔", ranged: "➶", siege: "♜"};
  const WEATHER = {frost: ["melee"], fog: ["ranged"], rain: ["siege"], storm: ["ranged", "siege"]};
  const EFFECT_TEXT = {
    spy: "Выходит на сторону соперника и даёт вам две карты из колоды.",
    medic: "Возвращает выбранный отряд из вашего сброса. Герои недоступны.",
    bond: "Базовая сила умножается на число одинаковых отрядов в вашем ряду.",
    morale: "Добавляет 1 к силе других ваших отрядов в ряду, кроме героев.",
    muster: "Призывает связанные отряды из вашей руки и колоды.",
    horn: "Удваивает силу других ваших отрядов в ряду. Эффекты штандартов не складываются.",
    mushroom: "Обращает Берсерков своего ряда во вторую форму.",
    berserker: "Мухомор обращает отряд во вторую форму. Превращение сохраняется.",
    avenger: "При уходе в сброс призывает новый отряд. В конце раунда — к следующему раунду.",
    scorch_melee: "Казнит сильнейшие рукопашные отряды соперника, если сила его ряда не меньше 10.",
    scorch_ranged: "Казнит сильнейшие дальнобойные отряды соперника, если сила его ряда не меньше 10.",
    scorch_siege: "Казнит сильнейшие осадные отряды соперника, если сила его ряда не меньше 10.",
  };
  let catalog, definitions = new Map(), state = null, socket = null;
  let selected = null, swaps = new Set(), deck = [], leader = "sun", dirtyDeck = false;
  let connected = false, busy = false, pendingVersion = null, reconnectDelay = 700;
  let retryTimer = null, heartbeat = null, toastTimer = null;
  let deckFilter = "all";
  let changingFullscreen = false;
  let mulliganIndex = 0, resultDismissed = false, resultSignature = "";
  let noticeQueue = [], currentNotice = null, noticeAnimation = null, noticeSerial = 0;
  let leaderPreview = null, leaderPreviewAnimation = null;
  const burningCards = new Map();
  const scorchFire = new window.FrontiersFire();
  let scorchFrame = null, scorchTick = null;
  const FILTERS = [["all", "cards", "Все карты"], ["melee", "melee", "Ближний бой"],
    ["ranged", "ranged", "Дальний бой"], ["siege", "siege", "Осада"],
    ["hero", "crown", "Герои"], ["weather", "sun", "Погода"], ["special", "banner", "Особые"]];
  const ICON_PATHS = {
    expand: ["M8 3H3v5M16 3h5v5M3 16v5h5M16 21h5v-5"],
    collapse: ["M3 8h5V3M16 3v5h5M3 16h5v5M16 21v-5h5"],
    cards: ["M7 5h12v16H7z", "M4 17H2V2h12v1", "M10 8h6M10 11h6"],
    melee: ["M8 15 18 3l3-1-1 3L10 17Z", "m6 13 6 6M5 18l3 3M7 17l-3 4M3 20l1 1"],
    ranged: ["M5 3C14 1 23 10 21 21", "M5 3 7 17 21 21", "M3 21 20 4m-5 1 5-1-1 5M4 17h3v3"],
    agile: ["M8 2.5C16 1 23.5 8 21.5 17.5L20.2 16.5C21.5 8.5 15.8 2.5 8.4 3.8Z", "M8 3 10 13 21 17", "M9 15 22 2m-4 1 4-1-1 4", "M2 10.5 5 12l5 5-2 2-5-5-1-3.5Z", "M6.5 19.5l5-5M9.4 18.4l3 3M11.5 22l2-2"],
    siege: ["M3 16h18v2H3ZM7 16l5-9 6 9M4 5l15 7M4 3l-1 4M11 5l2 2", "M8 20a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0ZM22 20a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z"],
    crown: ["m3 7 4 4 5-7 5 7 4-4-2 12H5L3 7Z", "M6 16h12"],
    sun: ["M16 12a4 4 0 1 0-8 0 4 4 0 0 0 8 0Z", "M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"],
    banner: ["M5 22V3m0 1c5-5 9 5 15 0v11c-6 5-10-5-15 0"],
    spy: ["M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z", "M15 12a3 3 0 1 0-6 0 3 3 0 0 0 6 0Z"],
    medic: ["M9 3h6v6h6v6h-6v6H9v-6H3V9h6V3Z"],
    bond: ["m9 8 3-3a4 4 0 0 1 6 6l-3 3M15 16l-3 3a4 4 0 0 1-6-6l3-3M8 16l8-8"],
    morale: ["M12 3 3 12h6v9h6v-9h6L12 3Z"],
    muster: ["M15 6a3 3 0 1 0-6 0 3 3 0 0 0 6 0ZM7 8a2 2 0 1 0-4 0 2 2 0 0 0 4 0ZM21 8a2 2 0 1 0-4 0 2 2 0 0 0 4 0Z", "M8 21v-5a4 4 0 0 1 8 0v5M3 19v-5a2 2 0 0 1 3-2M21 19v-5a2 2 0 0 0-3-2"],
    bear: ["M3 2 7 1l3 3h4l3-3 4 1 2 4-3 4 2 5-3 5-7 3-7-3-3-5 2-5-3-4 2-4Z M4 5l2-1 1 2-2 1-1-2Z M17 6l1-2 2 1-1 2-2-1Z M5 9l5 2-3 1-2-3Z M14 11l5-2-2 3-3-1Z M5 13l4 2-1 2 3 3-4-1-2-6Z M15 15l4-2-2 6-4 1 3-3-1-2Z M9 16l3 1 3-1-1 3-2 2-2-2-1-3Z", "M9 12h6l-3 3-3-3Z"],
    avenger: ["M3 22V10a9 9 0 0 1 18 0v12l-3-2-3 2-3-2-3 2-3-2-3 2Z", "M6.5 10.5l4 1.5-1 2-2-1-1-2.5ZM17.5 10.5l-4 1.5 1 2 2-1 1-2.5Z"],
    unknown: ["M12 2 22 12 12 22 2 12 12 2Z", "M9 9a3 3 0 1 1 4 3v3M13 18h.1"],
    frost: ["M12 2v20M3 7l18 10M3 17 21 7M9 4l3 3 3-3M9 20l3-3 3 3"],
    fog: ["M3 6h18M1 10h17M6 14h17M3 18h16"],
    rain: ["M4 12a3.5 3.5 0 0 1 0-7 5 5 0 0 1 9-1 4 4 0 0 1 5 8H4Z", "m6 16-2 4m8-4-2 4m8-4-2 4"],
    storm: ["M13 2 5 14h7l-1 8 8-13h-7l1-7Z"],
    scorch: ["M8 20v-3c-7-4-5-15 4-15s11 11 4 15v3H8Z", "M7 9h3v3H7ZM14 9h3v3h-3ZM12 12l-1 3h2l-1-3ZM10 17v3m4-3v3"],
    mushroom: ["M2 12a10 10 0 0 1 20 0H2ZM9 12v8h6v-8M7 21h10", "M7 8h.1M14 5h.1M17 9h.1"],
    decoy: ["M5 4h14M12 4v18M3 10l9-2 9 2M8 10l-1 9h10l-1-9", "M15 4a3 3 0 1 0-6 0"],
    opponent: ["M6 9V7a6 6 0 0 1 12 0v2l-2 6-4 3-4-3-2-6Z", "m8 9 3 1m2 0 3-1M2 23v-3l6-4m8 0 6 4v3M12 18v5"],
  };
  const ABILITY_ICONS = {
    spy: "spy", medic: "medic", bond: "bond", morale: "morale", muster: "muster",
    horn: "banner", mushroom: "mushroom", berserker: "bear", avenger: "avenger",
    scorch_melee: "scorch_melee", scorch_ranged: "scorch_ranged", scorch_siege: "scorch_siege",
  };
  function icon(key, className = "") {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("class", `icon ${className}`);
    if (key === "ranged") svg.classList.add("bow-icon");
    if (key === "agile") svg.classList.add("agile-icon");
    if (key === "avenger") svg.classList.add("ghost-icon");
    if (key === "bear") svg.classList.add("bear-icon");
    svg.dataset.icon = key;
    svg.setAttribute("aria-hidden", "true");
    function paths(parent, shapes) {
      for (const d of shapes) {
        const path = document.createElementNS(svg.namespaceURI, "path"); path.setAttribute("d", d); parent.append(path);
      }
    }
    if (["scorch_melee", "scorch_ranged", "scorch_siege"].includes(key)) {
      const skull = document.createElementNS(svg.namespaceURI, "g");
      skull.setAttribute("transform", "translate(-1 -1) scale(.87)");
      paths(skull, ICON_PATHS.scorch); svg.append(skull);
      const marker = document.createElementNS(svg.namespaceURI, "g");
      marker.setAttribute("transform", "translate(12 12) scale(.5)");
      const backing = document.createElementNS(svg.namespaceURI, "circle");
      for (const [attribute, value] of Object.entries({cx: "12", cy: "12", r: "13", fill: "#e2d9bd", stroke: "none"})) backing.setAttribute(attribute, value);
      marker.append(backing); paths(marker, ICON_PATHS[key.slice(7)]); svg.append(marker);
    } else {
      paths(svg, ICON_PATHS[key] || ICON_PATHS.unknown);
    }
    return svg;
  }
  function artClass(card) {
    return `art-${card.key}`;
  }
  function leaderPortrait(key = "sun") {
    // Варианты одного лидера имеют разные иллюстрации без искажения пропорций.
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "leader-art");
    svg.setAttribute("viewBox", "0 0 300 400");
    svg.setAttribute("preserveAspectRatio", "xMidYMid slice");
    svg.setAttribute("aria-hidden", "true");
    const image = document.createElementNS(svg.namespaceURI, "image");
    for (const [attribute, value] of Object.entries({href: `/static/leader_${key}.png`, x: "0", y: "0", width: "300", height: "400", preserveAspectRatio: "xMidYMid slice"})) image.setAttribute(attribute, value);
    svg.append(image); return svg;
  }

  function node(tag, className = "", text = null) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== null) result.textContent = text;
    return result;
  }
  function button(text, handler, className = "") {
    const result = node("button", className, text);
    result.type = "button";
    result.addEventListener("click", handler);
    return result;
  }
  function readStorage(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function writeStorage(key, value) { try { localStorage.setItem(key, value); } catch {} }
  function toast(message) {
    $("toast").textContent = message;
    $("toast").hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { $("toast").hidden = true; }, 6000);
  }
  function syncFullscreen() {
    const active = !!document.fullscreenElement;
    const toggle = $("fullscreen-button");
    toggle.hidden = !document.fullscreenEnabled || typeof document.documentElement.requestFullscreen !== "function";
    toggle.disabled = changingFullscreen;
    toggle.setAttribute("aria-pressed", String(active));
    toggle.setAttribute("aria-label", active ? "Выйти из полноэкранного режима" : "На весь экран");
    toggle.title = active ? "Выйти из полноэкранного режима (Esc)" : "На весь экран";
    toggle.replaceChildren(icon(active ? "collapse" : "expand"));
  }
  async function toggleFullscreen() {
    if (changingFullscreen) return;
    changingFullscreen = true;
    syncFullscreen();
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      toast("Браузер не разрешил сменить режим экрана.");
    } finally {
      changingFullscreen = false;
      syncFullscreen();
    }
  }
  async function api(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? "GET" : "POST", credentials: "same-origin",
      headers: body === undefined ? {} : {"Content-Type": "application/json"},
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(typeof data.detail === "string" ? data.detail : "Проверьте введённые данные.");
      error.status = response.status;
      throw error;
    }
    return data;
  }
  function status(text, mode = "") {
    $("connection").textContent = text;
    $("connection").className = `connection ${mode}`;
  }

  function receive(next) {
    const freshRoom = !state || state.code !== next.code;
    if (!freshRoom && next.revision < state.revision) return;
    const previous = state;
    const oldPhase = state?.game?.phase;
    if (freshRoom || (!dirtyDeck && !next.game)) {
      deck = [...next.my_deck];
      leader = next.my_leader;
    }
    if (next.seats[next.me].ready) {
      deck = [...next.my_deck]; leader = next.my_leader; dirtyDeck = false;
    }
    if (next.game && next.game.phase !== "finished") dirtyDeck = false;
    if (freshRoom || (oldPhase === "finished" && next.game?.phase === "mulligan")) {
      selected = null; swaps.clear(); pendingVersion = null;
      mulliganIndex = 0; resultDismissed = false; resultSignature = "";
      clearScorchAnimations();
      clearAnnouncements();
      if ($("result-dialog").open) $("result-dialog").close();
    }
    if (pendingVersion !== null && next.game?.version > pendingVersion) pendingVersion = null;
    if (!freshRoom) collectScorchedCards(previous, next);
    state = next;
    document.body.dataset.revision = String(next.revision);
    document.body.dataset.gameVersion = String(next.game?.version ?? -1);
    if (state.game && !state.game.players[state.me].hand.some((card) => card.id === selected)) selected = null;
    if (state.game?.players[state.me].mulligan_done) swaps.clear();
    writeStorage("frontiers.room", state.code);
    history.replaceState(null, "", `/?room=${encodeURIComponent(state.code)}`);
    announceChanges(freshRoom ? null : previous, next);
    render();
  }

  function disconnect() {
    clearTimeout(retryTimer); clearInterval(heartbeat);
    const previous = socket; socket = null;
    if (previous) previous.close();
    connected = false;
  }
  function connect(code) {
    disconnect();
    status("Соединяемся с комнатой…");
    const current = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/rooms/${code}`);
    socket = current;
    current.onopen = () => {
      if (socket !== current) return;
      connected = true; reconnectDelay = 700;
      status("● Соединение установлено", "online"); render();
      heartbeat = setInterval(() => {
        if (current.readyState === WebSocket.OPEN) current.send(JSON.stringify({type: "ping"}));
      }, 25000);
    };
    current.onmessage = (event) => {
      if (socket !== current) return;
      try {
        const message = JSON.parse(event.data);
        if (message.type === "state") receive(message.state);
        if (message.type === "error") {
          pendingVersion = null;
          if (message.state) receive(message.state); else render();
          toast(message.message);
        }
      } catch { toast("Не удалось прочитать обновление комнаты."); }
    };
    current.onclose = (event) => {
      if (socket !== current) return;
      connected = false; pendingVersion = null; clearInterval(heartbeat);
      status("● Соединение потеряно", "offline"); render();
      if (event.code === 1008) {
        toast("Комната или сессия недоступна. Вернитесь на главную и войдите по приглашению.");
        return;
      }
      retryTimer = setTimeout(() => { if (state?.code === code) connect(code); }, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 1.7, 10000);
    };
    current.onerror = () => status("● Восстанавливаем соединение…", "offline");
  }

  function send(action) {
    if (!connected || !socket || socket.readyState !== WebSocket.OPEN) return toast("Дождитесь восстановления соединения.");
    if (pendingVersion !== null || !state?.game) return;
    pendingVersion = state.game.version;
    socket.send(JSON.stringify({...action, version: pendingVersion}));
    selected = null;
    render();
  }
  function usableMoves() {
    return connected && pendingVersion === null ? state?.game?.moves || [] : [];
  }
  function selectedMoves() {
    return usableMoves().filter((move) => move.type === "play" && move.card_id === selected);
  }

  function description(card) {
    const parts = [];
    if (card.hero) parts.push("Герой: иммунитет к погоде, усилению, Казни, Чучелу и возвращению Лекарем.");
    if (card.description) parts.push(card.description);
    for (const ability of card.abilities || []) if (EFFECT_TEXT[ability]) parts.push(EFFECT_TEXT[ability]);
    if (card.rows?.length > 1) parts.push("Можно выбрать ближний или дальний бой при розыгрыше.");
    if (!parts.length) parts.push("Обычный отряд. Его сила добавляется к вашему счёту.");
    return parts.join(" ");
  }
  function glyph(card) {
    if (card.hero) return "⚜";
    if (card.kind === "weather") return {frost: "❄", fog: "≋", rain: "☂", storm: "ϟ", clear: "☀"}[card.key] || "☁";
    if (card.kind === "special") return {horn: "⚑", decoy: "♟", scorch: "♨", mushroom: "♧"}[card.key] || "◇";
    if (card.abilities?.includes("spy")) return "◈";
    if (card.abilities?.includes("medic")) return "✚";
    if (card.abilities?.includes("berserker")) return "♞";
    return ROW_GLYPHS[card.rows?.[0]] || "⚔";
  }
  function cardNode(card, options = {}) {
    const result = button("", (event) => {
      event.stopPropagation();
      if (options.onClick) options.onClick(); else showCard(card);
    }, `card ${card.kind} ${card.hero ? "hero" : ""} ${options.small ? "small" : ""} ${options.selected ? "selected" : ""} ${options.targetable ? "targetable" : ""}`);
    if (card.id) result.dataset.cardId = card.id;
    result.dataset.cardKey = card.key;
    result.title = `${card.name}. ${description(card)}`;
    result.setAttribute("aria-label", result.title);
    result.append(node("span", `card-art ${artClass(card)}`), node("span", "card-ribbon", "⚜"));
    const power = card.strength ?? card.base_strength;
    const top = node("div", "card-top");
    const badge = node("span", `card-power ${power !== card.base_strength ? "changed" : ""}`);
    if (card.kind === "unit") badge.textContent = String(power);
    else badge.append(icon(card.key === "clear" ? "sun" : card.key === "horn" ? "banner" : card.key));
    top.append(badge,
               node("span", "", card.hero ? "Герой" : card.kind === "unit" ? "Отряд" : card.kind === "weather" ? "Погода" : "Особая"));
    const seals = node("span", "card-seals");
    for (const ability of card.abilities || []) {
      const seal = node("span", "ability-seal");
      seal.dataset.ability = ability;
      seal.title = catalog.ability_names[ability];
      seal.setAttribute("role", "img"); seal.setAttribute("aria-label", seal.title);
      seal.append(icon(ABILITY_ICONS[ability] || "unknown")); seals.append(seal);
    }
    if (card.kind === "unit") {
      const rowIcon = icon(card.rows?.length > 1 ? "agile" : card.rows?.[0], "combat-seal");
      const label = (card.rows || []).map(row => ROW_NAMES[row]).join(" / ");
      rowIcon.setAttribute("aria-hidden", "false"); rowIcon.setAttribute("role", "img");
      rowIcon.setAttribute("aria-label", label);
      const rowTitle = document.createElementNS(rowIcon.namespaceURI, "title");
      rowTitle.textContent = card.rows.length > 1 ? "Можно сыграть в ближнем или дальнем бою" : label;
      rowIcon.prepend(rowTitle);
      seals.append(rowIcon);
    }
    result.append(top, node("span", "card-name", card.name), seals,
      node("span", "card-abilities", (card.abilities || []).map((ability) => catalog.ability_names[ability] || ability).join(" · ")),
      node("span", "card-row", (card.rows || []).map((row) => ROW_NAMES[row]).join(" / ")));
    return result;
  }
  function showInfo(content) {
    $("info-content").replaceChildren(content);
    if (!$("info-dialog").open) $("info-dialog").showModal();
  }
  function showCard(card) {
    const content = node("div", "card-details");
    content.append(cardNode(card, {onClick: () => {}}), node("p", "eyebrow", card.hero ? "Герой Бургундии" : "Коллекция Бургундии"),
      node("h2", "", card.name), node("p", "", description(card)));
    if (card.transform_to) content.append(node("p", "muted", `Вторая форма: ${definitions.get(card.transform_to)?.name || card.transform_to}.`));
    if (card.summon_to) content.append(node("p", "muted", `Призывает: ${definitions.get(card.summon_to)?.name || card.summon_to}.`));
    showInfo(content);
  }

  function render() {
    const active = !!(state?.game && (state.game.phase !== "finished" || !resultDismissed));
    const wasActive = document.body.classList.contains("in-match");
    document.body.classList.toggle("in-match", active);
    document.body.classList.toggle("in-room", !!state);
    document.body.classList.toggle("in-lobby", !!state && !active);
    (state ? $("room-status") : document.querySelector(".topbar")).append($("connection"));
    (state ? document.querySelector(".toolbar-actions") : document.querySelector(".topbar")).append($("fullscreen-button"));
    if (active && !wasActive) window.scrollTo(0, 0);
    $("landing").hidden = !!state;
    $("room").hidden = !state;
    if (!state) {
      closePresentation();
      return;
    }
    $("room-label").textContent = state.code;
    $("copy-invite").hidden = active;
    $("lobby").hidden = !!active;
    $("arena").hidden = !active;
    if (active) renderGame(); else { closeChoice(); closeMulligan(); closeLeaderPreview(); renderLobby(); }
    renderResult();
  }
  function renderLobby() {
    const mine = state.seats[state.me];
    const locked = mine.ready || busy;
    const seats = [];
    for (let index = 0; index < 2; index++) {
      const seat = state.seats[index];
      const item = node("div", `seat ${seat ? "" : "waiting"}`);
      item.append(node("span", "seat-avatar", seat ? seat.name[0].toUpperCase() : "+"));
      const label = node("div");
      label.append(node("strong", "", seat ? `${seat.name}${index === state.me ? " · вы" : ""}` : "Ждём соперника"),
        node("small", "", seat ? seat.ready ? "Готов к матчу" : seat.online ? "Выбирает колоду" : "Не в сети" : "Передайте другу приглашение"));
      item.append(label);
      if (seat?.ready) item.append(node("span", "ready-dot", "✓"));
      seats.push(item);
    }
    $("seats").replaceChildren(...seats);
    $("leader-select").value = leader;
    document.querySelector(".leader-portrait .leader-art").replaceWith(leaderPortrait(leader));
    $("leader-select").disabled = locked;
    $("leader-description").textContent = catalog.leaders[leader].description;
    $("deck-preset").disabled = locked;
    const sorted = [...deck].sort().join(",");
    $("deck-preset").value = Object.keys(catalog.decks).find((key) => [...catalog.decks[key].cards].sort().join(",") === sorted) || "custom";
    const units = deck.filter((key) => definitions.get(key).kind === "unit").length;
    const specials = deck.length - units;
    const valid = units >= 22 && specials <= 10 && deck.length <= 60;
    $("deck-count").textContent = `${units} отрядов · ${specials} особых`;
    $("deck-count").className = `count-badge sr-only ${valid ? "" : "invalid"}`;
    const counts = new Map(); for (const key of deck) counts.set(key, (counts.get(key) || 0) + 1);
    const filter = $("collection-filter").value;
    renderFilterTabs("collection-tabs", filter, (value) => { $("collection-filter").value = value; renderLobby(); });
    renderFilterTabs("deck-tabs", deckFilter, (value) => { deckFilter = value; renderLobby(); });
    for (const [id, category, inDeck] of [["collection", filter, false], ["deck-cards", deckFilter, true]]) {
      const list = $(id), position = list.scrollTop;
      const cards = catalog.cards.filter((card) => card.collectible && card.available !== false && matchesFilter(card, category)
        && (inDeck ? counts.has(card.key) : (counts.get(card.key) || 0) < card.copies));
      cards.sort((a, b) => cardOrder(a) - cardOrder(b) || b.base_strength - a.base_strength);
      list.replaceChildren(...cards.map((card) => {
        const item = node("div", "collection-item");
        const count = counts.get(card.key) || 0;
        const controls = node("div", "card-adjust");
        const adjust = button(inDeck ? "−" : "+", () => {
          if (inDeck) deck.splice(deck.indexOf(card.key), 1); else deck.push(card.key);
          dirtyDeck = true; renderLobby();
        });
        adjust.disabled = locked || (!inDeck && deck.length >= 60);
        adjust.setAttribute("aria-label", `${inDeck ? "Убрать" : "Добавить"}: ${card.name}`);
        controls.append(node("span", "", `×${inDeck ? count : card.copies - count}`), adjust);
        item.append(cardNode(card), controls); return item;
      }));
      if (!cards.length) list.append(node("p", "empty-collection", inDeck ? "В этой категории пока нет карт. Добавьте их из коллекции слева." : "Все карты этой категории уже в вашей колоде."));
      list.scrollTop = position;
    }
    const stats = [["Карты в колоде", deck.length, ""], ["Карты отрядов", `${units} / 22+`, units < 22 ? "invalid" : ""],
      ["Особые карты", `${specials} / 10`, specials > 10 ? "invalid" : ""],
      ["Общая сила отрядов", deck.reduce((sum, key) => sum + definitions.get(key).base_strength, 0), ""],
      ["Герои", deck.filter((key) => definitions.get(key).hero).length, ""]];
    $("deck-stats").replaceChildren(...stats.map(([label, value, mode]) => {
      const pair = node("div", mode); pair.append(node("dt", "", label), node("dd", "", String(value))); return pair;
    }));
    $("ready-button").disabled = busy || !connected || (!mine.ready && !valid);
    $("ready-button").textContent = mine.ready ? "Отменить готовность" : state.game ? "Готов к реваншу" : "Готов к матчу";
    $("ready-hint").textContent = mine.ready ? "Ждём готовности второго игрока." : "Матч начнётся, когда оба игрока будут готовы.";
    $("match-result").hidden = !state.game;
    if (state.game) {
      const game = state.game;
      const title = game.winner === null ? "Ничья" : game.winner === state.me ? "Ваша победа" : "Победа соперника";
      const results = node("div", "result-scores");
      for (const round of game.history) results.append(node("span", "", `Раунд ${round.round}: ${round.scores[state.me]} : ${round.scores[1 - state.me]}`));
      $("match-result").replaceChildren(node("p", "eyebrow", "Дуэль завершена"), node("h2", "", title),
        node("p", "muted", "Можно изменить колоду и подтвердить готовность к новому матчу."), results);
    }
  }

  function matchesFilter(card, filter) {
    return filter === "all" || filter === card.kind || (filter === "hero" && card.hero) || card.rows?.includes(filter);
  }
  function cardOrder(card) { return card.kind === "weather" ? 0 : card.kind === "special" ? 1 : card.hero ? 2 : 3; }
  function renderFilterTabs(id, value, change) {
    $(id).replaceChildren(...FILTERS.map(([key, symbol, label]) => {
      const tab = button("", () => change(key), value === key ? "active" : "");
      tab.title = label; tab.setAttribute("aria-label", label); tab.setAttribute("aria-pressed", String(key === value));
      tab.append(icon(symbol)); return tab;
    }));
  }

  function playerPanel(player, side) {
    const heading = node("div", "player-heading");
    heading.append(node("strong", "", player.name), node("span", "score-number", String(player.score)));
    const gems = node("div", "gems");
    gems.setAttribute("aria-label", `Жетонов раунда: ${player.lives}`);
    for (let index = 0; index < 2; index++) gems.append(node("span", index >= player.lives ? "lost" : "", "◆"));
    const emblem = node("div", "player-emblem", "⚜");
    const details = node("div", "player-details");
    details.append(heading, node("span", "player-faction", "Королевство Бургундия"),
      node("div", "player-meta", `В руке: ${player.hand_count} · Колода: ${player.deck_count}`), gems);
    const parts = [emblem, details];
    if (player.passed) parts.push(node("div", "passed-tag", "Пас"));
    if (!state.seats[side].online) parts.push(node("div", "passed-tag", "Не в сети"));
    return parts;
  }
  function renderGame() {
    const game = state.game, me = state.me, mine = game.players[me];
    $("opponent-score").replaceChildren(...playerPanel(game.players[1 - me], 1 - me));
    $("my-score").replaceChildren(...playerPanel(mine, me));
    $("round-label").textContent = game.round;
    $("history").replaceChildren(...game.history.map((round) => node("span", "", `${round.round}: ${round.scores[me]} : ${round.scores[1 - me]}`)));
    let banner;
    if (game.phase === "finished") banner = "Матч завершён";
    else if (game.phase === "mulligan") banner = mine.mulligan_done ? "Ждём подтверждения руки соперника" : "Выберите до двух карт для замены";
    else if (game.pending) banner = game.pending.actor === me ? "Лекарь: выберите отряд из сброса" : "Соперник выбирает цель Лекаря";
    else banner = game.turn === me ? (game.players[1 - me].passed ? "Соперник спасовал. Вы можете продолжать ходить" : "Ваш ход") : "Ход соперника";
    if (pendingVersion !== null) banner = "Сервер проверяет ход…";
    $("turn-banner").textContent = banner;
    $("turn-banner").title = banner;
    $("turn-banner").className = `turn-banner ${game.turn === me && game.phase === "playing" ? "your-turn" : ""}`;
    $("enemy-rows").replaceChildren(...[...ROWS].reverse().map((row) => combatRow(1 - me, row)));
    $("own-rows").replaceChildren(...ROWS.map((row) => combatRow(me, row)));
    $("weather-strip").replaceChildren(...game.weather.map((effect) => node("span", "weather-chip", effect.name)));
    for (const [id, player] of [["leader-button", mine], ["enemy-leader", game.players[1 - me]]]) {
      const text = node("span", "leader-caption");
      text.append(node("strong", "", "Франциск II Мудрый"), node("small", "", catalog.leaders[player.leader].name));
      $(id).replaceChildren(leaderPortrait(player.leader), text, node("span", "leader-availability", player.leader_used ? "Использован" : id === "leader-button" ? "Использовать лидера" : "Лидер соперника"));
      $(id).classList.toggle("used", player.leader_used);
      $(id).title = catalog.leaders[player.leader].description;
    }
    $("my-score").classList.toggle("active-player", game.turn === me && game.phase === "playing");
    $("opponent-score").classList.toggle("active-player", game.turn !== me && game.phase === "playing");
    for (const [prefix, player] of [["own", mine], ["enemy", game.players[1 - me]]]) {
      $(prefix + "-deck").replaceChildren(node("span", "pile-crest", "⚜"), node("strong", "", String(player.deck_count)), node("small", "", "Колода"));
      const discarded = player.discard.at(-1);
      const preview = node("span", `discard-preview ${discarded ? artClass(discarded) : ""}`);
      preview.append(node("span", "", discarded ? glyph(discarded) : "∅"));
      $(prefix + "-discard").replaceChildren(preview, node("small", "", `Сброс · ${player.discard.length}`));
    }
    $("leader-button").title = catalog.leaders[mine.leader].description;
    $("leader-button").disabled = !usableMoves().some((move) => move.type === "leader");
    $("pass-button").disabled = !usableMoves().some((move) => move.type === "pass");
    $("concede-button").disabled = !usableMoves().some((move) => move.type === "concede");
    const canSwap = game.phase === "mulligan" && !mine.mulligan_done;
    $("mulligan-button").hidden = !canSwap;
    $("mulligan-button").disabled = !connected || pendingVersion !== null;
    $("mulligan-button").textContent = swaps.size ? `Заменить карт: ${swaps.size}` : "Оставить руку";
    $("hand-count").textContent = `В руке ${mine.hand.length} · В колоде ${mine.deck_count}`;
    $("hand").replaceChildren(...mine.hand.map((card) => cardNode(card, {
      selected: canSwap ? swaps.has(card.id) : selected === card.id,
      onClick: () => {
        if (canSwap && pendingVersion === null) {
          if (swaps.has(card.id)) swaps.delete(card.id);
          else if (swaps.size < 2) swaps.add(card.id);
          else return toast("Можно заменить только две карты.");
          renderGame();
        } else if (usableMoves().some((move) => move.type === "play" && move.card_id === card.id)) {
          selected = selected === card.id ? null : card.id; renderGame();
        } else showCard(card);
      },
    })));
    if (!mine.hand.length) $("hand").append(node("div", "empty-hand", "Рука пуста. Можно использовать доступную способность лидера или спасовать."));
    const chosen = mine.hand.find((card) => card.id === selected);
    const moves = selectedMoves();
    const info = [];
    if (chosen) {
      info.push(node("span", "", chosen.key === "horn" ? "Выберите подсвеченное место для штандарта слева" : moves.some((move) => move.target_id) ? "Выберите свой отряд на поле" : moves.length > 1 ? "Выберите подсвеченный ряд" : chosen.name));
      if (moves.length === 1 && !moves[0].target_id && chosen.key !== "horn") info.push(button("Сыграть", () => send(moves[0]), "primary"));
      info.push(button("О карте", () => showCard(chosen), "text-button"));
    } else if (!canSwap) info.push(node("span", "", "Нажмите на карту в руке, чтобы выбрать действие"));
    $("selection-info").replaceChildren(...info);
    syncTableCardProportions();
    renderChoices();
    renderMulligan();
    renderLeaderPreview();
    startScorchAnimations();
  }
  function collectScorchedCards(previous, next) {
    const before = previous?.game, game = next.game;
    if (!before || !game || game.version <= before.version) return;
    const ids = new Set(game.scorched || []);
    for (let side = 0; side < 2; side++) {
      const board = before.players[side].board;
      for (const card of board) {
        const key = `${game.version}:${card.id}`;
        if (!ids.has(card.id) || burningCards.has(key)) continue;
        const source = document.querySelector(`.row-cards [data-card-id="${CSS.escape(card.id)}"]`);
        if (!source) continue;
        const bounds = source.getBoundingClientRect();
        if (!bounds.width || !bounds.height) continue;
        const image = source.cloneNode(true), element = node("div", "scorch-burn");
        image.removeAttribute("data-card-id"); image.removeAttribute("title");
        image.classList.remove("selected", "targetable"); image.tabIndex = -1;
        element.dataset.burnId = card.id; element.setAttribute("aria-hidden", "true"); element.inert = true;
        element.append(image);
        const order = board.filter(item => item.row === card.row).map(item => item.id);
        const burn = {element, image, side, row: card.row, elapsed: 0,
          following: order.slice(order.indexOf(card.id) + 1), animations: [], started: false};
        scorchFire.prepare(burn, key); burningCards.set(key, burn);
      }
    }
    if (burningCards.size && currentNotice?.type === "turn") {
      noticeAnimation?.cancel(); noticeAnimation = null; currentNotice = null;
      $("match-announcement").hidden = true;
    }
  }
  function clearScorchAnimations() {
    for (const burn of burningCards.values()) {
      for (const animation of burn.animations) animation.cancel();
      burn.element.remove();
    }
    burningCards.clear();
    cancelAnimationFrame(scorchFrame); scorchFrame = null; scorchTick = null;
    scorchFire.clear();
  }
  function startScorchAnimations() {
    for (const [id, burn] of burningCards) {
      if (burn.started || !burn.element.isConnected) continue;
      burn.started = true;
      const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
      burn.reduced = reduced;
      burn.element.classList.toggle("reduced-motion", reduced);
      const frames = reduced ? [{opacity: 1}, {opacity: 0}] : [
        {offset: 0, opacity: 1, filter: "brightness(1) sepia(0) saturate(1)", clipPath: scorchFire.clip(burn, 0)},
        {offset: .18, opacity: 1, filter: "brightness(1.1) sepia(.75) saturate(1.3)", clipPath: scorchFire.clip(burn, .18)},
        {offset: .6, opacity: 1, filter: "brightness(.4) sepia(.5) saturate(.2)", clipPath: scorchFire.clip(burn, .6)},
        {offset: 1, opacity: 0, filter: "brightness(.1) sepia(.5) saturate(0)", clipPath: scorchFire.clip(burn, 1)},
      ];
      burn.duration = reduced ? 220 : 2400;
      const animation = burn.image.animate(frames, {duration: burn.duration, easing: "linear", fill: "both"});
      animation.pause(); animation.currentTime = 0;
      animation.finished.catch(() => {});
      burn.animations.push(animation);
    }
    scheduleScorchFrame();
  }
  function scheduleScorchFrame() {
    if (scorchFrame === null && burningCards.size && document.visibilityState === "visible") scorchFrame = requestAnimationFrame(advanceScorchFrame);
  }
  function advanceScorchFrame(time) {
    scorchFrame = null;
    if (document.visibilityState !== "visible") { scorchTick = null; return scorchFire.clear(); }
    // Считаем показанные кадры: фоновая вкладка не пропускает весь эффект за один скачок часов.
    const delta = scorchTick === null ? 16 : Math.max(0, Math.min(50, time - scorchTick));
    scorchTick = time;
    for (const [id, burn] of burningCards) {
      if (!burn.started) continue;
      burn.elapsed = Math.min(burn.duration, burn.elapsed + delta);
      burn.animations[0].currentTime = burn.elapsed;
      if (burn.elapsed >= burn.duration) {
        burningCards.delete(id); burn.element.remove();
        for (const animation of burn.animations) animation.cancel();
      }
    }
    scorchFire.draw(burningCards, delta);
    if (burningCards.size) scheduleScorchFrame();
    else { scorchTick = null; playAnnouncement(); }
  }
  function closeLeaderPreview() {
    leaderPreviewAnimation?.cancel(); leaderPreviewAnimation = null; leaderPreview = null;
    if ($("leader-dialog").open) $("leader-dialog").close();
  }
  function renderLeaderPreview() {
    if (!leaderPreview) return;
    const game = state?.game;
    if (state?.code !== leaderPreview.code || game?.phase !== "playing" || game.version !== leaderPreview.version ||
        game.players[state.me].leader !== leaderPreview.key || game.players[state.me].leader_used) return closeLeaderPreview();
    $("leader-apply").disabled = !usableMoves().some(move => move.type === "leader");
    $("leader-confirmation-status").textContent = connected ? "Один раз за матч. Применение завершит ваш ход." : "Соединение потеряно. Дождитесь восстановления связи или отмените выбор.";
  }
  function openLeaderPreview() {
    if (!usableMoves().some(move => move.type === "leader")) return;
    selected = null; renderGame();
    const game = state.game, key = game.players[state.me].leader;
    leaderPreview = {code: state.code, version: game.version, key};
    const preview = $("leader-preview"), caption = node("div", "leader-preview-caption");
    caption.append(node("strong", "", "Франциск II Мудрый"), node("span", "", catalog.leaders[key].name));
    preview.replaceChildren(leaderPortrait(key), caption);
    $("leader-title").textContent = catalog.leaders[key].name;
    $("leader-rule").textContent = catalog.leaders[key].description;
    renderLeaderPreview();
    $("leader-dialog").showModal();
    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const source = $("leader-button").getBoundingClientRect(), target = preview.getBoundingClientRect();
      const x = source.left + source.width / 2 - target.left - target.width / 2;
      const y = source.top + source.height / 2 - target.top - target.height / 2;
      const scale = Math.min(source.width / target.width, source.height / target.height);
      leaderPreviewAnimation = preview.animate([
        {transform: `translate(${x}px, ${y}px) scale(${scale})`, opacity: .65},
        {transform: "none", opacity: 1},
      ], {duration: 480, easing: "cubic-bezier(.2,.7,.2,1)"});
    }
  }
  function closeMulligan() { if ($("mulligan-dialog").open) $("mulligan-dialog").close(); }
  function focusMulligan(index, keyboard = false) {
    const hand = state?.game?.players[state.me].hand;
    if (!hand?.length) return;
    mulliganIndex = Math.max(0, Math.min(hand.length - 1, index));
    renderMulligan();
    if (keyboard) $("mulligan-cards").children[mulliganIndex]?.focus({preventScroll: true});
  }
  function toggleMulligan(index) {
    const game = state?.game;
    if (!game || game.phase !== "mulligan" || game.players[state.me].mulligan_done || !connected || pendingVersion !== null) return;
    const card = game.players[state.me].hand[index];
    if (!card) return;
    if (swaps.has(card.id)) swaps.delete(card.id);
    else if (swaps.size < 2) swaps.add(card.id);
    else return toast("Можно заменить только две карты. Снимите отметку с одной из выбранных.");
    renderMulligan();
  }
  function renderMulligan() {
    const game = state?.game;
    if (!game || game.phase !== "mulligan") return closeMulligan();
    const mine = game.players[state.me], hand = mine.hand;
    mulliganIndex = Math.max(0, Math.min(hand.length - 1, mulliganIndex));
    const waiting = mine.mulligan_done;
    const blocked = waiting || !connected || pendingVersion !== null;
    const signature = hand.map(card => card.id).join(",");
    for (const [id, thumbnail] of [["mulligan-cards", false], ["mulligan-thumbnails", true]]) {
      const track = $(id);
      // Сохраняем элементы при навигации: CSS плавно перемещает соседние карты.
      if (track.dataset.hand !== signature) {
        track.replaceChildren(...hand.map((card, index) => cardNode(card, {onClick: () => {
          if (thumbnail || index !== mulliganIndex) focusMulligan(index);
          else toggleMulligan(index);
        }})));
        track.dataset.hand = signature;
      }
      [...track.children].forEach((element, index) => {
        const distance = index - mulliganIndex, chosen = swaps.has(hand[index].id);
        element.classList.toggle("focused", distance === 0);
        element.classList.toggle("selected", chosen);
        element.setAttribute("aria-pressed", String(chosen));
        element.tabIndex = thumbnail || distance === 0 ? 0 : -1;
        if (!thumbnail) {
          element.style.setProperty("--offset", String(distance));
          element.style.setProperty("--scale", String(Math.max(.6, 1 - Math.abs(distance) * .14)));
          element.style.setProperty("--opacity", Math.abs(distance) > 2 ? "0" : "1");
          element.style.setProperty("--layer", String(10 - Math.abs(distance)));
          element.hidden = Math.abs(distance) > 2;
          element.setAttribute("aria-label", `${element.title}${chosen ? " Выбрана для замены." : ""}`);
        }
      });
    }
    $("mulligan-dialog").classList.toggle("waiting", waiting);
    $("mulligan-title").firstChild.textContent = waiting ? "Рука готова. Ждём соперника " : "Выберите карты для замены ";
    $("mulligan-count").textContent = waiting ? "✓" : `${swaps.size}/2`;
    $("mulligan-prev").disabled = mulliganIndex === 0;
    $("mulligan-next").disabled = mulliganIndex === hand.length - 1;
    const focused = hand[mulliganIndex];
    $("mulligan-card-name").textContent = focused?.name || "Начальная рука";
    $("mulligan-card-description").textContent = focused ? description(focused) : "";
    $("mulligan-select").disabled = blocked || (!swaps.has(focused?.id) && swaps.size === 2);
    $("mulligan-select").textContent = swaps.has(focused?.id) ? "Оставить эту карту" : "Выбрать для замены";
    $("mulligan-select").hidden = waiting;
    $("mulligan-button").disabled = blocked;
    $("mulligan-button").hidden = waiting;
    $("mulligan-button").textContent = swaps.size ? `Заменить ${swaps.size === 1 ? "1 карту" : "2 карты"}` : "Оставить руку";
    $("mulligan-concede").disabled = !usableMoves().some(move => move.type === "concede");
    $("mulligan-hint").textContent = !connected ? "Соединение потеряно. Выбранные карты сохранятся до восстановления связи."
      : pendingVersion !== null ? "Сервер подтверждает выбор…"
      : waiting ? "Ваш выбор подтверждён. Матч начнётся, когда соперник оставит свою руку."
      : "← → — просмотр · Enter — выбор карты · можно заменить до двух карт";
    if (!$("mulligan-dialog").open) $("mulligan-dialog").showModal();
  }
  function ceremonyEmblem(kind) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 120 120"); svg.setAttribute("class", "ceremony-emblem");
    svg.setAttribute("aria-hidden", "true");
    let ink = "currentColor";
    function shape(d, fill = "none", width = "2", parent = svg, stroke = ink) {
      const path = document.createElementNS(svg.namespaceURI, "path");
      for (const [key, value] of Object.entries({d, fill, stroke, "stroke-width": width, "stroke-linejoin": "round"})) path.setAttribute(key, value);
      parent.append(path);
      return path;
    }
    if (kind === "pass") {
      const flag = icon("banner"); flag.setAttribute("x", "16"); flag.setAttribute("y", "8"); flag.setAttribute("width", "92"); flag.setAttribute("height", "104"); svg.append(flag);
      return svg;
    }
    if (kind === "enemy-turn") {
      const opponent = icon("opponent"); opponent.setAttribute("x", "16"); opponent.setAttribute("y", "6"); opponent.setAttribute("width", "88"); opponent.setAttribute("height", "108"); svg.append(opponent);
      return svg;
    }
    const broken = kind === "defeat" || kind === "round-loss";
    ink = broken ? "#bd9278" : "#c99e4c";
    const highlight = broken ? ink : "#d7b365";
    svg.setAttribute("viewBox", "0 0 180 180");
    for (const angle of [-45, 45]) {
      const sword = document.createElementNS(svg.namespaceURI, "g");
      sword.setAttribute("transform", `translate(90 98) rotate(${angle})`);
      svg.append(sword);
      shape("M0-101 8-84V53H-8V-84Z", ink, "1", sword).setAttribute("stroke-linejoin", "miter");
      shape("M0-88V50", "none", "1.4", sword, broken ? "#493126" : "#372a16").setAttribute("opacity", ".8");
      shape("M-19 50H19V57H-19Z", highlight, "0", sword);
      shape("M-4 56H4V79H-4Z", ink, "0", sword);
      const pommel = document.createElementNS(svg.namespaceURI, "circle");
      for (const [key, value] of Object.entries({cy: "83", r: "6.5", fill: highlight})) pommel.setAttribute(key, value);
      sword.append(pommel);
    }
    shape("M48 49 90 38l42 11v43c0 28-19 47-42 60-23-13-42-32-42-60Z", "#15140e", "4");
    shape("M56 55 90 46l34 9v37c0 23-15 39-34 51-19-12-34-28-34-51Z", "none", "1.5");
    shape("m58 29-7-23 23 14L90 4l16 16 23-14-7 23Z", ink, "0");
    if (kind === "draw" || kind === "round-draw") {
      shape("M90 69v46.5M64.5 79.5h51M64.5 79.5 51 105h27Zm51 0L102 105h27ZM73.5 123h33", "none", "3")
        .setAttribute("transform", "translate(90 96) scale(.68) translate(-90 -96)");
    } else if (broken) {
      shape("M94 54 82 84 101 92 77 131", "none", "4.5");
    }
    return svg;
  }
  function clearAnnouncements() {
    noticeQueue = []; currentNotice = null;
    noticeAnimation?.cancel(); noticeAnimation = null;
    $("match-announcement").hidden = true;
  }
  function closePresentation() {
    closeMulligan(); closeLeaderPreview(); clearScorchAnimations(); clearAnnouncements();
    if ($("result-dialog").open) $("result-dialog").close();
  }
  function playAnnouncement() {
    if (currentNotice || burningCards.size) return;
    const next = noticeQueue.shift();
    if (!next) return renderResult();
    if (!state?.game || resultDismissed) return clearAnnouncements();
    currentNotice = next;
    const layer = $("match-announcement");
    layer.dataset.kind = next.kind; layer.dataset.sequence = String(++noticeSerial);
    $("announcement-emblem").replaceChildren(ceremonyEmblem(next.kind));
    $("announcement-title").textContent = next.title;
    $("announcement-detail").textContent = next.detail || "";
    layer.hidden = false;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const animation = layer.animate([
      {opacity: 0, transform: reduced ? "none" : "translateY(8px)", offset: 0},
      {opacity: 1, transform: "none", offset: .16},
      {opacity: 1, transform: "none", offset: .78},
      {opacity: 0, transform: reduced ? "none" : "translateY(-4px)", offset: 1},
    ], {duration: next.type === "round" ? 2600 : 1900, easing: "ease-in-out", fill: "both"});
    noticeAnimation = animation;
    animation.finished.then(() => {
      if (noticeAnimation !== animation) return;
      layer.hidden = true; currentNotice = null; noticeAnimation = null;
      animation.cancel(); playAnnouncement();
    }, () => {});
  }
  function announceChanges(previous, next) {
    const before = previous?.game, game = next.game;
    // Снимок при входе и повторная доставка той же версии не повторяют старые события.
    if (!before || !game || game.version <= before.version || before.phase === "finished") return;
    const notices = [], me = next.me;
    const rounds = game.history.slice(before.history.length);
    if (before.phase === "playing") {
      for (const side of [before.turn, 1 - before.turn]) {
        if (!before.players[side].passed && (game.players[side].passed || rounds.length)) {
          notices.push({type: "pass", kind: "pass", title: side === me ? "Вы спасовали" : "Противник спасовал", detail: game.players[side].name});
        }
      }
    }
    for (const round of rounds) {
      const kind = round.winner === null ? "round-draw" : round.winner === me ? "round-win" : "round-loss";
      notices.push({type: "round", kind, title: round.winner === null ? "Ничья в раунде" : round.winner === me ? "Вы выиграли раунд!" : "Вы проиграли раунд",
        detail: `Раунд ${round.round} · ${round.scores[me]} : ${round.scores[1 - me]}`});
    }
    if (game.phase === "playing" && (before.phase === "mulligan" || game.turn !== before.turn || rounds.length)) {
      notices.push({type: "turn", kind: game.turn === me ? "your-turn" : "enemy-turn", title: game.turn === me ? "Ваш ход!" : "Ход противника", detail: `Раунд ${game.round}`});
    }
    if (!notices.length && game.phase !== "finished") return;
    // Устаревшее объявление хода уступает новому действию; результаты и пас сохраняют порядок.
    noticeQueue = noticeQueue.filter(notice => notice.type !== "turn");
    if (currentNotice?.type === "turn") {
      noticeAnimation?.cancel(); noticeAnimation = null; currentNotice = null;
      $("match-announcement").hidden = true;
    }
    noticeQueue.push(...notices);
    playAnnouncement();
  }
  function dismissResult() {
    resultDismissed = true;
    clearAnnouncements();
    if ($("result-dialog").open) $("result-dialog").close();
    render();
  }
  function renderResult() {
    const game = state?.game;
    if (!game || game.phase !== "finished" || resultDismissed || currentNotice || noticeQueue.length || burningCards.size) return;
    const dialog = $("result-dialog"), me = state.me;
    const signature = `${state.code}:${game.version}:${me}`;
    if (resultSignature !== signature) {
      const outcome = game.winner === null ? "draw" : game.winner === me ? "victory" : "defeat";
      dialog.dataset.outcome = outcome;
      $("result-emblem").replaceChildren(ceremonyEmblem(outcome));
      $("result-title").textContent = {victory: "Победа!", defeat: "Поражение", draw: "Ничья"}[outcome];
      const conceded = game.players.every(player => player.lives > 0);
      $("result-subtitle").textContent = conceded ? game.winner === me ? "Соперник сдался." : "Вы сдались." : "Королевство Бургундия · Итоги раундов";
      const table = node("table", "match-score-table"), head = node("thead"), body = node("tbody"), headers = node("tr");
      table.append(node("caption", "", "Счёт игроков по раундам"));
      for (const title of ["Игрок", "Раунд 1", "Раунд 2", "Раунд 3"]) {
        const cell = node("th", "", title); cell.scope = "col"; headers.append(cell);
      }
      head.append(headers);
      for (const side of [me, 1 - me]) {
        const row = node("tr"), name = node("th", "", `${game.players[side].name}${side === me ? " · вы" : ""}`);
        name.scope = "row"; row.append(name);
        for (let number = 1; number <= 3; number++) {
          const round = game.history.find(item => item.round === number);
          row.append(node("td", round?.winner === side ? "round-winner" : "", round ? String(round.scores[side]) : "—"));
        }
        body.append(row);
      }
      table.append(head, body); $("result-table").replaceChildren(table);
      resultSignature = signature;
    }
    closeMulligan(); closeChoice(); closeLeaderPreview();
    if ($("info-dialog").open) $("info-dialog").close();
    if (!dialog.open) dialog.showModal();
  }
  function syncTableCardProportions() {
    const reference = $("hand").querySelector(".card.unit:not(.hero), .card:not(.hero)") || $("hand").querySelector(".card");
    if (!reference) return;
    const cardStyle = getComputedStyle(reference);
    const width = reference.getBoundingClientRect().width - parseFloat(cardStyle.borderLeftWidth) - parseFloat(cardStyle.borderRightWidth);
    if (width <= 0) return;
    const power = reference.querySelector(".card-power");
    const powerStyle = getComputedStyle(power);
    const seal = $("hand").querySelector(".combat-seal, .ability-seal");
    const values = {
      "power-size": power.getBoundingClientRect().width,
      "power-font": parseFloat(powerStyle.fontSize),
      "badge-border": parseFloat(powerStyle.borderLeftWidth),
      "seal-gap": parseFloat(getComputedStyle(reference.querySelector(".card-seals")).gap),
    };
    if (seal) {
      const owner = seal.closest(".card"), ownerStyle = getComputedStyle(owner);
      const ownerWidth = owner.getBoundingClientRect().width - parseFloat(ownerStyle.borderLeftWidth) - parseFloat(ownerStyle.borderRightWidth);
      values["seal-size"] = seal.getBoundingClientRect().width / ownerWidth * width;
      const combat = $("hand").querySelector(".combat-seal");
      if (combat) values["seal-padding"] = parseFloat(getComputedStyle(combat).paddingLeft) / ownerWidth * width;
    }
    for (const [key, pixels] of Object.entries(values)) {
      document.body.style.setProperty(`--table-${key}`, `${(pixels / width * 100).toFixed(4)}cqw`);
    }
  }
  function combatRow(side, row) {
    const game = state.game, player = game.players[side];
    const own = side === state.me;
    const chosen = game.players[state.me].hand.find((card) => card.id === selected);
    const targetSide = chosen?.abilities?.includes("spy") ? 1 - state.me : state.me;
    const rowMove = selectedMoves().find((move) => move.row === row && !move.target_id);
    const slotMove = own && chosen?.key === "horn" && rowMove;
    const droppable = side === targetSide && !!rowMove && chosen?.key !== "horn";
    const weathered = game.weather.some((effect) => WEATHER[effect.key]?.includes(row));
    const result = node("div", `combat-row ${own ? "own" : "enemy"} ${droppable ? "droppable" : ""} ${weathered ? "weathered" : ""}`);
    result.dataset.side = own ? "own" : "enemy";
    result.dataset.row = row;
    if (droppable) {
      result.tabIndex = 0; result.setAttribute("role", "button");
      result.setAttribute("aria-label", `Разыграть карту: ${ROW_NAMES[row]}`);
      result.addEventListener("click", () => send(rowMove));
      result.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); send(rowMove); } });
    }
    const label = node("div", "row-info");
    label.title = ROW_NAMES[row];
    label.append(node("span", "row-symbol", ROW_GLYPHS[row]), node("strong", "", String(player.rows[row])), node("span", "", ROW_NAMES[row]));
    for (const card of player.specials.filter((item) => item.row === row)) {
      const marker = button(glyph(card), (event) => { event.stopPropagation(); showCard(card); }, "mobile-row-effect");
      marker.title = card.name;
      marker.setAttribute("aria-label", card.name);
      label.append(marker);
    }
    if (player.leader_horn.includes(row)) label.append(node("span", "mobile-row-effect", "×2"));
    const cards = node("div", "row-cards"), liveCards = new Map();
    for (const card of player.board.filter((item) => item.row === row)) {
      const move = own ? selectedMoves().find((option) => option.target_id === card.id) : null;
      const element = cardNode(card, {small: true, targetable: !!move, onClick: () => move ? send(move) : showCard(card)});
      liveCards.set(card.id, element); cards.append(element);
    }
    // Занимаем прежние места сгорающих карт, чтобы оставшиеся отряды не прыгали под огонь.
    for (const burn of burningCards.values()) {
      if (burn.side !== side || burn.row !== row) continue;
      const following = burn.following.find(id => liveCards.has(id));
      cards.insertBefore(burn.element, following ? liveCards.get(following) : null);
    }
    const medallion = node("span", "row-medallion");
    medallion.append(icon(row, "row-watermark"));
    cards.append(medallion);
    if (cards.children.length === 1) cards.append(node("span", "empty-row", droppable ? "Выложить сюда" : ROW_NAMES[row]));
    const special = node("div", `row-special ${slotMove ? "slot-droppable" : ""}`);
    if (slotMove) {
      special.tabIndex = 0; special.setAttribute("role", "button");
      special.setAttribute("aria-label", `Установить штандарт: ${ROW_NAMES[row]}`);
      special.addEventListener("click", event => { event.stopPropagation(); send(slotMove); });
      special.addEventListener("keydown", event => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.stopPropagation(); send(slotMove); }
      });
    }
    for (const card of player.specials.filter((item) => item.row === row)) special.append(cardNode(card, {small: true}));
    if (player.leader_horn.includes(row) && !special.children.length) {
      const standard = cardNode(definitions.get("horn"), {small: true, onClick: () => {
        const content = node("div");
        content.append(node("p", "eyebrow", "Способность Франциска"), node("h2", "", "Военная академия"), node("p", "", catalog.leaders.academy.description));
        showInfo(content);
      }});
      standard.classList.add("leader-standard"); standard.dataset.source = "leader";
      standard.title = `Военная академия: ${catalog.leaders.academy.description}`;
      standard.setAttribute("aria-label", standard.title);
      special.append(standard);
    }
    if (!special.children.length) special.append(icon("banner", "empty-slot"));
    result.append(label, special, cards);
    return result;
  }
  function closeChoice() { if ($("choice-dialog").open) $("choice-dialog").close(); }
  function renderChoices() {
    const game = state.game;
    if (!game.pending || game.pending.actor !== state.me) return closeChoice();
    const moves = usableMoves().filter((move) => move.type === "choose");
    const ownDiscard = game.players[state.me].discard;
    const ids = [...new Set(moves.map((move) => move.card_id))];
    $("choice-cards").replaceChildren(...ids.map((id) => {
      const card = ownDiscard.find((item) => item.id === id), item = node("div", "choice-item");
      const choices = moves.filter((move) => move.card_id === id);
      item.append(cardNode(card, {onClick: () => { if (choices.length === 1) send(choices[0]); }}));
      for (const move of choices) {
        const choose = button(`Вернуть: ${ROW_NAMES[move.row]}`, () => send(move), "primary");
        choose.dataset.choiceId = id; choose.dataset.choiceRow = move.row; item.append(choose);
      }
      return item;
    }));
    if (!ids.length) $("choice-cards").append(node("p", "muted", pendingVersion !== null ? "Сервер применяет выбор…" : "Дождитесь соединения с сервером."));
    if (!$("choice-dialog").open) $("choice-dialog").showModal();
  }

  async function enterRoom(join) {
    if (busy || !$("entry-form").reportValidity()) return;
    const name = $("player-name").value.trim();
    const code = $("room-code").value.trim().toUpperCase();
    if (join && code.length !== 8) return toast("Введите восьмизначный код комнаты.");
    busy = true; $("create-room").disabled = $("join-room").disabled = true;
    try {
      const next = await api(join ? `/api/rooms/${encodeURIComponent(code)}/join` : "/api/rooms", {name});
      writeStorage("frontiers.name", name); dirtyDeck = false; receive(next); connect(next.code);
    } catch (error) { toast(error.message); }
    finally { busy = false; $("create-room").disabled = $("join-room").disabled = false; render(); }
  }

  $("entry-form").addEventListener("submit", (event) => { event.preventDefault(); enterRoom(false); });
  $("join-room").addEventListener("click", () => enterRoom(true));
  $("fullscreen-button").addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", syncFullscreen);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") scheduleScorchFrame();
    else {
      cancelAnimationFrame(scorchFrame); scorchFrame = null; scorchTick = null;
      scorchFire.clear();
    }
  });
  $("room-code").addEventListener("input", () => { $("room-code").value = $("room-code").value.toUpperCase().replace(/[^A-Z2-9]/g, ""); });
  $("leader-select").addEventListener("change", () => { leader = $("leader-select").value; dirtyDeck = true; renderLobby(); });
  $("deck-preset").addEventListener("change", () => {
    const preset = catalog.decks[$("deck-preset").value];
    if (preset) { deck = [...preset.cards]; dirtyDeck = true; renderLobby(); }
  });
  $("collection-filter").addEventListener("change", renderLobby);
  $("ready-button").addEventListener("click", async () => {
    if (busy || !state) return;
    busy = true; renderLobby();
    try { receive(await api(`/api/rooms/${state.code}/ready`, {leader, deck, ready: !state.seats[state.me].ready})); }
    catch (error) { toast(error.message); }
    finally { busy = false; render(); }
  });
  $("mulligan-button").addEventListener("click", () => send({type: "mulligan", card_ids: [...swaps]}));
  $("mulligan-select").addEventListener("click", () => toggleMulligan(mulliganIndex));
  $("mulligan-prev").addEventListener("click", () => focusMulligan(mulliganIndex - 1));
  $("mulligan-next").addEventListener("click", () => focusMulligan(mulliganIndex + 1));
  $("mulligan-concede").addEventListener("click", () => $("concede-button").click());
  $("mulligan-home").addEventListener("click", () => $("leave-view").click());
  $("mulligan-dialog").addEventListener("cancel", event => event.preventDefault());
  $("result-dialog").addEventListener("cancel", event => { event.preventDefault(); dismissResult(); });
  $("result-continue").addEventListener("click", dismissResult);
  $("result-home").addEventListener("click", () => $("leave-view").click());
  document.addEventListener("keydown", event => {
    if (!$("mulligan-dialog").open) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      focusMulligan(mulliganIndex + (event.key === "ArrowLeft" ? -1 : 1), true);
    }
  });
  $("leader-button").addEventListener("click", openLeaderPreview);
  $("leader-cancel").addEventListener("click", closeLeaderPreview);
  $("leader-dialog").addEventListener("cancel", event => { event.preventDefault(); closeLeaderPreview(); });
  $("leader-apply").addEventListener("click", () => {
    if (!leaderPreview || !usableMoves().some(move => move.type === "leader")) return;
    closeLeaderPreview(); send({type: "leader"});
  });
  $("pass-button").addEventListener("click", () => send({type: "pass"}));
  $("concede-button").addEventListener("click", () => { if (confirm("Сдаться в этом матче?")) send({type: "concede"}); });
  $("copy-invite").addEventListener("click", async () => {
    const invite = `${location.origin}/?room=${state.code}`;
    try { await navigator.clipboard.writeText(invite); toast("Приглашение скопировано."); }
    catch { const content = node("div"); content.append(node("h2", "", "Приглашение другу")); const input = node("input"); input.value = invite; input.readOnly = true; content.append(input); showInfo(content); input.select(); }
  });
  $("leave-view").addEventListener("click", () => {
    disconnect(); state = null; selected = null; swaps.clear(); dirtyDeck = false;
    try { localStorage.removeItem("frontiers.room"); } catch {}
    history.replaceState(null, "", "/"); closeChoice(); status("Карточная дуэль для двоих"); render();
  });
  $("journal-button").addEventListener("click", () => {
    const content = node("div"); content.append(node("p", "eyebrow", "Хроника дуэли"), node("h2", "", "События матча"));
    const log = node("ol", "event-log"); log.id = "event-log";
    log.append(...[...state.game.events].reverse().map((event) => node("li", "", event)));
    content.append(log); showInfo(content);
  });
  for (const [id, own] of [["own-discard", true], ["enemy-discard", false]]) {
    $(id).addEventListener("click", () => {
      const cards = state.game.players[own ? state.me : 1 - state.me].discard;
      const content = node("div"); content.append(node("h2", "", own ? "Ваш сброс" : "Сброс соперника"));
      const list = node("div", "choice-cards");
      list.append(...cards.map((card) => cardNode(card)));
      if (!cards.length) list.append(node("p", "muted", "В сбросе пока нет карт."));
      content.append(list); showInfo(content);
    });
  }
  $("close-info").addEventListener("click", () => $("info-dialog").close());
  $("choice-dialog").addEventListener("cancel", (event) => event.preventDefault());
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && selected) { selected = null; if (state?.game) renderGame(); } });
  $("rules-button").addEventListener("click", () => {
    const content = node("div", "rules-copy"), list = node("ol");
    content.append(node("p", "eyebrow", "Перед первой дуэлью"), node("h2", "", "Как играть в Frontiers"));
    for (const text of ["Выберите колоду и одну способность Франциска. Нажмите «Готов к матчу».",
      "Начальная рука — 10 карт на весь матч. До первого хода можно заменить две карты.",
      "Игроки ходят по очереди: разыгрывают одну карту, используют лидера или пасуют. Дополнительные карты дают способности.",
      "Пас действует до конца раунда. Соперник может продолжать играть. Когда оба спасовали, побеждает большая суммарная сила.",
      "Поражение в раунде отнимает один из двух жетонов. Ничья отнимает жетон у обоих. Если жетоны закончились у обоих — ничья в матче.",
      "Герои защищены от погоды, усилений и Казни. Погода действует на обе стороны, штандарт — только на вашу.",
      "После раунда поле очищается. Бургундия добирает карту за выигранный раунд; обычного добора между раундами нет.",
      "Нажмите на карту, чтобы узнать её способность. После перезагрузки страницы вы вернётесь на своё место, пока сохранена сессия браузера."])
      list.append(node("li", "", text));
    content.append(list); showInfo(content);
  });

  async function boot() {
    syncFullscreen();
    new ResizeObserver(syncTableCardProportions).observe($("hand"));
    document.querySelector(".leader-portrait .card-art").replaceWith(leaderPortrait());
    $("create-room").disabled = $("join-room").disabled = true;
    $("player-name").value = readStorage("frontiers.name") || "";
    const invite = new URLSearchParams(location.search).get("room");
    $("room-code").value = (invite || "").toUpperCase();
    try {
      catalog = await api("/api/catalog");
      definitions = new Map(catalog.cards.map((card) => [card.key, card]));
      for (const [key, item] of Object.entries(catalog.leaders)) { const option = node("option", "", item.name); option.value = key; $("leader-select").append(option); }
      for (const [key, item] of Object.entries(catalog.decks)) { const option = node("option", "", item.name); option.value = key; $("deck-preset").append(option); }
      const custom = node("option", "", "Своя колода"); custom.value = "custom"; $("deck-preset").append(custom);
      $("create-room").disabled = $("join-room").disabled = false;
      const code = (invite || readStorage("frontiers.room") || "").toUpperCase();
      if (code) {
        try { const saved = await api(`/api/rooms/${encodeURIComponent(code)}`); receive(saved); connect(saved.code); }
        catch (error) { if (error.status !== 403) toast(error.message); }
      }
    } catch { toast("Не удалось загрузить карты. Проверьте соединение и обновите страницу."); }
  }
  boot();
})();
