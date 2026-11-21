"""Single-player adapter for the game engine running in the browser worker."""

import json
import random

from frontiers.catalog import DECKS, LEADERS, validate_deck
from frontiers.bot import BOT, DIFFICULTIES, choose_bot_move
from frontiers.rooms import Room, RoomError, Seat
from frontiers.tutorial import LocalTutorial, lesson_list


class LocalMatch:
    def __init__(self):
        self.room: Room | None = None
        self.difficulty = "normal"
        self.tutorial: LocalTutorial | None = None

    def dispatch(self, raw: str) -> str:
        request = json.loads(raw)
        try:
            operation = request["type"]
            if operation == "tutorial-list":
                return json.dumps({"lessons": lesson_list(), "bot_turn": False}, ensure_ascii=False)
            if operation == "tutorial-start":
                self.tutorial = LocalTutorial(request.get("lesson", ""),
                                              (request.get("name", "Вы"), request.get("opponent", "Соперник")))
                self.room = None
                return json.dumps({"state": self.tutorial.view(), "bot_turn": False}, ensure_ascii=False)
            if self.tutorial and operation == "action":
                state = self.tutorial.act(request["action"], request["version"])
                return json.dumps({"state": state, "bot_turn": False}, ensure_ascii=False)
            if operation == "create":
                name = request["name"].strip()
                if not name or len(name) > 32 or any(ord(char) < 32 for char in name):
                    raise ValueError("Введите имя от 1 до 32 символов.")
                difficulty = request.get("difficulty", "normal")
                if difficulty not in DIFFICULTIES:
                    raise ValueError("Неизвестная сложность бота.")
                self.tutorial = None
                self.difficulty = difficulty
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
                move = choose_bot_move(self.room.game, self.difficulty)
                if move is not None:
                    self.room.apply(BOT, move, self.room.game.version)
            else:
                raise ValueError("Неизвестное действие.")
            state = self.room.view(0)
            state["bot_difficulty"] = self.difficulty
            state["seats"][BOT].update(online=True, ready=True)
            state["seats"][0]["online"] = True
            next_bot_move = self.room.game and any(move["type"] != "concede"
                                                    for move in self.room.game.legal_moves(BOT))
            return json.dumps({"state": state, "bot_turn": bool(next_bot_move)}, ensure_ascii=False)
        except ValueError as error:
            return json.dumps({"error": str(error)}, ensure_ascii=False)
