"""Small deterministic lessons replayed through the normal game engine."""

import random
import uuid

from frontiers.cards import CombatRow as Row
from frontiers.catalog import CATALOG, STARTER_DECK
from frontiers.engine import Game, RuleError
from frontiers.models import CardInstance, MatchPlayer, PlacedCard


LESSONS = {
    "rows": {
        "title": "Ряды и сила",
        "description": "Сила ваших отрядов складывается. Каждый отряд занимает разрешённую боевую линию.",
        "steps": [
            ("Сыграйте Рыцаря в ближний бой.", "play", "knight"),
            ("Теперь сыграйте Дозорного в дальний бой.", "play", "scout"),
        ],
        "summary": "Отряды в разных рядах дают общий счёт. Для победы в раунде нужно набрать больше силы, чем соперник.",
    },
    "weather": {
        "title": "Погода и лидер",
        "description": "Погода влияет на соответствующий ряд обоих игроков. Герои защищены от неё.",
        "steps": [
            ("Сыграйте Мороз и сравните силу обычных отрядов с силой героя.", "play", "frost"),
            ("Примените способность лидера «Солнцеликий», чтобы снять погоду.", "leader", None),
        ],
        "summary": "Мороз снизил силу обычных рукопашных отрядов до 1. Герой сохранил силу, а нулевой отряд остался нулевым. Этот лидер снимает погоду один раз за матч.",
    },
    "boosts": {
        "title": "Сплочённость и штандарт",
        "description": "Связанные отряды усиливают друг друга в одном ряду. Штандарт удваивает силу обычных отрядов ряда.",
        "steps": [
            ("Сыграйте первую Королевскую баллисту в осадный ряд.", "play", "catapult"),
            ("Добавьте вторую Королевскую баллисту и посмотрите на силу обеих карт.", "play", "catapult"),
            ("Поставьте Штандарт в осадный ряд.", "play", "horn"),
        ],
        "summary": "Две Королевские баллисты со Сплочённостью удвоили силу друг друга. Штандарт затем удвоил силу ряда ещё раз.",
    },
    "abilities": {
        "title": "Шпион и лекарь",
        "description": "Способности отрядов срабатывают при выходе на поле.",
        "steps": [
            ("Сыграйте Королевского писаря: шпион выйдет к сопернику и даст вам две карты.", "play", "spy_scribe"),
            ("Сыграйте Полкового хирурга в осадный ряд.", "play", "field_medic"),
            ("Выберите Лазурную стражу из отбоя для способности Лекаря.", "choose", "blue_guard"),
        ],
        "summary": "Шпион усилил соперника, но дал вам две карты. Лекарь вернул обычный отряд из отбоя на поле. Герой в отбор целей не попал.",
    },
    "rounds": {
        "title": "Пас и раунды",
        "description": "Соперник уже спасовал с сильным героем. Сила двух ваших отрядов меньше его счёта. Карты в руке сохраняются между раундами.",
        "steps": [
            ("Спасуйте, чтобы уступить этот раунд и сохранить карты для следующего.", "pass", None),
        ],
        "summary": "Вы потеряли одну жизнь, но сохранили руку. Матч продолжается: для победы нужно выиграть два раунда.",
    },
}


def _game(lesson: str, names=None) -> Game:
    names = names or ("Вы", "Соперник")
    game = Game([MatchPlayer(names[0], "sun"), MatchPlayer(names[1], "fog")],
                random.Random(7), phase="playing", match_id=f"tutorial-{lesson}")
    for player in game.players:
        player.mulligan_done = True
    game.players[1].passed = True

    def cards(side, zone, keys):
        return [CardInstance(f"{side}-{zone}-{index}", key) for index, key in enumerate(keys)]

    hands = {
        "rows": ["knight", "scout", "clear"],
        "weather": ["frost", "clear"],
        "boosts": ["catapult", "catapult", "horn", "clear"],
        "abilities": ["spy_scribe", "field_medic", "clear"],
        "rounds": ["knight", "scout", "clear"],
    }
    game.players[0].hand = cards(0, "hand", hands[lesson])
    boards = {
        "rows": ([], ["knight"]),
        "weather": (["knight"], ["knight", "regent", "watchman"]),
        "boosts": ([], ["knight"]),
        "abilities": ([], ["knight"]),
        "rounds": ([], ["regent"]),
    }
    for side, keys in enumerate(boards[lesson]):
        game.players[side].board = [PlacedCard(card, CATALOG[card.key].rows[0])
                                    for card in cards(side, "board", keys)]
    if lesson == "abilities":
        game.players[0].deck = cards(0, "deck", ["knight", "scout"])
        game.players[0].discard = cards(0, "discard", ["blue_guard", "regent"])
    return game


def lesson_list() -> list[dict]:
    return [{"id": key, "title": lesson["title"], "description": lesson["description"]} for key, lesson in LESSONS.items()]


def replay(lesson: str, actions: list[dict], names=None) -> dict:
    specification = LESSONS[lesson]
    steps = specification["steps"]
    if len(actions) > len(steps):
        raise RuleError("Сценарий уже завершён.")
    game = _game(lesson, names)
    for index, action in enumerate(actions):
        instruction, kind, key = steps[index]
        available = game.players[0].hand + game.players[0].discard
        chosen = next((card for card in available if card.id == action.get("card_id")), None)
        wrong_row = key == "horn" and action.get("row") != Row.SIEGE.value
        if wrong_row or action.get("type") != kind or (key is not None and (chosen is None or chosen.key != key)):
            raise RuleError(instruction)
        move = {field: value for field, value in action.items() if field != "version"}
        game = game.act(0, move, action["version"])
    complete = len(actions) == len(steps)
    return {
        "id": lesson, "title": specification["title"], "description": specification["description"],
        "instruction": specification["summary"] if complete else steps[len(actions)][0],
        "step": len(actions), "steps": len(steps), "complete": complete, "game": game.view(0),
    }


class LocalTutorial:
    """Guided local match shaped exactly like the normal room snapshots."""

    def __init__(self, lesson: str, names=None):
        self.names = names
        if lesson not in LESSONS:
            raise RuleError("Сценарий не найден.")
        self.lesson = lesson
        self.actions = []
        self.run_id = uuid.uuid4().hex

    def act(self, action: dict, version: int) -> dict:
        actions = [*self.actions, {**action, "version": version}]
        result = replay(self.lesson, actions, self.names)
        self.actions = actions
        return self.view(result)

    def view(self, result=None) -> dict:
        result = result or replay(self.lesson, self.actions, self.names)
        game = result["game"]
        game["match_id"] = self.run_id
        if result["complete"]:
            game["moves"] = []
        else:
            _, kind, key = LESSONS[self.lesson]["steps"][result["step"]]
            cards = game["players"][0]["hand"] + game["players"][0]["discard"]
            ids = {card["id"] for card in cards if card["key"] == key}
            game["moves"] = [move for move in game["moves"] if move["type"] == kind
                             and (key is None or move.get("card_id") in ids)
                             and (key != "horn" or move.get("row") == "siege")]
        return {
            "code": f"tutorial-{self.run_id}", "me": 0, "revision": len(self.actions),
            "my_deck": list(STARTER_DECK), "my_leader": "sun",
            "seats": [{"name": player["name"], "leader": player["leader"],
                       "faction": player["faction"], "ready": True, "online": True}
                      for player in game["players"]],
            "game": game, "tutorial": {key: value for key, value in result.items() if key != "game"},
        }
