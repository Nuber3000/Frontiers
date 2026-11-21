"use strict";

// Only guidance lives here. The regular arena renders cards, effects and sounds.
window.FrontiersTutorial = class {
  constructor({begin, prepare, start, cancel, exit}) {
    this.begin = begin;
    this.prepare = prepare; this.start = start; this.cancel = cancel; this.exit = exit;
    this.dialog = document.getElementById("tutorial-dialog");
    this.lessons = []; this.state = null; this.busy = false; this.serial = 0;
    const on = (id, event, callback) => document.getElementById(id).addEventListener(event, callback);
    on("tutorial-button", "click", () => this.begin());
    on("deck-tutorial-next", "click", () => this.deckContinue());
    on("deck-tutorial-exit", "click", () => { this.endDeck(); this.exit(); });
    document.addEventListener("click", event => this.deckInput(event), true);
    document.addEventListener("keydown", event => this.deckInput(event), true);
    window.addEventListener("resize", () => { this.scheduleDeckPosition(); this.scheduleBoardPosition(); });
    document.addEventListener("scroll", () => { this.scheduleDeckPosition(); this.scheduleBoardPosition(); }, true);
    const dialogs = new MutationObserver(() => this.scheduleBoardPosition());
    for (const dialog of document.querySelectorAll("dialog")) dialogs.observe(dialog, {attributes: true, attributeFilter: ["open"]});
    on("tutorial-close", "click", () => this.close());
    this.dialog.addEventListener("cancel", event => { event.preventDefault(); this.close(); });
    on("tutorial-retry", "click", () => { this.dialog.close(); this.state ? this.launch(this.state.id) : this.open(); });
    on("tutorial-restart", "click", () => this.launch(this.state.id));
    on("tutorial-exit", "click", () => this.exit());
    on("tutorial-next", "click", () => {
      const next = this.lessons[this.lessons.findIndex(item => item.id === this.state.id) + 1];
      if (next) this.launch(next.id); else this.exit();
    });
  }
  startDeck() {
    this.deckTour = {step: 0, added: null};
    this.deckTarget = null; this.positionedStep = -1;
  }
  endDeck() {
    this.deckTour = null; this.deckTarget = null; this.deckSpotlight = null;
    cancelAnimationFrame(this.deckFrame); this.deckFrame = null;
    document.getElementById("deck-tutorial-overlay").hidden = true;
    document.body.classList.remove("in-deck-tutorial");
  }
  allowDeckAction(kind, key) {
    if (!this.deckTour) return false;
    const required = [null, "faction", "leader", "add", "remove"][this.deckTour.step];
    return kind === required && (kind !== "remove" || key === this.deckTour.added);
  }
  deckAction(kind, {before, after, key}) {
    if (!this.allowDeckAction(kind, key) || before === after) return;
    if (kind === "add" && after !== before + 1) return;
    if (kind === "remove" && after !== before - 1) return;
    if (kind === "add") this.deckTour.added = key;
    this.deckTour.step++;
    this.renderDeck();
  }
  deckContinue() {
    if (this.deckTour?.step === 0) { this.deckTour.step = 1; this.renderDeck(); }
    else if (this.deckTour?.step === 5) {
      document.getElementById("deck-tutorial-overlay").hidden = true;
      this.open();
    }
  }
  renderDeck() {
    if (!this.deckTour) return;
    const steps = [
      ["Выбор колоды", "Это экран подготовки к матчу. Слева — доступные карты, справа — ваша колода, в центре — лидер и состав колоды. Сначала попробуем изменить их вместе.", null],
      ["Смените фракцию", "Откройте список фракций и выберите другую фракцию. У каждой — свои карты и особенность.", "#faction-select"],
      ["Смените карту лидера", "В списке под портретом выберите другой вариант карты лидера. Она меняет способность лидера; её описание показано ниже.", "#leader-select"],
      ["Добавьте карту в колоду", "Нажмите «+» на выделенной карте. Так вы добавите её в колоду, из которой будет собрана рука в начале матча.", "#collection .collection-item .card-adjust button:not(:disabled)"],
      ["Уберите карту из колоды", "Теперь нажмите «−» на только что добавленной карте справа. Карта вернётся в коллекцию. Так вы можете менять состав колоды перед матчем.", null],
      ["Размер колоды и шанс добора", "В колоде должно быть не меньше 22 отрядов и не больше 10 особых и погодных карт вместе. При увеличении числа карт в колоде, шанс выпадения нужной карты снижается. Добавляйте карты, которые помогают вашей стратегии.", "#deck-stats"],
    ];
    const step = this.deckTour.step, [title, text, selector] = steps[step];
    const overlay = document.getElementById("deck-tutorial-overlay");
    overlay.hidden = false; document.body.classList.add("in-deck-tutorial");
    overlay.dataset.step = String(step);
    document.getElementById("deck-tutorial-title").textContent = this.t(title);
    document.getElementById("deck-tutorial-text").textContent = this.t(text);
    document.getElementById("deck-tutorial-progress").textContent = this.t("Шаг {0} из {1}", step + 1, steps.length);
    const next = document.getElementById("deck-tutorial-next");
    next.hidden = step !== 0 && step !== 5;
    document.getElementById("ready-button").disabled = step !== 5 || this.busy;
    next.textContent = this.t(step === 5 ? "К сценариям на столе" : "Начать знакомство");
    this.deckTarget = step === 4
      ? document.querySelector(`#deck-cards .collection-item:has([data-card-key="${CSS.escape(this.deckTour.added)}"]) .card-adjust button`)
      : selector ? document.querySelector(selector) : null;
    // Keep the card itself visible around its small + / - control.
    this.deckSpotlight = this.deckTarget?.closest(".collection-item") || this.deckTarget;
    if (this.positionedStep !== step) {
      this.positionedStep = step;
      this.deckSpotlight?.scrollIntoView({block: "center", inline: "nearest"});
      (this.deckTarget || next).focus({preventScroll: true});
    }
    this.scheduleDeckPosition();
  }
  scheduleDeckPosition() {
    if (!this.deckTour || document.getElementById("deck-tutorial-overlay").hidden || this.deckFrame) return;
    this.deckFrame = requestAnimationFrame(() => { this.deckFrame = null; this.positionDeck(); });
  }
  positionDeck() {
    const overlay = document.getElementById("deck-tutorial-overlay");
    if (!this.deckTour || overlay.hidden) return;
    const coach = document.getElementById("deck-tutorial-coach");
    const focus = document.getElementById("deck-tutorial-focus");
    const width = document.documentElement.clientWidth, height = innerHeight, gap = 12;
    const rect = this.deckSpotlight?.getBoundingClientRect();
    const left = rect ? Math.max(0, rect.left - 6) : 0;
    const top = rect ? Math.max(0, rect.top - 6) : 0;
    const right = rect ? Math.min(width, rect.right + 6) : width;
    const bottom = rect ? Math.min(height, rect.bottom + 6) : 0;
    const place = (node, x, y, w, h) => Object.assign(node.style,
      {left: `${x}px`, top: `${y}px`, width: `${Math.max(0, w)}px`, height: `${Math.max(0, h)}px`});
    const masks = overlay.querySelectorAll(".deck-tutorial-mask");
    place(masks[0], 0, 0, width, top);
    place(masks[1], 0, bottom, width, height - bottom);
    place(masks[2], 0, top, left, bottom - top);
    place(masks[3], right, top, width - right, bottom - top);
    focus.hidden = !rect;
    if (rect) place(focus, left, top, right - left, bottom - top);
    this.placeCoach(coach, rect);
  }
  placeCoach(coach, rect, placement = null) {
    const width = document.documentElement.clientWidth, height = innerHeight, gap = 12;
    const left = rect ? Math.max(0, rect.left - 6) : 0;
    const top = rect ? Math.max(0, rect.top - 6) : 0;
    const right = rect ? Math.min(width, rect.right + 6) : width;
    const bottom = rect ? Math.min(height, rect.bottom + 6) : 0;
    const cw = coach.offsetWidth, ch = coach.offsetHeight;
    let x = (width - cw) / 2, y = (height - ch) / 2;
    if (placement === "center") {
      y -= 64;
      if (rect) y = Math.min(y, rect.top - ch - gap);
    }
    if (placement === "right" && rect) {
      x = width - cw - gap; y = rect.top + rect.height / 2 - ch / 2;
    } else if (rect && placement !== "center") {
      if (right + gap + cw <= width - gap) { x = right + gap; y = top; }
      else if (left - gap - cw >= gap) { x = left - gap - cw; y = top; }
      else if (bottom + gap + ch <= height - gap) { x = left; y = bottom + gap; }
      else { x = left; y = top - gap - ch; }
    }
    coach.style.left = `${Math.max(gap, Math.min(x, width - cw - gap))}px`;
    coach.style.top = `${Math.max(gap, Math.min(y, height - ch - gap))}px`;
  }
  deckInput(event) {
    const overlay = document.getElementById("deck-tutorial-overlay");
    if (!this.deckTour || overlay.hidden) return;
    const coach = document.getElementById("deck-tutorial-coach");
    if (event.type === "keydown" && event.key === "Tab") {
      const controls = [this.deckTarget, ...coach.querySelectorAll("button")].filter(node => node && !node.disabled && !node.hidden);
      const index = controls.indexOf(document.activeElement);
      const next = controls[(index + (event.shiftKey ? -1 : 1) + controls.length) % controls.length];
      event.preventDefault(); event.stopImmediatePropagation(); next?.focus();
      return;
    }
    if (event.type === "keydown" && event.key === "Escape") {
      // Let the browser close a native select before handling any other action.
      return;
    }
    if (coach.contains(event.target) || this.deckTarget?.contains(event.target)) return;
    event.preventDefault(); event.stopImmediatePropagation();
  }
  t(message, ...args) { return window.FrontiersI18n.t(message, ...args); }
  async open() {
    if (this.busy) return;
    const preparation = this.prepare();
    if (!preparation) return;
    const serial = ++this.serial;
    this.busy = true; this.error = "";
    this.dialog.showModal(); this.renderLoading();
    try {
      this.lessons = await preparation;
      if (serial !== this.serial) return;
      await this.start(this.lessons[0].id);
      if (serial === this.serial) this.dialog.close();
    } catch (error) {
      if (serial === this.serial) this.error = error.message;
    } finally {
      if (serial === this.serial) {
        this.busy = false; this.renderLoading(); this.render(this.state, this.game, this.blocked, this.selected);
      }
    }
  }
  close() {
    ++this.serial; this.busy = false;
    this.dialog.close(); this.cancel();
  }
  async launch(id) {
    if (this.busy) return;
    const serial = ++this.serial;
    this.busy = true; this.error = "";
    this.render(this.state, this.game, this.blocked, this.selected);
    try {
      await this.start(id);
    } catch (error) {
      if (serial === this.serial) {
        this.error = error.message;
        if (!this.dialog.open) this.dialog.showModal();
      }
    } finally {
      if (serial === this.serial) {
        this.busy = false; this.renderLoading(); this.render(this.state, this.game, this.blocked, this.selected);
      }
    }
  }
  loadingStage(stage) {
    const messages = {runtime: "Загружаем локальный движок обучения…", rules: "Подготавливаем правила и карты…", ready: "Обучение готово к запуску."};
    if (this.busy && messages[stage]) document.getElementById("tutorial-loading").textContent = this.t(messages[stage]);
  }
  renderLoading() {
    document.getElementById("tutorial-retry").hidden = !this.error;
    document.getElementById("tutorial-loading").hidden = !this.busy;
    document.getElementById("tutorial-menu-error").textContent = this.error ? window.FrontiersI18n.errorText(this.error) : "";
  }
  render(state, game, blocked = false, selected = null) {
    this.state = state; this.game = game; this.blocked = blocked; this.selected = selected;
    const guide = document.getElementById("tutorial-guide");
    guide.hidden = !state;
    document.body.classList.toggle("in-tutorial", !!state);
    document.querySelectorAll(".tutorial-target").forEach(node => node.classList.remove("tutorial-target"));
    if (!state) { document.getElementById("room").prepend(guide); return; }
    document.getElementById("tutorial-scenario-title").textContent = this.t(state.title);
    document.getElementById("tutorial-scenario-progress").textContent = this.t("Сценарий {0} из {1}", this.lessons.findIndex(lesson => lesson.id === state.id) + 1, this.lessons.length);
    document.getElementById("tutorial-progress").textContent = this.t("Шаг {0} из {1}", Math.min(state.step + 1, state.steps), state.steps);
    document.getElementById("tutorial-task").textContent = this.t(state.instruction);
    const description = document.getElementById("tutorial-description");
    description.textContent = this.t(state.description); description.hidden = state.complete;
    const next = document.getElementById("tutorial-next");
    next.hidden = !state.complete;
    next.textContent = this.t(state.id === this.lessons.at(-1)?.id ? "Завершить обучение" : "Следующий сценарий");
    for (const id of ["tutorial-restart", "tutorial-next"]) document.getElementById(id).disabled = blocked || this.busy;
    for (const move of game.moves) {
      const target = move.type === "leader" ? document.getElementById("leader-button")
        : move.type === "pass" ? document.getElementById("pass-button")
        : move.card_id ? document.querySelector(`#arena .card[data-card-id="${CSS.escape(move.card_id)}"], #choice-dialog .card[data-card-id="${CSS.escape(move.card_id)}"]`) : null;
      target?.classList.add("tutorial-target");
    }
    this.positionBoard();
  }
  scheduleBoardPosition() {
    if (!this.state || this.boardFrame) return;
    this.boardFrame = requestAnimationFrame(() => { this.boardFrame = null; this.positionBoard(); });
  }
  positionBoard() {
    if (!this.state) return;
    const guide = document.getElementById("tutorial-guide");
    const dialogs = [...document.querySelectorAll("dialog[open]")];
    const modal = dialogs.at(-1);
    // Keep guidance in the same top layer as the regular target-choice dialogs.
    const supported = modal?.id === "leader-dialog" || modal?.id === "choice-dialog";
    guide.hidden = !!modal && !supported;
    if (guide.hidden) return;
    const parent = supported ? modal : document.getElementById("room");
    if (guide.parentElement !== parent) parent.append(guide);
    let target = null;
    let instruction = this.state.instruction;
    const move = this.game.moves[0];
    if (modal?.id === "leader-dialog") {
      target = document.getElementById("leader-apply");
      instruction = "Нажмите «Применить», чтобы использовать способность лидера.";
    } else if (modal?.id === "choice-dialog") {
      target = document.querySelector("#choice-cards .card");
    } else if (this.state.complete) {
      target = document.getElementById("my-score");
    } else if (move?.type === "play" && this.game.moves.some(item => item.card_id === this.selected)) {
      target = move.row && document.querySelector(`.combat-row.own[data-row="${move.row}"] ${move.card_id && this.game.players[0].hand.find(card => card.id === move.card_id)?.key === "horn" ? ".row-special" : ".row-cards"}`);
      const play = document.querySelector("#selection-info .primary");
      if (play) {
        target = play;
        instruction = "Нажмите «Сыграть», чтобы разыграть выбранную карту.";
      } else {
        instruction = "Нажмите на подсвеченное место усиления в осадном ряду.";
      }
    } else {
      target = document.querySelector("#arena .tutorial-target");
    }
    document.getElementById("tutorial-task").textContent = this.t(instruction);
    let bounds = target?.getBoundingClientRect(), placement = null;
    if (!modal && this.state.id === "boosts" && this.state.step >= 2) {
      bounds = document.querySelector('.combat-row.own[data-row="siege"]').getBoundingClientRect();
      placement = "center";
    } else if (!modal && this.state.id === "abilities" && document.documentElement.clientWidth >= 900) {
      // The empty area on the right of the melee row keeps the hand and played units visible.
      bounds = document.querySelector('.combat-row.own[data-row="melee"]').getBoundingClientRect();
      placement = "right";
    }
    this.placeCoach(guide, bounds, placement);
  }
};
