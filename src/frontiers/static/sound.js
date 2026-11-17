"use strict";

window.FrontiersAudio = (() => {
  const storageKey = "frontiers.sound";
  const outputGain = .35 * 1.3 * 2;
  const musicGain = .25;
  let enabled = true, volume = .25, context = null, master = null, noiseBuffer = null;
  let musicVolume = .2, music = null, musicUnlocked = false, musicStarting = false;
  let fireBuffer = null, fireLoading = null, fireLevel = 0, nextFireAttempt = 0;
  let lastMatch = null, lastVersion = -1, resultPending = null;
  let audioEpoch = 0;
  const recordings = new Map(["horn", "frost", "fog", "storm", "clear", "turn", "round-win", "round-loss", "round-draw", "draw", "victory", "defeat"].map(kind =>
    [kind, {file: `/static/audio/sound-${kind}.ogg`, buffer: null, loading: null, retryAt: 0, level: 0}]));
  const voices = new Set();
  const burns = new Set();
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (typeof saved?.enabled === "boolean") enabled = saved.enabled;
    if (Number.isFinite(saved?.volume)) volume = Math.max(0, Math.min(1, saved.volume));
    if (Number.isFinite(saved?.musicVolume)) musicVolume = Math.max(0, Math.min(1, saved.musicVolume));
  } catch {}

  function syncMusic() {
    if (!musicUnlocked || !musicVolume || document.hidden) { music?.pause(); return; }
    if (!music) {
      // Stream long music instead of decoding the entire track into an AudioBuffer.
      music = new Audio("/static/audio/music-background.ogg");
      music.preload = "none";
      music.loop = true;
    }
    music.volume = musicVolume * musicGain;
    if (!music.paused || musicStarting) return;
    musicStarting = true;
    music.play().then(() => {
      if (!musicVolume || document.hidden) music.pause();
    }).catch(() => {}).finally(() => { musicStarting = false; });
  }

  function stop() {
    audioEpoch++;
    for (const source of voices) { try { source.stop(); } catch {} }
    voices.clear();
  }
  function unlock(event) {
    if (event && !event.isTrusted) return;
    if (event) musicUnlocked = true;
    syncMusic();
    if (!enabled || !volume || document.hidden) return;
    try {
      if (!context) {
        const Audio = window.AudioContext || window.webkitAudioContext;
        if (!Audio) return;
        context = new Audio();
        master = context.createGain();
        master.gain.value = volume * outputGain;
        master.connect(context.destination);
      }
      if (context.state === "suspended") context.resume().catch(() => {});
      prepareFire();
      for (const kind of recordings.keys()) prepareRecording(kind);
    } catch {} // Sound support must never prevent a game from starting.
  }
  document.addEventListener("pointerdown", unlock, {capture: true, passive: true});
  document.addEventListener("keydown", event => { if (!event.repeat) unlock(event); }, true);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      music?.pause();
      stop();
      if (context?.state === "running") context.suspend().catch(() => {});
    } else if (context || musicUnlocked) unlock();
  });

  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify({enabled, volume, musicVolume})); } catch {}
    if (master) master.gain.setTargetAtTime(enabled ? volume * outputGain : 0, context.currentTime, .015);
    if (!enabled || !volume) stop();
    syncMusic();
    syncControls();
  }
  function track(source, nodes) {
    voices.add(source);
    source.onended = () => {
      voices.delete(source);
      source.disconnect();
      for (const node of nodes) node.disconnect();
    };
  }
  function envelope(gain, start, duration, level) {
    gain.gain.setValueAtTime(.0001, start);
    gain.gain.exponentialRampToValueAtTime(level, start + Math.min(.012, duration / 4));
    gain.gain.exponentialRampToValueAtTime(.0001, start + duration);
  }
  function tone(frequency, end, delay = 0, duration = .12, level = .12, type = "triangle") {
    const oscillator = context.createOscillator(), gain = context.createGain();
    const start = context.currentTime + delay;
    oscillator.type = type;
    oscillator.frequency.setValueAtTime(frequency, start);
    oscillator.frequency.exponentialRampToValueAtTime(end, start + duration);
    envelope(gain, start, duration, level);
    oscillator.connect(gain); gain.connect(master);
    track(oscillator, [gain]); oscillator.start(start); oscillator.stop(start + duration + .02);
  }
  function noise(delay, duration, frequency, level) {
    if (!noiseBuffer) {
      noiseBuffer = context.createBuffer(1, context.sampleRate, context.sampleRate);
      const data = noiseBuffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    }
    const source = context.createBufferSource(), filter = context.createBiquadFilter(), gain = context.createGain();
    const start = context.currentTime + delay;
    source.buffer = noiseBuffer;
    filter.type = "lowpass"; filter.frequency.value = frequency; filter.Q.value = .5;
    envelope(gain, start, duration, level);
    source.connect(filter); filter.connect(gain); gain.connect(master);
    track(source, [gain, filter]); source.start(start, Math.random() * .1); source.stop(start + duration + .02);
  }
  function melody(notes, spacing = .1, duration = .25, level = .1) {
    notes.forEach((frequency, index) => tone(frequency, frequency * .998, index * spacing, duration, level));
  }
  function recordingLevel(buffer, target = .025) {
    let peak = 0, loudness = 0;
    const windowSize = Math.round(buffer.sampleRate * .1);
    for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
      const data = buffer.getChannelData(channel);
      let energy = 0;
      for (let i = 0; i < data.length; i++) {
        peak = Math.max(peak, Math.abs(data[i]));
        energy += data[i] * data[i];
        if (i >= windowSize) energy -= data[i - windowSize] ** 2;
        loudness = Math.max(loudness, Math.sqrt(Math.max(0, energy) / windowSize));
      }
    }
    return Math.min(.11 / Math.max(peak, .001), target / Math.max(loudness, .001));
  }
  function prepareRecording(kind) {
    const sample = recordings.get(kind);
    if (sample.buffer) return Promise.resolve(true);
    if (sample.loading) return sample.loading;
    if (performance.now() < sample.retryAt) return Promise.resolve(false);
    sample.loading = fetch(sample.file, {cache: "force-cache"})
      .then(response => {
        if (!response.ok) throw new Error("Sound unavailable");
        return response.arrayBuffer();
      })
      .then(bytes => context.decodeAudioData(bytes))
      .then(buffer => {
        sample.level = recordingLevel(buffer, ["fog", "storm"].includes(kind) ? .02 : .025);
        sample.buffer = buffer;
        return true;
      })
      .catch(() => { sample.retryAt = performance.now() + 30000; return false; })
      .finally(() => { sample.loading = null; });
    return sample.loading;
  }
  function recording(kind) {
    const sample = recordings.get(kind);
    if (!sample.buffer) {
      const epoch = audioEpoch;
      prepareRecording(kind).then(ready => {
        if (ready && epoch === audioEpoch) play(kind);
      });
      return;
    }
    const source = context.createBufferSource(), gain = context.createGain();
    const start = context.currentTime, duration = sample.buffer.duration;
    const fadeOut = Math.min(kind === "fog" ? .9 : .08, duration / 2);
    source.buffer = sample.buffer;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(sample.level, start + Math.min(.008, duration / 4));
    gain.gain.setValueAtTime(sample.level, start + Math.max(.008, duration - fadeOut));
    gain.gain.linearRampToValueAtTime(0, start + duration);
    source.connect(gain); gain.connect(master);
    track(source, [gain]); source.start(start); source.stop(start + duration);
  }
  function prepareFire() {
    if (fireBuffer || fireLoading || performance.now() < nextFireAttempt) return;
    fireLoading = fetch("/static/audio/scorch-fire.ogg", {cache: "force-cache"})
      .then(response => {
        if (!response.ok) throw new Error("Fire sound unavailable");
        return response.arrayBuffer();
      })
      .then(bytes => context.decodeAudioData(bytes))
      .then(buffer => {
        // Match the loudest 100 ms to the other effects, not just the peak.
        fireLevel = recordingLevel(buffer);
        fireBuffer = buffer;
      })
      .catch(() => { nextFireAttempt = performance.now() + 30000; })
      .finally(() => { fireLoading = null; });
  }
  function fire(milliseconds) {
    if (!fireBuffer) { noise(0, Math.min(.5, (milliseconds || 900) / 1000), 1300, .06); return; }
    const source = context.createBufferSource(), gain = context.createGain();
    const start = context.currentTime;
    const duration = Math.min(fireBuffer.duration, (milliseconds || window.FrontiersFire?.duration || 900) / 1000);
    source.buffer = fireBuffer;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(fireLevel, start + .006);
    gain.gain.setValueAtTime(fireLevel, start + Math.max(.006, duration - .18));
    gain.gain.linearRampToValueAtTime(0, start + duration);
    source.connect(gain); gain.connect(master);
    track(source, [gain]); source.start(start); source.stop(start + duration);
  }
  function play(kind, milliseconds) {
    if (!enabled || !volume || document.hidden || context?.state !== "running" || voices.size > 32) return;
    try {
      if (recordings.has(kind)) { recording(kind); return; }
      switch (kind) {
        case "select": tone(520, 400, 0, .045, .035, "sine"); break;
        case "card": noise(0, .12, 1500, .22); tone(150, 65, .05, .09, .16); break;
        case "shuffle":
          for (let i = 0; i < 4; i++) noise(i * .065, .07, 1800 + i * 300, .18);
          break;
        case "leader": melody([196, 294, 392], .07, .35, .13); noise(0, .2, 650, .12); break;
        case "scorch": fire(milliseconds); break;
        case "pass": tone(120, 55, 0, .13, .18); tone(95, 45, .15, .1, .12); break;
      }
    } catch {} // Audio device changes and unavailable outputs are harmless.
  }

  function burn(match, version, milliseconds = window.FrontiersFire?.duration || 900, phase = "table") {
    const key = `${match}:${version}:${phase}`;
    if (burns.has(key)) return;
    burns.add(key);
    if (burns.size > 32) burns.delete(burns.values().next().value);
    play("scorch", milliseconds);
  }

  function observe(previous, next) {
    const before = previous?.game, game = next.game;
    if (!game) { lastMatch = null; lastVersion = -1; resultPending = null; return; }
    if (game.match_id !== lastMatch) {
      stop(); burns.clear();
      lastMatch = game.match_id; lastVersion = game.version; resultPending = null;
      if (previous?.code === next.code && game.phase === "mulligan") play("shuffle");
      return;
    }
    if (game.version <= lastVersion) return;
    lastVersion = game.version;
    // Reconnecting to a newer snapshot must not replay missed actions.
    if (!before || before.match_id !== game.match_id || game.version !== before.version + 1) return;
    // Burning is sounded by the first visible animation frame, not receipt of state.
    if (!game.scorched?.length && game.played?.card?.key !== "scorch") {
      if (game.played?.card) {
        const card = game.played.card;
        play(card.key === "rain" ? "storm" : ["horn", "frost", "fog", "storm", "clear"].includes(card.key) ? card.key : card.abilities?.includes("horn") ? "horn" : "card");
      } else if (game.leader_played != null || game.players.some((player, side) => player.leader_used && !before.players[side].leader_used)) {
        const leader = game.leader_played != null ? game.players[game.leader_played].leader : game.players.find((player, side) => player.leader_used && !before.players[side].leader_used).leader;
        const effect = {academy: "horn", skone_horn: "horn", ellifarn_aim: "horn", fog: "fog", skone_storm: "storm", shiron_rain: "storm", sun: "clear"};
        play(effect[leader] || "leader");
      }
      else if (before.phase === "mulligan" && game.players[next.me].mulligan_done
          && !before.players[next.me].mulligan_done
          && game.players[next.me].hand?.some(card => !before.players[next.me].hand.some(old => old.id === card.id))) play("shuffle");
    }
    if (game.phase === "finished" && before.phase !== "finished") resultPending = game.match_id;
  }
  function result(match, kind) {
    if (resultPending !== match) return;
    resultPending = null;
    play(kind);
  }
  function notice(kind) {
    if (kind === "your-turn") play("turn");
    else if (["pass", "round-win", "round-loss", "round-draw"].includes(kind)) play(kind);
  }

  function syncControls() {
    const button = document.getElementById("sound-button");
    if (!button) return;
    const {t} = window.FrontiersI18n;
    button.title = t("Настройки звука");
    button.setAttribute("aria-label", t("Настройки звука"));
    button.dataset.muted = String((!enabled || !volume) && !musicVolume);
    document.getElementById("sound-enabled").checked = enabled;
    document.getElementById("sound-volume").value = Math.round(volume * 100);
    document.getElementById("sound-level").textContent = `${Math.round(volume * 100)}%`;
    document.getElementById("music-volume").value = Math.round(musicVolume * 100);
    document.getElementById("music-level").textContent = `${Math.round(musicVolume * 100)}%`;
  }
  function bindControls() {
    const dialog = document.getElementById("sound-dialog");
    document.getElementById("sound-button").addEventListener("click", () => { syncControls(); dialog.showModal(); });
    document.getElementById("sound-close").addEventListener("click", () => dialog.close());
    document.getElementById("sound-enabled").addEventListener("change", event => {
      enabled = event.target.checked; save(); unlock();
    });
    document.getElementById("sound-volume").addEventListener("input", event => {
      volume = Number(event.target.value) / 100; save(); unlock();
    });
    document.getElementById("music-volume").addEventListener("input", event => {
      musicVolume = Number(event.target.value) / 100; save(); unlock();
    });
    document.getElementById("sound-preview").addEventListener("click", () => {
      unlock();
      if (context?.state === "suspended") context.resume().then(() => play("card")).catch(() => {});
      else play("card");
    });
    syncControls();
  }
  return {play, burn, stop, observe, notice, result, bindControls, syncControls};
})();
