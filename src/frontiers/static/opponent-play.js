"use strict";

/* Визуальный показ уже подтверждённой карты; правила остаются на сервере. */
(() => {
  class FrontiersOpponentPlay {
    constructor() {
      this.layer = null; this.frame = null; this.step = null; this.token = null;
      this.animations = []; this.target = null; this.fire = null;
      document.addEventListener("visibilitychange", () => {
        if (this.step) this.step.tick = null;
        if (document.visibilityState === "visible") this.schedule();
        else { cancelAnimationFrame(this.frame); this.frame = null; this.fire?.clear(); }
      });
    }
    schedule() {
      if (this.frame === null && this.step && document.visibilityState === "visible")
        this.frame = requestAnimationFrame(time => this.advance(time));
    }
    advance(time) {
      this.frame = null;
      const step = this.step;
      if (!step || document.visibilityState !== "visible") return;
      const delta = step.tick === null ? 16 : Math.max(0, Math.min(50, time - step.tick));
      step.tick = time; step.elapsed = Math.min(step.duration, step.elapsed + delta);
      step.update(step.elapsed, delta);
      if (step.elapsed >= step.duration) { this.step = null; step.resolve(true); }
      this.schedule();
    }
    stage(duration, update) {
      return new Promise(resolve => { this.step = {duration, update, resolve, elapsed: 0, tick: null}; this.schedule(); });
    }
    animate(element, frames, duration, easing = "ease-in-out") {
      const animation = element.animate(frames, {duration, easing, fill: "both"});
      animation.pause(); animation.currentTime = 0; animation.finished.catch(() => {});
      this.animations.push(animation); return animation;
    }
    clear() {
      this.token = null;
      cancelAnimationFrame(this.frame); this.frame = null;
      if (this.step) { const step = this.step; this.step = null; step.resolve(false); }
      for (const animation of this.animations) animation.cancel();
      this.animations = [];
      this.target?.classList.remove("opponent-arrival"); this.target = null;
      this.layer?.remove(); this.layer = null; this.fire?.clear();
    }
    async play(card, {scorch, commit, destination}) {
      this.clear();
      const token = {}; this.token = token;
      const layer = document.createElement("section"), wrapper = document.createElement("div");
      layer.id = "opponent-play"; layer.className = "opponent-play";
      layer.setAttribute("aria-label", "Карта соперника"); layer.setAttribute("aria-live", "polite");
      wrapper.className = "opponent-play-card"; wrapper.append(card); layer.append(wrapper);
      card.disabled = true; card.tabIndex = -1;
      document.body.append(layer); this.layer = layer;
      try {
        layer.dataset.stage = "reveal";
        const reveal = this.animate(wrapper, [
          {opacity: 0, transform: "translate(28px,-50%) scale(.82)"},
          {opacity: 1, transform: "translate(0,-50%) scale(1)"},
        ], 250, "ease-out");
        if (!await this.stage(250, time => { reveal.currentTime = time; })) return false;
        if (!await this.stage(450, () => {})) return false;
        if (scorch) {
          layer.dataset.stage = "burn";
          if (!this.fire) this.fire = new window.FrontiersFire("opponent-fire-effects");
          const burn = {element: wrapper, image: card, elapsed: 0, duration: 900, started: true, reduced: false};
          this.fire.prepare(burn, card.dataset.cardId || "played-scorch");
          const animation = this.animate(card, [
            {offset: 0, opacity: 1, filter: "brightness(1)", clipPath: this.fire.clip(burn, 0)},
            {offset: .55, opacity: 1, filter: "brightness(.5) sepia(.7)", clipPath: this.fire.clip(burn, .55)},
            {offset: 1, opacity: 0, filter: "brightness(.1)", clipPath: this.fire.clip(burn, 1)},
          ], burn.duration, "linear");
          const burns = new Map([["played", burn]]);
          if (!await this.stage(burn.duration, (time, delta) => {
            burn.elapsed = time; animation.currentTime = time; this.fire.draw(burns, delta);
          })) return false;
          this.fire.clear(); commit();
        } else {
          commit();
          if (this.token !== token) return false;
          layer.dataset.stage = "flight";
          const target = destination();
          const from = wrapper.getBoundingClientRect(), to = target?.getBoundingClientRect();
          if (to?.width && to?.height) {
            this.target = target; target.classList.add("opponent-arrival");
            const x = to.left + to.width / 2 - from.left - from.width / 2;
            const y = to.top + to.height / 2 - from.top - from.height / 2;
            const scale = Math.min(to.width / from.width, to.height / from.height);
            const flight = this.animate(wrapper, [
              {transform: "translate(0,-50%) scale(1)", opacity: 1},
              {transform: `translate(${x}px,calc(-50% + ${y}px)) scale(${scale})`, opacity: .7},
            ], 420, "cubic-bezier(.4,0,.2,1)");
            if (!await this.stage(420, time => { flight.currentTime = time; })) return false;
          } else {
            const fade = this.animate(wrapper, [{opacity: 1}, {opacity: 0}], 220);
            if (!await this.stage(220, time => { fade.currentTime = time; })) return false;
          }
        }
        return true;
      } finally { if (this.token === token) this.clear(); }
    }
  }
  window.FrontiersOpponentPlay = FrontiersOpponentPlay;
})();
