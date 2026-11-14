"""Bounded local AI. Search uses public information and sampled hidden cards."""

from collections import Counter
from copy import deepcopy
import math
import random
import time

from frontiers.catalog import CATALOG, LEADERS
from frontiers.engine import Game
from frontiers.models import CardInstance


BOT = 1
DIFFICULTIES = ("easy", "normal", "hard")


def card_value(key: str) -> float:
    card = CATALOG[key]
    if card.kind != "unit":
        return {"ting": 15, "scorch": 10, "horn": 9, "decoy": 8,
                "mushroom": 6, "clear": 5}.get(key, 4)
    bonuses = {"spy": 14, "medic": 9, "muster": 5, "bond": 2, "morale": 3,
               "horn": 6, "berserker": 3, "avenger": 7, "stormborn": 4}
    return card.strength + (4 if card.hero else 0) + sum(bonuses.get(a, 2) for a in card.abilities)


def _knowledge_game(game: Game, rng: random.Random) -> Game:
    """Never use the opponent's hidden identities or either deck's real order.

    A hypothetical opposing hand is sampled from their faction's collection,
    excluding publicly visible copies. Only explicitly revealed cards are kept.
    This is a possible reply, not knowledge of the player's actual deck.
    """
    model = deepcopy(game)
    own, opponent = model.players[BOT], model.players[0]
    visible = {card.id: card for card in game.players[BOT].revealed}
    known = [deepcopy(visible[card.id]) for card in game.players[0].hand if card.id in visible]
    faction = LEADERS[opponent.leader]["faction"]
    used = Counter(card.key for card in known + opponent.discard)
    used.update(item.card.key for player in model.players for item in player.board + player.specials)
    pool = [key for key, card in CATALOG.items()
            if card.collectible and card.faction in ("neutral", faction)
            for _ in range(max(0, card.copies - used[key]))]
    rng.shuffle(pool)
    # Very large custom decks may exhaust the remaining collection in a model.
    fallback = [key for key, card in CATALOG.items()
                if card.collectible and card.kind == "unit" and card.faction == faction]
    def sample(count, zone):
        return [CardInstance(f"model-{zone}-{i}", pool.pop() if pool else rng.choice(fallback))
                for i in range(count)]
    opponent.hand = known + sample(len(opponent.hand) - len(known), "hand")
    opponent.deck = sample(len(opponent.deck), "deck")
    opponent.revealed = []
    own.deck.sort(key=lambda card: (card.key, card.id))
    rng.shuffle(own.deck)
    model.rng = random.Random(rng.getrandbits(64))
    return model


def _mulligan(game: Game, difficulty: str) -> dict:
    player = game.players[BOT]
    move = {"type": "mulligan", "card_ids": []}
    if game.starter_chooser == BOT:
        move["starter"] = 0  # The last move is usually worth more than initiative.
    if difficulty == "easy":
        return move
    groups = Counter(CATALOG[card.key].group for card in player.hand
                     if "muster" in CATALOG[card.key].abilities)
    specials = sum(CATALOG[card.key].kind != "unit" for card in player.hand)
    candidates = []
    for card in player.hand:
        definition = CATALOG[card.key]
        if "muster" in definition.abilities and groups[definition.group] > 1:
            groups[definition.group] -= 1
            candidates.append((0, card.id))
        elif definition.kind != "unit" and specials > 2:
            specials -= 1
            candidates.append((2 + card_value(card.key) / 10, card.id))
        elif definition.kind == "unit" and card_value(card.key) < 5:
            candidates.append((4 + card_value(card.key), card.id))
    limit = 4 if LEADERS[player.leader]["faction"] == "ellifarn" else 2
    move["card_ids"] = [card_id for _, card_id in sorted(candidates)[:limit]]
    return move


def _round_winner(game: Game) -> int | None:
    difference = game.total(BOT) - game.total(0)
    if difference:
        return BOT if difference > 0 else 0
    empires = [side for side, player in enumerate(game.players)
               if LEADERS[player.leader]["faction"] == "shiron"]
    return empires[0] if len(empires) == 1 else None


