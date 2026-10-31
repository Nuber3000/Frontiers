"use strict";

// Only small, public summaries and card keys are persisted; never artwork or hands.
window.FrontiersProfile = function (catalog) {
  const prefix = "frontiers.profile.v1.";
  const cards = new Map(catalog.cards.map(card => [card.key, card]));
  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(prefix + key)) ?? fallback; }
    catch { return fallback; }
  }
  function write(key, value) {
    try { localStorage.setItem(prefix + key, JSON.stringify(value)); }
    catch { throw new Error("Браузер не смог сохранить данные. Проверьте доступ к локальному хранилищу и свободное место."); }
  }
  function validDeck(item) {
    if (!item || !catalog.factions[item.faction]?.playable || catalog.leaders[item.leader]?.faction !== item.faction
        || !Array.isArray(item.cards) || item.cards.length > 60) return false;
    const counts = new Map();
    return item.cards.every(key => {
      const card = cards.get(key);
      counts.set(key, (counts.get(key) || 0) + 1);
      return card?.collectible && card.available !== false && [item.faction, "neutral"].includes(card.faction)
        && counts.get(key) <= card.copies;
    });
  }
  function decks() {
    const value = read("decks", []);
    return Array.isArray(value) ? value.filter(item => validDeck(item) && typeof item.id === "string"
      && typeof item.name === "string" && item.name.trim().length > 0 && item.name.length <= 40).slice(0, 50) : [];
  }
  function history() {
    const value = read("history", []);
    return Array.isArray(value) ? value.filter(item => item && typeof item.id === "string"
      && Number.isFinite(item.finishedAt) && ["victory", "defeat", "draw"].includes(item.outcome)
      && Array.isArray(item.players) && item.players.length === 2
      && item.players.every(player => typeof player?.name === "string" && player.name.length <= 32 && catalog.factions[player.faction])
      && Array.isArray(item.rounds) && item.rounds.length <= 3
      && item.rounds.every(round => Number.isInteger(round.round) && Array.isArray(round.scores) && round.scores.length === 2
        && round.scores.every(score => Number.isSafeInteger(score) && score >= 0))).slice(0, 100) : [];
  }
  return {
    decks, history,
    draft(faction) {
      faction = faction || read("lastFaction", "burgundy");
      const item = read("draft." + faction, null);
      return validDeck(item) && item.faction === faction ? item : null;
    },
    saveDraft(item) {
      if (!validDeck(item)) throw new Error("Эта колода содержит недоступные карты.");
      write("draft." + item.faction, {faction: item.faction, leader: item.leader, cards: [...item.cards]});
      write("lastFaction", item.faction);
    },
    saveDeck(name, item, id = null) {
      name = name.trim();
      if (!name || name.length > 40) throw new Error("Название колоды должно содержать от 1 до 40 символов.");
      if (!validDeck(item)) throw new Error("Эта колода содержит недоступные карты.");
      const items = decks();
      if (id && !items.some(deck => deck.id === id)) throw new Error("Сохранённая колода уже удалена.");
      if (!id && items.length >= 50) throw new Error("Можно сохранить до 50 колод. Удалите ненужную колоду.");
      const saved = {id: id || (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`),
        name, faction: item.faction, leader: item.leader, cards: [...item.cards]};
      write("decks", [saved, ...items.filter(deck => deck.id !== saved.id)]);
      return saved;
    },
    deleteDeck(id) { write("decks", decks().filter(deck => deck.id !== id)); },
    record(state) {
      const game = state.game;
      if (game?.phase !== "finished" || !game.match_id) return;
      const id = `${game.match_id}:${state.me}`, items = history();
      if (items.some(item => item.id === id)) return;
      const order = [state.me, 1 - state.me];
      const record = {id, finishedAt: Date.now(),
        outcome: game.winner === null ? "draw" : game.winner === state.me ? "victory" : "defeat",
        players: order.map(side => ({name: game.players[side].name, faction: game.players[side].faction})),
        rounds: game.history.map(round => ({round: round.round, scores: order.map(side => round.scores[side])}))};
      write("history", [record, ...items].slice(0, 100));
    },
  };
};
