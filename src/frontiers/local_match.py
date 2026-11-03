"""Single-player adapter for the game engine running in the browser worker."""

import json
import random

from frontiers.catalog import DECKS, LEADERS, validate_deck
from frontiers.engine import Game
from frontiers.rooms import Room, RoomError, Seat


BOT = 1


def choose_bot_move(game: Game) -> dict | None:
    moves = [move for move in game.legal_moves(BOT) if move["type"] != "concede"]
    if not moves:
        return None
    if game.phase == "mulligan":
        return moves[0]

    own, opponent = game.players[BOT], game.players[0]
    can_pass = any(move["type"] == "pass" for move in moves)
    lead = game.total(BOT) - game.total(0)
    if can_pass and opponent.passed and lead > 0:
        return {"type": "pass"}
    if can_pass and not opponent.passed and game.round_number < 3 and lead >= 12 and len(own.hand) <= 6:
        return {"type": "pass"}

    def value(move):
        after = game.act(BOT, move, game.version)
        if after.phase == "finished":
            return 1000 if after.winner == BOT else -1000 if after.winner == 0 else 0
        if after.round_number != game.round_number:
            return 40 * (after.players[BOT].lives - after.players[0].lives - own.lives + opponent.lives)
        points = after.total(BOT) - after.total(0) - lead
        cards = len(after.players[BOT].hand) - len(own.hand)
        pending_choice = 4 if after.turn == BOT and (after.pending or after.pending_levy) else 0
        return points + 4 * cards + pending_choice - (2 if move["type"] == "leader" else 0)

    candidates = [move for move in moves if move["type"] != "pass"]
    if not candidates:
        return {"type": "pass"}
    return max(candidates, key=value)


class LocalMatch:
    def __init__(self):
        self.room: Room | None = None

    def dispatch(self, raw: str) -> str:
        request = json.loads(raw)
        try:
            operation = request["type"]
            if operation == "create":
                name = request["name"].strip()
                if not name or len(name) > 32 or any(ord(char) < 32 for char in name):
                    raise ValueError("Введите имя от 1 до 32 символов.")
                self.room = Room("С ботом", [Seat("local", name), Seat("bot", "Bot", ready=True)])
            elif self.room is None:
                raise RoomError("Сначала откройте игру с ботом.")
            elif operation == "ready":
                validate_deck(request["deck"], request["leader"])
                preset = random.choice(list(DECKS.values()))
                bot_leader = random.choice([key for key, leader in LEADERS.items()
                                            if leader["faction"] == preset["faction"]])
                self.room.set_ready(BOT, bot_leader, preset["cards"], True)
                self.room.set_ready(0, request["leader"], request["deck"], True)
            elif operation == "action":
                self.room.apply(0, request["action"], request["version"])
            elif operation == "bot" and self.room.game:
                move = choose_bot_move(self.room.game)
                if move is not None:
                    self.room.apply(BOT, move, self.room.game.version)
            else:
                raise ValueError("Неизвестное действие.")
            state = self.room.view(0)
            state["seats"][BOT].update(online=True, ready=True)
            state["seats"][0]["online"] = True
            next_bot_move = self.room.game and any(move["type"] != "concede"
                                                    for move in self.room.game.legal_moves(BOT))
            return json.dumps({"state": state, "bot_turn": bool(next_bot_move)}, ensure_ascii=False)
        except ValueError as error:
            return json.dumps({"error": str(error)}, ensure_ascii=False)