def _evaluate(game: Game) -> float:
    own, opponent = game.players[BOT], game.players[0]
    reserve = lambda p: sum(card_value(card.key) for card in p.hand)
    resources = 7 * (len(own.hand) - len(opponent.hand)) + .28 * (reserve(own) - reserve(opponent))
    if game.phase == "finished":
        return (100000 if game.winner == BOT else -100000 if game.winner == 0 else 0) + resources * .01
    difference = game.total(BOT) - game.total(0)
    score = 85 * (own.lives - opponent.lives) + resources + 28 * math.tanh(difference / 18)
    score += 4 * (int(not own.leader_used and not own.leader_blocked)
                  - int(not opponent.leader_used and not opponent.leader_blocked))
    if game.pending or game.pending_levy:
        owner = 1 - game.turn if game.pending_levy else game.turn
        targets = [c for c in game.players[owner].discard
                   if CATALOG[c.key].kind == "unit" and not CATALOG[c.key].hero]
        if targets:
            score += (1 if game.turn == BOT else -1) * max(card_value(c.key) for c in targets) * .8
    # Keep medics, reusable spies and resurrection options useful in hand.
    for side, player in enumerate(game.players):
        sign = 1 if side == BOT else -1
        targets = [c for c in player.discard if CATALOG[c.key].kind == "unit" and not CATALOG[c.key].hero]
        if targets and any("medic" in CATALOG[c.key].abilities for c in player.hand):
            score += sign * min(8, max(card_value(c.key) for c in targets) * .4)
        if any(c.key == "decoy" for c in player.hand):
            reusable = [item for item in player.board if not CATALOG[item.card.key].hero
                        and set(CATALOG[item.card.key].abilities) & {"spy", "medic"}]
            score += sign * min(12, 8 * len(reusable))
        if player.passed and not game.players[1 - side].passed:
            winner = _round_winner(game)
            if winner != side:
                score -= sign * (220 if player.lives == 1 else 32)
            elif game.players[1 - side].hand:
                # A small lead is not secured while the opponent can still play.
                score -= sign * (8 + (90 if player.lives == 1 else 30) * math.exp(-abs(difference) / 12))
    return score


def _moves(game: Game, side: int) -> list[dict]:
    """Equivalent copies do not need separate search branches."""
    cards = {card.id: card.key for player in game.players
             for card in player.hand + player.discard + [item.card for item in player.board]}
    targets = {item.card.id: (item.card.key, item.row.value) for player in game.players for item in player.board}
    seen, result = set(), []
    for move in game.legal_moves(side):
        if move["type"] == "concede":
            continue
        identity = tuple(sorted((key, targets.get(value, value) if key == "target_id" else
                                 cards.get(value, value) if key == "card_id" else value)
                                for key, value in move.items()))
        if identity not in seen:
            seen.add(identity)
            result.append(move)
    return result


class _Search:
    def __init__(self, difficulty: str):
        self.remaining = 160 if difficulty == "hard" else 70
        self.deadline = time.monotonic() + (0.85 if difficulty == "hard" else 0.4)

    @property
    def available(self):
        return self.remaining > 0 and time.monotonic() < self.deadline

    def rank(self, game: Game, side: int) -> list[tuple[float, dict, Game]]:
        ranked = []
        for move in _moves(game, side):
            # Always produce one usable move, even on a very slow device.
            if ranked and not self.available:
                break
            self.remaining -= 1
            after = game.act(side, move, game.version)
            ranked.append((_evaluate(after), move, after))
        ranked.sort(key=lambda item: item[0], reverse=side == BOT)
        return ranked

    def resolve(self, game: Game) -> Game:
        # A medic's choice is part of the same turn, not the opponent's reply.
        for _ in range(4):
            if not (game.pending or game.pending_levy) or not self.available:
                break
            ranked = self.rank(game, game.turn)
            if not ranked:
                break
            game = ranked[0][2]
        return game


def choose_bot_move(game: Game, difficulty: str = "normal") -> dict | None:
    if difficulty not in DIFFICULTIES:
        raise ValueError("Неизвестная сложность бота.")
    legal = [move for move in game.legal_moves(BOT) if move["type"] != "concede"]
    if not legal:
        return None
    if game.phase == "mulligan":
        return _mulligan(game, difficulty)
    choosing = bool(game.pending or game.pending_levy)
    if not choosing and game.players[0].passed and _round_winner(game) == BOT:
        return {"type": "pass"}

    rng = random.Random(7919 * game.version + 31 * game.round_number)
    model = _knowledge_game(game, rng)
    search = _Search(difficulty)
    ranked = search.rank(model, BOT)
    if not ranked:
        return legal[0]
    if difficulty == "easy":
        # A weaker but legal opponent, without looking ahead.
        options = [item for item in ranked if item[1]["type"] != "pass"] or ranked
        return rng.choice(options[:3])[1]

    # Sacrifice an expensive opening round instead of emptying the hand chasing it.
    own, opponent = model.players[BOT], model.players[0]
    if not choosing and not opponent.passed and own.lives > 1:
        deficit = model.total(0) - model.total(BOT)
        best_swing = max(item[2].total(BOT) - item[2].total(0) + deficit for item in ranked)
        if deficit >= 18 and best_swing < deficit and len(own.hand) >= len(opponent.hand):
            return {"type": "pass"}

    best_score, best_move = -math.inf, ranked[0][1]
    # Resolve choices for the strongest immediate moves. Hard also checks a
    # plausible opponent reply and one counterplay, bounded by time and states.
    for immediate, move, after in ranked[:6]:
        if not search.available:
            break
        after = search.resolve(after)
        value = _evaluate(after)
        if difficulty == "hard" and after.phase == "playing" and search.available:
            replies = search.rank(after, after.turn)
            if replies:
                reply = search.resolve(replies[0][2])
                future = _evaluate(reply)
                if reply.phase == "playing" and reply.turn == BOT and search.available:
                    counters = search.rank(reply, BOT)
                    if counters:
                        future = _evaluate(search.resolve(counters[0][2]))
                value = .55 * value + .45 * future
        if value > best_score:
            best_score, best_move = value, move
    return best_move
