"use strict";

/* Общий холст над столом: мягкие частицы огня, дым и тлеющий край карты. */
(() => {
  class FrontiersFire {
    constructor() {
      this.canvas = document.createElement("canvas");
      this.canvas.id = "scorch-effects"; this.canvas.className = "scorch-effects";
      this.canvas.setAttribute("aria-hidden", "true"); this.canvas.hidden = true;
      document.body.append(this.canvas);
      this.context = this.canvas.getContext("2d");
      this.width = this.height = this.ratio = 0;
      this.sprites = null;
    }
    prepare(burn, id) {
      let seed = 2166136261;
      for (const char of id) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619);
      burn.random = () => {
        seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
        return (seed >>> 0) / 4294967296;
      };
      burn.profile = Array.from({length: 17}, () => burn.random() - .5);
      burn.particles = []; burn.emission = 0;
    }
    edge(burn, x, progress) {
      const stage = progress < .18 ? [0, .18, 1, .97, 0, .025]
        : progress < .6 ? [.18, .6, .97, .5, .025, .09] : [.6, 1, .5, 0, .09, 0];
      const t = Math.max(0, Math.min(1, (progress - stage[0]) / (stage[1] - stage[0])));
      const position = Math.max(0, Math.min(16, x * 16)), index = Math.min(15, Math.floor(position));
      const roughness = burn.profile[index] + (burn.profile[index + 1] - burn.profile[index]) * (position - index);
      return Math.max(0, Math.min(1, stage[2] + (stage[3] - stage[2]) * t + roughness * (stage[4] + (stage[5] - stage[4]) * t)));
    }
    clip(burn, progress) {
      const edge = burn.profile.map((_, index) => `${index / 16 * 100}% ${this.edge(burn, index / 16, progress) * 100}%`).reverse();
      return `polygon(0 0,100% 0,${edge.join(",")})`;
    }
    sprite(stops) {
      const canvas = document.createElement("canvas"); canvas.width = canvas.height = 64;
      const context = canvas.getContext("2d"), gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
      for (const [offset, color] of stops) gradient.addColorStop(offset, color);
      context.fillStyle = gradient; context.fillRect(0, 0, 64, 64);
      return canvas;
    }
    emit(burn, progress) {
      const random = burn.random, x = .03 + random() * .94, y = this.edge(burn, x, progress);
      burn.particles.push({kind: "fire", x, y, age: 0, life: .22 + random() * .42,
        vx: (random() - .5) * .2, vy: .3 + random() * .55, size: .06 + random() * .12, phase: random() * 6.28});
      if (random() < .23) burn.particles.push({kind: "smoke", x, y: y - .04, age: 0,
        life: .65 + random() * .65, vx: (random() - .5) * .17, vy: .14 + random() * .2,
        size: .12 + random() * .16, phase: random() * 6.28});
      if (random() < .12) burn.particles.push({kind: "ember", x, y, age: 0,
        life: .45 + random() * .5, vx: (random() - .5) * .5, vy: .55 + random() * .5,
        size: .008 + random() * .01, phase: random() * 6.28});
    }
    draw(burns, milliseconds) {
      if (!this.context) return;
      const active = [...burns.values()].filter(burn => burn.started && !burn.reduced);
      if (!active.length) return this.clear();
      if (!this.sprites) this.sprites = {
        fire: this.sprite([[0, "#fff8bdee"], [.2, "#ffd65cbb"], [.5, "#ff691444"], [1, "#b7200000"]]),
        smoke: this.sprite([[0, "#403b3655"], [.5, "#37322b22"], [1, "#24201a00"]]),
      };
      const width = innerWidth, height = innerHeight, ratio = Math.min(devicePixelRatio || 1, 1.5);
      if (width !== this.width || height !== this.height || ratio !== this.ratio) {
        this.width = width; this.height = height; this.ratio = ratio;
        this.canvas.width = Math.ceil(width * ratio); this.canvas.height = Math.ceil(height * ratio);
        this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
      this.canvas.hidden = false;
      const context = this.context, seconds = milliseconds / 1000;
      context.clearRect(0, 0, width, height);
      for (const burn of active) {
        const bounds = burn.element.getBoundingClientRect(), row = burn.element.parentElement?.getBoundingClientRect();
        if (!row || bounds.right < row.left || bounds.left > row.right || bounds.bottom < 0 || bounds.top > height) continue;
        const progress = Math.min(1, burn.elapsed / burn.duration);
        const fade = Math.min(1, progress * 12, (1 - progress) * 5);
        burn.emission += seconds * 150;
        while (burn.emission >= 1) { burn.emission--; if (progress < .94 && burn.particles.length < 200) this.emit(burn, progress); }
        for (const particle of burn.particles) {
          particle.age += seconds;
          particle.x += particle.vx * seconds;
          particle.y -= particle.vy * seconds;
        }
        burn.particles = burn.particles.filter(particle => particle.age < particle.life);
        context.save();
        context.beginPath(); context.rect(row.left + 1, row.top - bounds.height * .5, row.width - 2, row.height + bounds.height); context.clip();
        for (const kind of ["smoke", "fire", "ember"]) {
          context.globalCompositeOperation = kind === "smoke" ? "source-over" : "lighter";
          for (const particle of burn.particles) {
            if (particle.kind !== kind) continue;
            const life = particle.age / particle.life;
            const curl = Math.sin(particle.phase + particle.age * 11) * .025 * life;
            const x = bounds.left + (particle.x + curl) * bounds.width, y = bounds.top + particle.y * bounds.height;
            const size = particle.size * bounds.width;
            context.globalAlpha = Math.sin(life * Math.PI) * fade * (kind === "fire" ? .62 : .8);
            if (kind === "ember") {
              context.fillStyle = life < .45 ? "#ffdf80" : "#dc6024";
              context.fillRect(x, y, Math.max(1, size), Math.max(1.5, size * 1.6));
            } else {
              const spread = kind === "smoke" ? 1 + life * 2 : .9 + (1 - life) * .7;
              const w = size * spread, h = w * (kind === "fire" ? 1.8 : 1.1);
              context.drawImage(this.sprites[kind], x - w / 2, y - h / 2, w, h);
            }
          }
        }
        context.globalCompositeOperation = "source-over"; context.globalAlpha = fade;
        context.beginPath();
        for (let index = 0; index <= 32; index++) {
          const x = bounds.left + index / 32 * bounds.width;
          const y = bounds.top + this.edge(burn, index / 32, progress) * bounds.height;
          if (!index) context.moveTo(x, y); else context.lineTo(x, y);
        }
        context.lineWidth = 3; context.strokeStyle = "#21170f"; context.stroke();
        context.lineWidth = 1.1; context.strokeStyle = "#ffb23c";
        context.shadowColor = "#ff5217"; context.shadowBlur = 7; context.stroke();
        context.restore();
      }
    }
    clear() {
      this.context?.clearRect(0, 0, this.width, this.height);
      this.canvas.hidden = true;
    }
  }
  window.FrontiersFire = FrontiersFire;
})();
