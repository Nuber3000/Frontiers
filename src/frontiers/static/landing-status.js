"use strict";

(() => {
  const landing = document.getElementById("landing"), counter = document.getElementById("online-rooms");
  let count = null, timer = null, pending = null;
  function render() {
    counter.textContent = window.FrontiersI18n.t("Комнат в сети: {0}", count ?? "—");
  }
  function active() { return !landing.hidden && document.visibilityState === "visible"; }
  async function refresh() {
    timer = null;
    if (!active() || pending) return;
    const request = new AbortController(); pending = request;
    const timeout = setTimeout(() => request.abort(), 6000);
    try {
      const response = await fetch("/api/stats", {signal: request.signal, cache: "no-store"});
      if (!response.ok) throw new Error("stats");
      const data = await response.json();
      if (pending === request) { count = data.online_rooms; render(); }
    } catch {
      if (pending === request && active()) { count = null; render(); }
    } finally {
      clearTimeout(timeout);
      if (pending === request) {
        pending = null;
        if (active()) timer = setTimeout(refresh, 15000);
      }
    }
  }
  function sync() {
    if (!active()) {
      clearTimeout(timer); timer = null;
      pending?.abort(); pending = null;
    } else if (!pending && timer === null) refresh();
  }
  new MutationObserver(sync).observe(landing, {attributes: true, attributeFilter: ["hidden"]});
  document.addEventListener("visibilitychange", sync);
  window.addEventListener("pagehide", () => {
    pending?.abort(); pending = null; clearTimeout(timer); timer = null;
  });
  window.addEventListener("pageshow", sync);
  window.FrontiersRoomCounter = {localize: render};
  render(); sync();
})();
