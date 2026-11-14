"use strict";

window.FrontiersWeather = class {
  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.id = "weather-effects"; this.canvas.className = "weather-effects";
    this.canvas.setAttribute("aria-hidden", "true"); this.canvas.hidden = true;
    document.body.append(this.canvas);
    this.context = this.canvas.getContext("2d");
    this.rows = new Map(); this.frame = null; this.last = null; this.time = 0;
    this.sunlight = null; this.sunbeam = null;
    this.width = this.height = this.ratio = 0;
    this.motion = matchMedia("(prefers-reduced-motion: reduce)");
    this.clouds = null;
    this.resize = new ResizeObserver(() => { this.bounds(); this.schedule(); });
    const field = document.querySelector(".battlefield");
    if (field) this.resize.observe(field);
    window.addEventListener("resize", () => { this.bounds(); this.schedule(); });
    this.motion.addEventListener("change", () => {
      if (this.motion.matches) { this.sunlight = null; delete this.canvas.dataset.clearing; }
      if (this.motion.matches && !this.rows.size) { this.clear(); return; }
      this.last = null; this.schedule();
    });
    document.addEventListener("visibilitychange", () => {
      cancelAnimationFrame(this.frame); this.frame = null; this.last = null;
      if (document.hidden) this.canvas.hidden = true;
      else { this.bounds(); this.schedule(); }
    });
  }

  random(seed) {
    let state = 2166136261;
    for (const char of seed) state = Math.imul(state ^ char.charCodeAt(0), 16777619);
    return () => {
      state ^= state << 13; state ^= state >>> 17; state ^= state << 5;
      return (state >>> 0) / 4294967296;
    };
  }

  observe(previous, next) {
    const before = previous?.game, game = next.game;
    if (!before || !game || previous.code !== next.code || before.match_id !== game.match_id) {
      this.clear(); return;
    }
    // Reconnects and repeated snapshots must not replay a clearing animation.
    if (game.version !== before.version + 1 || this.motion.matches) return;
    if (game.weather.length > before.weather.length) {
      this.sunlight = null; delete this.canvas.dataset.clearing;
    }
    const cleared = game.played?.card?.key === "clear" || game.players.some((player, side) =>
      player.leader === "sun" && player.leader_used && !before.players[side].leader_used);
    if (cleared) {
      this.sunlight = {elapsed: 0, duration: 3.1, bounds: []};
      this.canvas.dataset.clearing = "true";
    }
  }

  update() {
    if (!this.context) return;
    const active = new Set();
    for (const element of document.querySelectorAll("#arena .combat-row[data-weather]")) {
      const effects = element.dataset.weather.split(" ").filter(Boolean);
      for (const effect of effects) {
        if (effect === "rain" && effects.includes("storm")) continue;
        const key = `${element.dataset.side}:${element.dataset.row}:${effect}`;
        active.add(key);
        let row = this.rows.get(key);
        if (!row) {
          row = {key, effects: [effect], progress: 0, opacity: 0, target: 1, bounds: null};
          this.rows.set(key, row);
        }
        row.target = 1;
      }
    }
    for (const [key, row] of this.rows) if (!active.has(key)) row.target = 0;
    this.bounds(); this.schedule();
  }

  bounds() {
    for (const row of this.rows.values()) {
      const [side, kind] = row.key.split(":");
      const element = document.querySelector(`#arena .combat-row[data-side="${side}"][data-row="${kind}"]`);
      const cards = element?.querySelector(".row-cards")?.getBoundingClientRect();
      // Keep the placement border visible and leave the separate boost slot dry.
      row.bounds = cards ? {x: cards.left + 1, y: cards.top + 1,
        width: Math.max(0, cards.width - 2), height: Math.max(0, cards.height - 2)} : null;
    }
    if (this.sunlight) this.sunlight.bounds = [...document.querySelectorAll("#arena .row-cards")].map(element => {
      const r = element.getBoundingClientRect();
      return {x: r.left + 1, y: r.top + 1, width: Math.max(0, r.width - 2), height: Math.max(0, r.height - 2)};
    });
  }

  schedule() {
    if (this.frame === null && (this.rows.size || this.sunlight) && !document.hidden && this.context)
      this.frame = requestAnimationFrame(time => this.draw(time));
  }

  clear() {
    cancelAnimationFrame(this.frame); this.frame = null; this.last = null;
    this.rows.clear(); this.context?.clearRect(0, 0, this.width, this.height);
    this.sunlight = null; delete this.canvas.dataset.clearing;
    this.canvas.hidden = true;
  }

  makeClouds() {
    return Array.from({length: 3}, (_, index) => {
      const canvas = document.createElement("canvas"); canvas.width = 256; canvas.height = 128;
      const context = canvas.getContext("2d"), random = this.random(`cloud-${index}`);
      for (let i = 0; i < 12; i++) {
        const x = 32 + random() * 192, y = 42 + random() * 40, radius = 24 + random() * 32;
        const gradient = context.createRadialGradient(x, y, 0, x, y, radius);
        gradient.addColorStop(0, "#e4e4dc55"); gradient.addColorStop(.45, "#cdd5d02a"); gradient.addColorStop(1, "#c5d1ce00");
        context.fillStyle = gradient; context.fillRect(0, 0, 256, 128);
      }
      return canvas;
    });
  }

  fog(context, row, storm = false) {
    const {width: w, height: h} = row.bounds;
    if (!this.clouds) this.clouds = this.makeClouds();
    const bed = context.createLinearGradient(0, h * .35, 0, h);
    bed.addColorStop(0, "#dbe2d800"); bed.addColorStop(.7, storm ? "#b0c7c210" : "#d6ddd82a");
    bed.addColorStop(1, storm ? "#adc0b922" : "#d3dcd738");
    context.fillStyle = bed; context.fillRect(0, h * .35, w, h * .65);
    const random = this.random(row.key + "fog"), count = Math.max(9, Math.ceil(w / 80));
    for (let i = 0; i < count; i++) {
      const width = 170 + random() * 160, height = h * (.38 + random() * .33);
      const speed = (storm ? 24 : 9) + random() * 9;
      const x = ((i * (w + 300) / count + this.time * speed) % (w + 300)) - 200;
      const y = h - height * (.65 + random() * .28) + Math.sin(this.time * .5 + i) * h * .035;
      context.globalAlpha = row.opacity * (storm ? .18 : .34);
      context.drawImage(this.clouds[i % 3], x, y, width, height);
    }
    context.globalAlpha = row.opacity;
  }

  makeFrost(row) {
    const {width: w, height: h} = row.bounds, random = this.random(row.key + "frost");
    const canvas = document.createElement("canvas"), ratio = this.ratio || 1;
    canvas.width = Math.ceil(w * ratio); canvas.height = Math.ceil(h * ratio);
    const context = canvas.getContext("2d"), pixels = context.createImageData(canvas.width, canvas.height);
    // A granular, uneven ice film, baked once per row size rather than every frame.
    const noise = (stepX, stepY) => {
      const columns = Math.ceil(w / stepX) + 2, rows = Math.ceil(h / stepY) + 2;
      const values = Float32Array.from({length: columns * rows}, random);
      return (x, y) => {
        const gx = x / stepX, gy = y / stepY, ix = Math.floor(gx), iy = Math.floor(gy);
        const sx = gx - ix, sy = gy - iy, u = sx * sx * (3 - 2 * sx), v = sy * sy * (3 - 2 * sy);
        const i = iy * columns + ix;
        return (values[i] * (1 - u) + values[i + 1] * u) * (1 - v)
          + (values[i + columns] * (1 - u) + values[i + columns + 1] * u) * v;
      };
    };
    const cloud = noise(53, 24), grain = noise(4, 3), fine = noise(1.4, 1.6);
    for (let py = 0; py < canvas.height; py++) {
      const y = py / ratio, bottom = (h - y) / h;
      for (let px = 0; px < canvas.width; px++) {
        const x = px / ratio, broad = cloud(x, y), detail = grain(x, y), speck = fine(x, y);
        const edge = Math.exp(-Math.min(x, w - x) / 15);
        const bank = Math.max(0, 1 - bottom / (.09 + broad * .14));
        const rime = Math.max(0, detail * .55 + speck * .45 - .47);
        const veil = Math.max(0, 1 - bottom / (.36 + broad * .43));
        const alpha = Math.min(.88, bank * bank * (.35 + speck * .5)
          + rime * veil * 1.1 + rime * edge * 1.3);
        const i = (py * canvas.width + px) * 4;
        const white = Math.min(1, bank * .7 + detail * .4);
        pixels.data[i] = 137 + white * 98;
        pixels.data[i + 1] = 177 + white * 64;
        pixels.data[i + 2] = 193 + white * 53;
        pixels.data[i + 3] = alpha * 255;
      }
    }
    context.putImageData(pixels, 0, 0); context.scale(ratio, ratio);
    const bed = context.createLinearGradient(0, h * .62, 0, h);
    bed.addColorStop(0, "#578aac00"); bed.addColorStop(.75, "#518db238"); bed.addColorStop(1, "#afdce35c");
    context.fillStyle = bed; context.fillRect(0, h * .62, w, h * .38);

    // Narrow translucent ice needles with bright facets, rooted in the frozen rim.
    const needle = (x, base, height, width, lean) => {
      const tip = x + lean, top = base - height;
      const facet = context.createLinearGradient(x - width, 0, x + width, 0);
      facet.addColorStop(0, "#88b9d000"); facet.addColorStop(.4, "#c7e7eb40");
      facet.addColorStop(.53, "#f1ffffbb"); facet.addColorStop(.68, "#9ecad955"); facet.addColorStop(1, "#80adc600");
      context.fillStyle = facet; context.beginPath(); context.moveTo(x - width, base);
      context.lineTo(tip, top); context.lineTo(x + width, base); context.closePath(); context.fill();
      context.strokeStyle = "#e7fbff88"; context.lineWidth = .45;
      context.beginPath(); context.moveTo(x, base); context.lineTo(tip, top); context.stroke();
    };
    for (let i = 0; i < Math.ceil(w / 42); i++) {
      const x = (i + .2 + random() * .6) * 42;
      const tall = random() < .26 || x < 22 || x > w - 30;
      const height = h * (tall ? .38 + random() * .53 : .04 + random() * .16);
      const base = h - random() * h * .04;
      needle(x, base, height, 1 + random() * 3, (random() - .5) * height * .12);
      for (let j = 0; j < 3; j++) {
        needle(x + (random() - .5) * 11, base, height * (.22 + random() * .44),
          .5 + random() * 1.5, (random() - .5) * height * .22);
      }
    }
    for (let i = 0; i < w * 2; i++) {
      const x = random() * w, y = h - random() ** 2 * h * .11;
      context.fillStyle = `rgba(231,250,250,${.12 + random() * .46})`;
      context.fillRect(x, y, .4 + random() * 2.3, .3 + random() * 1.1);
    }
    context.beginPath(); context.moveTo(0, h - 1.5);
    for (let x = 0; x <= w; x += 2) context.lineTo(x, h - 1.5 - random() ** 2 * 4);
    context.strokeStyle = "#e2faffad"; context.lineWidth = 1.3; context.stroke();
    return {canvas, width: w, height: h, ratio};
  }

  frost(context, row) {
    const {width: w, height: h} = row.bounds, random = this.random(row.key + "snow");
    if (!row.frost || row.frost.width !== w || row.frost.height !== h || row.frost.ratio !== this.ratio)
      row.frost = this.makeFrost(row);
    context.drawImage(row.frost.canvas, 0, 0, w, h);
    for (let i = 0; i < Math.min(36, w / 30); i++) {
      const x = (random() * w + this.time * (3 + random() * 6)) % w;
      const y = (random() * h + this.time * (2 + random() * 4)) % h;
      context.fillStyle = `rgba(218,242,250,${.16 + random() * .22})`;
      context.beginPath(); context.arc(x, y, .4 + random() * .8, 0, Math.PI * 2); context.fill();
    }
  }

  rain(context, row, storm = false) {
    const {width: w, height: h} = row.bounds, random = this.random(row.key + "rain");
    const count = Math.min(130, Math.ceil(w / (storm ? 9 : 13)));
    const slant = storm ? .38 : .08;
    context.lineWidth = storm ? .9 : .7;
    for (let i = 0; i < count; i++) {
      const length = h * (.12 + random() * .33), speed = 130 + random() * 160;
      const y = (random() * (h + length) + this.time * speed) % (h + length) - length;
      const x = (random() * (w + 80) - this.time * speed * slant % (w + 80) + w + 80) % (w + 80) - 40;
      context.strokeStyle = `rgba(191,218,230,${.12 + random() * .2})`;
      context.beginPath(); context.moveTo(x, y); context.lineTo(x - length * slant, y + length); context.stroke();
    }
    for (let i = 0; i < Math.min(30, w / 35); i++) {
      const x = random() * w, phase = (this.time * (1.4 + random()) + random()) % 1;
      context.strokeStyle = `rgba(198,226,235,${(1 - phase) * .24})`;
      context.beginPath(); context.ellipse(x, h - 2 - random() * 4, 1 + phase * 6, .5 + phase, 0, Math.PI, Math.PI * 2); context.stroke();
    }
    const damp = context.createLinearGradient(0, h * .6, 0, h);
    damp.addColorStop(0, "#b2cfdd00"); damp.addColorStop(1, "#b2cfdd22");
    context.fillStyle = damp; context.fillRect(0, h * .6, w, h * .4);
    if (storm) this.fog(context, row, true);
  }

  makeSunbeam() {
    const canvas = document.createElement("canvas"); canvas.width = 128; canvas.height = 512;
    const context = canvas.getContext("2d"), pixels = context.createImageData(128, 512);
    // Feather a cone once: every scaled ray retains the same point at its tip.
    for (let y = 0; y < 512; y++) {
      const distance = y / 512, halfWidth = Math.max(.5, distance * 64);
      const fade = Math.pow(1 - distance, .8) * Math.min(1, y / 6);
      for (let x = 0; x < 128; x++) {
        const edge = Math.max(0, 1 - Math.abs(x + .5 - 64) / halfWidth);
        const i = (y * 128 + x) * 4;
        pixels.data[i] = 255; pixels.data[i + 1] = 218; pixels.data[i + 2] = 134;
        pixels.data[i + 3] = Math.round(160 * edge * edge * fade);
      }
    }
    context.putImageData(pixels, 0, 0);
    return canvas;
  }

  clearSkies(context, delta) {
    const sun = this.sunlight;
    sun.elapsed = Math.min(sun.duration, sun.elapsed + delta);
    if (sun.elapsed >= sun.duration) {
      this.sunlight = null; delete this.canvas.dataset.clearing; return;
    }
    const bounds = sun.bounds.filter(r => r.width && r.height);
    if (!bounds.length) return;
    if (!this.sunbeam) this.sunbeam = this.makeSunbeam();
    const x = Math.min(...bounds.map(r => r.x)), y = Math.min(...bounds.map(r => r.y));
    const w = Math.max(...bounds.map(r => r.x + r.width)) - x;
    const h = Math.max(...bounds.map(r => r.y + r.height)) - y;
    const smooth = value => { const t = Math.max(0, Math.min(1, value)); return t * t * (3 - 2 * t); };
    const envelope = smooth(sun.elapsed / .55) * smooth((sun.duration - sun.elapsed) / .9);
    const progress = sun.elapsed / sun.duration;
    const random = this.random("clear-skies");
    context.save(); context.beginPath();
    for (const r of bounds) context.rect(r.x, r.y, r.width, r.height);
    context.clip(); context.translate(x + w * .025, y - h * .12);
    const length = Math.hypot(w, h) * 1.12;
    // Keep the warm haze close to the source and individual shafts.
    const radius = Math.min(w, h) * .75;
    const glow = context.createRadialGradient(0, 0, 0, 0, 0, radius);
    glow.addColorStop(0, "#ffcd6e80"); glow.addColorStop(.3, "#ffc45640");
    glow.addColorStop(.65, "#ffbc4020"); glow.addColorStop(1, "#ffbc4000");
    context.globalAlpha = envelope * (.87 + .13 * Math.sin(sun.elapsed * 1.2));
    context.fillStyle = glow; context.fillRect(-radius, -radius, radius * 2, radius * 2);
    for (let i = 0; i < 10; i++) {
      const angle = -.04 - random() * 1.12;
      const width = length * (.025 + Math.pow(random(), 1.6) * .14);
      const reach = length * (.65 + random() * .35);
      const phase = random() * Math.PI * 2, speed = .8 + random() * .9;
      const pulse = .66 + .34 * Math.sin(sun.elapsed * speed + phase);
      const brightness = envelope * pulse * (.45 + random() * .45);
      context.save();
      context.rotate(angle + progress * .045 + Math.sin(sun.elapsed * .45 + phase) * .006);
      context.globalAlpha = brightness * .32;
      context.drawImage(this.sunbeam, -width * 1.8, 0, width * 3.6, reach);
      context.globalAlpha = brightness;
      context.drawImage(this.sunbeam, -width / 2, 0, width, reach);
      context.restore();
    }
    context.globalAlpha = envelope;
    for (let i = 0; i < 18; i++) {
      const py = (random() * h - sun.elapsed * 6 + h) % h;
      const px = random() * Math.min(w * .55, py * .9 + 30);
      context.fillStyle = `rgba(255,235,170,${.08 + random() * .2})`;
      context.beginPath(); context.arc(px, py, .5 + random() * .7, 0, Math.PI * 2); context.fill();
    }
    context.restore();
  }

  draw(now) {
    this.frame = null;
    if (document.hidden) { this.last = null; this.canvas.hidden = true; return; }
    if (!document.body.classList.contains("in-match")) return this.clear();
    if (this.last !== null && now - this.last < 32 && !this.motion.matches) { this.schedule(); return; }
    const delta = this.last === null ? 1 / 30 : Math.min(.1, (now - this.last) / 1000);
    this.last = now;
    if (!this.motion.matches) this.time += delta;
    const width = innerWidth, height = innerHeight, ratio = Math.min(devicePixelRatio || 1, 1.25);
    if (width !== this.width || height !== this.height || ratio !== this.ratio) {
      this.width = width; this.height = height; this.ratio = ratio;
      this.canvas.width = Math.ceil(width * ratio); this.canvas.height = Math.ceil(height * ratio);
      this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    const context = this.context;
    context.clearRect(0, 0, width, height);
    for (const [key, row] of this.rows) {
      row.progress = this.motion.matches ? row.target
        : Math.max(0, Math.min(1, row.progress + (row.target ? delta / 1.1 : -delta / 1.65)));
      row.opacity = row.progress * row.progress * (3 - 2 * row.progress);
      if (!row.target && !row.progress) { this.rows.delete(key); continue; }
      if (!row.bounds?.width || !row.bounds?.height) continue;
      const {x, y, width: w, height: h} = row.bounds;
      context.save(); context.beginPath(); context.rect(x, y, w, h); context.clip(); context.translate(x, y);
      context.globalAlpha = row.opacity;
      const effects = row.effects;
      if (effects.includes("frost")) this.frost(context, row);
      if (effects.includes("fog")) this.fog(context, row);
      if (effects.includes("rain") || effects.includes("storm")) this.rain(context, row, effects.includes("storm"));
      context.restore();
    }
    if (this.sunlight) this.clearSkies(context, delta);
    this.canvas.hidden = !this.rows.size && !this.sunlight;
    if (!this.rows.size && !this.sunlight) { this.last = null; return; }
    if (!this.motion.matches) this.schedule();
  }
};
