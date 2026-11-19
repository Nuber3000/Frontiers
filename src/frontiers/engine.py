"""Проверяемый движок матча: действия возвращают новое состояние целиком."""

from copy import deepcopy
from dataclasses import dataclass, field
import random
import secrets
import uuid

from frontiers.cards import CombatRow as Row
from frontiers.catalog import CATALOG, LEADERS, ROWS, card_definition_view, faction_allows_card, validate_deck
from frontiers.udul import SOUL_LIMIT
from frontiers.models import CardInstance, MatchPlayer, PlacedCard


WEATHER_ROWS = {
    "frost": (Row.MELEE,), "fog": (Row.RANGED,), "rain": (Row.SIEGE,),
    "storm": (Row.RANGED, Row.SIEGE),
}


class RuleError(ValueError):
    """Ошибка игрового действия, которую можно показать игроку."""


class StaleState(RuleError):
    """Клиент пытался сделать ход на основе устаревшего состояния."""


@dataclass
class WeatherEffect:
    owner: int
    key: str
    card: CardInstance | None = None


@dataclass
class Game:
    players: list[MatchPlayer]
    rng: random.Random
    phase: str = "mulligan"
    turn: int = 0
    round_starter: int = 0
    starter_chooser: int | None = None
    round_number: int = 1
    version: int = 0
    weather: list[WeatherEffect] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    pending_actors: list[int] = field(default_factory=list)
    pending_levy: bool = False
    selection: dict | None = None
    round_resume_turn: int | None = None
    history: list[dict] = field(default_factory=list)
    event_messages: list[dict] = field(default_factory=list)
    scorched: list[str] = field(default_factory=list)
    executed_on_arrival: list[dict] = field(default_factory=list)
    played: dict | None = None
    leader_played: int | None = None
    winner: int | None = None
    match_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def create(cls, names: list[str], decks: list[list[str]], leaders: list[str],
               seed: int | None = None) -> "Game":
        if len(names) != 2 or len(decks) != 2 or len(leaders) != 2:
            raise RuleError("Для матча нужны ровно два игрока.")
        for deck, leader in zip(decks, leaders):
            validate_deck(deck, leader)
        rng = random.Random(seed if seed is not None else secrets.randbits(256))
        game = cls([MatchPlayer(names[i], leaders[i]) for i in range(2)], rng)
        for side, player in enumerate(game.players):
            if LEADERS[player.leader].get("passive"):
                player.leader_used = True
            if player.leader == "shiron_nullify":
                game.players[1 - side].leader_blocked = True
        for player, keys in zip(game.players, decks):
            player.deck = [game._new_card(key) for key in keys]
            rng.shuffle(player.deck)
            game._draw(player, 11 if game._is_ellifarn(player) else 10)
        game.turn = game.round_starter = rng.randrange(2)
        # The first draw of initiative is also the tiebreaker for two councils.
        for side in (game.turn, 1 - game.turn):
            if game._is_ellifarn(game.players[side]):
                game.starter_chooser = side
                break
        game._log("Матч начался. Подтвердите начальную руку.")
        return game

    @staticmethod
    def _is_ellifarn(player: MatchPlayer) -> bool:
        return LEADERS[player.leader]["faction"] == "ellifarn"

    @staticmethod
    def _new_card(key: str) -> CardInstance:
        return CardInstance(uuid.uuid4().hex, key)

    def _log(self, template: str, *args: str | int, translate: tuple[int, ...] = ()) -> None:
        """Keep player names verbatim and mark catalogue labels for translation."""
        self.event_messages.append({"template": template, "args": args, "translate": translate})
        self.event_messages = self.event_messages[-80:]

    @property
    def events(self) -> list[str]:
        return [event["template"].format(*event["args"]) for event in self.event_messages]

    @staticmethod
    def _can_use_card(player: MatchPlayer, card: CardInstance) -> bool:
        return faction_allows_card(LEADERS[player.leader]["faction"], CATALOG[card.key])

    def _draw(self, player: MatchPlayer, amount: int) -> int:
        drawn = [card for card in player.deck if self._can_use_card(player, card)][:amount]
        drawn_ids = {card.id for card in drawn}
        player.deck[:] = [card for card in player.deck if card.id not in drawn_ids]
        player.hand.extend(drawn)
        return len(drawn)

    def act(self, actor: int, action: dict, version: int) -> "Game":
        """Проверки выполняются на копии: отклонённая команда ничего не меняет."""
        if actor not in (0, 1):
            raise RuleError("Неизвестный игрок.")
        if version != self.version:
            raise StaleState("Состояние обновилось. Повторите ход после обновления поля.")
        if self.phase == "finished":
            raise RuleError("Матч уже завершён.")
        candidate = deepcopy(self)
        candidate.scorched = []
        candidate.executed_on_arrival = []
        candidate.played = None
        candidate.leader_played = None
        candidate._act(actor, action)
        candidate.version += 1
        return candidate

    def _act(self, actor: int, action: dict) -> None:
        kind = action.get("type")
        if kind == "concede":
            self.phase, self.winner = "finished", 1 - actor
            self.pending.clear()
            self.pending_actors.clear()
            self.pending_levy = False
            self.selection = None
            self.round_resume_turn = None
            self._log("{0} сдаётся.", self.players[actor].name)
            return
        if self.phase == "mulligan":
            if kind != "mulligan":
                raise RuleError("Сначала подтвердите начальную руку.")
            self._mulligan(actor, action.get("card_ids", []), action.get("starter"))
            return
        if action.get("starter") is not None:
            raise RuleError("Первый ход выбирают перед первым раундом.")
        if actor != self.turn or self.players[actor].passed:
            raise RuleError("Сейчас ход другого игрока.")
        if self.selection:
            if kind != "choose":
                raise RuleError("Сначала завершите выбор карты для способности.")
            self._choose_selection(actor, action)
        elif self.pending_levy:
            if kind != "choose":
                raise RuleError("Выберите отряд из отбоя соперника.")
            card = self._find(self._discard_units(1 - actor), action.get("card_id"))
            self.players[1 - actor].discard.remove(card)
            self.players[actor].hand.append(card)
            self.pending_levy = False
            self._log("Посмертная повинность: {0} забирает «{1}» в руку.", self.players[actor].name, CATALOG[card.key].name, translate=(1,))
        elif self.pending:
            if kind != "choose":
                if LEADERS[self.players[actor].leader]["faction"] == "udul":
                    raise RuleError("Выберите отряд для «Возрождения».")
                raise RuleError("Выберите отряд для способности Лекаря.")
            self._choose(actor, action)
        elif kind == "play":
            self._play(actor, action)
        elif kind == "leader":
            self._leader(actor, action)
        elif kind == "pass":
            self.players[actor].passed = True
            self._log("{0} пасует.", self.players[actor].name)
        else:
            raise RuleError("Неизвестное действие.")
        self._finish_action(actor)

    def _mulligan(self, actor: int, card_ids: list[str], starter: int | None) -> None:
        player = self.players[actor]
        if player.mulligan_done:
            raise RuleError("Начальная рука уже подтверждена.")
        limit = 4 if self._is_ellifarn(player) else 2
        if not isinstance(card_ids, list) or len(card_ids) > limit or len(set(card_ids)) != len(card_ids):
            raise RuleError("Можно заменить не более четырёх разных карт." if limit == 4
                            else "Можно заменить не более двух разных карт.")
        if starter is not None and (self.starter_chooser != actor or type(starter) is not int or starter not in (0, 1)):
            raise RuleError("Вы не можете сделать такой выбор первого хода.")
        selected = [self._find(player.hand, card_id) for card_id in card_ids]
        player.hand = [card for card in player.hand if card.id not in card_ids]
        self._draw(player, len(selected))
        player.deck.extend(selected)
        self.rng.shuffle(player.deck)
        player.mulligan_done = True
        if actor == self.starter_chooser:
            self.turn = self.round_starter = actor if starter is None else starter
        self._log("{0} подтверждает начальную руку.", player.name)
        if all(player.mulligan_done for player in self.players):
            self.phase = "playing"
            self._log("Раунд 1. Первый ход: {0}.", self.players[self.turn].name)

    @staticmethod
    def _find(cards: list[CardInstance], card_id: str | None) -> CardInstance:
        for card in cards:
            if card.id == card_id:
                return card
        raise RuleError("Карта отсутствует в доступной зоне.")

    @staticmethod
    def _row(value: str | None, allowed: tuple[Row, ...] = ROWS) -> Row:
        if value is None and len(allowed) == 1:
            return allowed[0]
        try:
            row = Row(value)
        except (ValueError, TypeError):
            raise RuleError("Выберите боевую линию.") from None
        if row not in allowed:
            raise RuleError("Карту нельзя разыграть на выбранной линии.")
        return row

    def _slot_free(self, side: int, row: Row) -> bool:
        return not any(item.row == row for item in self.players[side].specials)

    def _play(self, actor: int, action: dict) -> None:
        player = self.players[actor]
        card = self._find(player.hand, action.get("card_id"))
        definition = CATALOG[card.key]
        row = None
        target = None
        if definition.kind == "unit":
            row = self._row(action.get("row"), definition.rows)
        elif card.key == "horn":
            row = self._row(action.get("row"))
            if not self._slot_free(actor, row):
                raise RuleError("Место особой карты этого ряда уже занято.")
            if row in player.leader_horn:
                raise RuleError("Этот ряд уже усилен способностью лидера.")
        elif card.key == "mushroom":
            row = self._row(action.get("row"))
        elif card.key == "decoy":
            target = next((item for item in player.board
                           if item.card.id == action.get("target_id")
                           and CATALOG[item.card.key].kind == "unit"
                           and not CATALOG[item.card.key].hero), None)
            if target is None:
                raise RuleError("Чучело заменяет только ваш отряд, кроме героя.")

        destination_row = row or (target.row if target is not None else None)
        self.played = {"actor": actor, "card": self._card_view(card),
                       "side": 1 - actor if "spy" in definition.abilities else actor,
                       "row": destination_row.value if destination_row is not None else None}
        player.hand.remove(card)
        self._log("{0} разыгрывает «{1}».", player.name, definition.name, translate=(1,))
        if definition.kind == "unit":
            self._place_unit(actor, card, row)
        elif card.key in WEATHER_ROWS:
            self.weather.append(WeatherEffect(actor, card.key, card))
        elif card.key == "clear":
            player.discard.append(card)
            self._clear_weather()
        elif card.key == "scorch":
            player.discard.append(card)
            self._scorch()
        elif card.key == "horn":
            player.specials.append(PlacedCard(card, row))
        elif card.key == "mushroom":
            player.discard.append(card)
            self._transform(instant_side=actor, instant_row=row)
        elif card.key == "ting":
            player.discard.append(card)
            count = self._draw(player, 2)
            self._log("Тинг: {0} добирает карт: {1}.", player.name, count)
        elif card.key == "decoy":
            index = player.board.index(target)
            player.board[index] = PlacedCard(card, target.row)
            player.hand.append(target.card)
        elif card.key == "udul_portal":
            player.discard.append(card)
            targets = [item for item in player.deck if CATALOG[item.key].kind == "unit"
                       and self._can_use_card(player, item)]
            summoned = self.rng.sample(targets, min(2, len(targets)))
            for item in summoned:
                player.deck.remove(item)
            for item in summoned:
                self._place_unit(actor, item, self._best_row(actor, item))
            self._log("Портал: {0} призывает отрядов: {1}.", player.name, len(summoned))
        else:
            raise RuleError("Эффект карты не поддерживается.")

    def _place_unit(self, actor: int, card: CardInstance, row: Row) -> None:
        definition = CATALOG[card.key]
        if not self._can_use_card(self.players[actor], card):
            raise RuleError("Эта карта недоступна выбранной фракции.")
        spy = "spy" in definition.abilities
        side = 1 - actor if spy else actor
        recipient = self.players[side]
        recipient.board.append(PlacedCard(card, row))
        if spy and LEADERS[recipient.leader]["faction"] == "udul":
            self.executed_on_arrival.append({
                "card": {**self._card_view(card), "strength": definition.strength},
                "side": side, "row": row.value,
            })
            self._execute_units({card.id})
        self._transform()
        if spy:
            count = self._draw(self.players[actor], 2)
            self._log("Шпион: {0} добирает карт: {1}.", self.players[actor].name, count)
        if "muster" in definition.abilities:
            self._muster(actor, definition.group, row)
        for row_name in ("melee", "ranged", "siege"):
            if f"scorch_{row_name}" in definition.abilities:
                target_row = Row(row_name)
                if self.row_total(1 - actor, target_row) >= 10:
                    self._scorch(1 - actor, target_row)
        if "medic" in definition.abilities and self._medic_targets(actor):
            self.pending.append(definition.name)
            self.pending_actors.append(actor)

    def _muster(self, actor: int, group: str, row: Row) -> None:
        player = self.players[actor]
        summoned = []
        for zone in (player.hand, player.deck):
            matches = [card for card in zone if CATALOG[card.key].group == group
                       and CATALOG[card.key].kind == "unit" and not CATALOG[card.key].hero
                       and self._can_use_card(player, card)]
            selected = {card.id for card in matches}
            zone[:] = [card for card in zone if card.id not in selected]
            summoned.extend(matches)
        for card in summoned:
            self._log("Призыв: «{0}» выходит на поле.", CATALOG[card.key].name, translate=(0,))
            allowed_rows = CATALOG[card.key].rows
            self._place_unit(actor, card, row if row in allowed_rows else allowed_rows[0])

    def _best_row(self, actor: int, card: CardInstance) -> Row:
        definition = CATALOG[card.key]
        side = 1 - actor if "spy" in definition.abilities else actor
        item = PlacedCard(card, definition.rows[0])
        self.players[side].board.append(item)
        try:
            scores = []
            for row in definition.rows:
                item.row = row
                scores.append((self.strengths(side)[card.id], row))
            return max(scores, key=lambda pair: pair[0])[1]
        finally:
            self.players[side].board.remove(item)

    def _transform(self, instant_side: int | None = None, instant_row: Row | None = None) -> None:
        for side, player in enumerate(self.players):
            if instant_side is not None and side != instant_side:
                continue
            for item in player.board:
                definition = CATALOG[item.card.key]
                if not definition.transform_to or definition.hero:
                    continue
                instant_effect = side == instant_side and (instant_row is None or item.row == instant_row)
                druids = any(other.row == item.row and
                             "mushroom" in CATALOG[other.card.key].abilities
                             for other in player.board)
                if instant_effect or druids:
                    item.card.key = definition.transform_to
                    self._log("Превращение: «{0}».", CATALOG[item.card.key].name, translate=(0,))

    def _clear_weather(self) -> None:
        for effect in self.weather:
            if effect.card is not None:
                self.players[effect.owner].discard.append(effect.card)
        self.weather.clear()

    def strengths(self, side: int) -> dict[str, int]:
        player = self.players[side]
        values = {}
        for item in player.board:
            definition = CATALOG[item.card.key]
            if definition.kind != "unit":
                values[item.card.id] = 0
                continue
            if definition.hero:
                values[item.card.id] = definition.strength
                continue
            value = definition.strength
            stormborn = "stormborn" in definition.abilities
            if not stormborn and any(item.row in WEATHER_ROWS[effect.key] for effect in self.weather):
                resilient = player.leader == "skone_resilience" and not player.leader_blocked
                value = (value + 1) // 2 if resilient else 1
            allies = [other for other in player.board if other.row == item.row]
            if "bond" in definition.abilities:
                value *= sum(CATALOG[other.card.key].group == definition.group and
                             "bond" in CATALOG[other.card.key].abilities
                             for other in allies)
            value += sum(other.card.id != item.card.id and
                         "morale" in CATALOG[other.card.key].abilities for other in allies)
            if stormborn and any(effect.key == "storm" for effect in self.weather):
                value *= 2
            horn = item.row in player.leader_horn or any(
                special.row == item.row and special.card.key == "horn"
                for special in player.specials)
            horn = horn or any(other.card.id != item.card.id and
                               "horn" in CATALOG[other.card.key].abilities for other in allies)
            values[item.card.id] = value * 2 if horn else value
        return values

    def row_total(self, side: int, row: Row) -> int:
        values = self.strengths(side)
        return sum(values[item.card.id] for item in self.players[side].board if item.row == row)

    def total(self, side: int) -> int:
        return sum(self.strengths(side).values())

    def _scorch(self, side: int | None = None, row: Row | None = None) -> None:
        candidates = []
        for index, player in enumerate(self.players):
            if side is not None and index != side:
                continue
            values = self.strengths(index)
            for item in player.board:
                definition = CATALOG[item.card.key]
                if definition.kind == "unit" and not definition.hero and (row is None or item.row == row):
                    candidates.append((values[item.card.id], item.card.id))
        if not candidates:
            return
        highest = max(value for value, _ in candidates)
        self._execute_units({card_id for value, card_id in candidates if value == highest})

    def _execute_units(self, victims: set[str]) -> None:
        for player in self.players:
            if player.leader == "udul_souls":
                player.souls = min(SOUL_LIMIT, player.souls + len(victims))
        summons = []
        for index, player in enumerate(self.players):
            survivors = []
            for item in player.board:
                if item.card.id not in victims:
                    survivors.append(item)
                    continue
                player.discard.append(item.card)
                self.scorched.append(item.card.id)
                definition = CATALOG[item.card.key]
                self._log("Казнь: «{0}» отправляется в сброс.", definition.name, translate=(0,))
                if definition.summon_to:
                    summons.append((index, definition.summon_to))
            player.board = survivors
        for index, key in summons:
            self._place_unit(index, self._new_card(key), CATALOG[key].rows[0])

    def _discard_units(self, actor: int) -> list[CardInstance]:
        return [card for card in self.players[actor].discard
                if CATALOG[card.key].kind == "unit" and not CATALOG[card.key].hero]

    def _medic_targets(self, actor: int) -> list[CardInstance]:
        return [card for card in self._discard_units(actor)
                if self._can_use_card(self.players[actor], card)]

    def _choose(self, actor: int, action: dict) -> None:
        card = self._find(self._medic_targets(actor), action.get("card_id"))
        row = self._row(action.get("row"), CATALOG[card.key].rows)
        self.pending.pop(0)
        if self.pending_actors:
            self.pending_actors.pop(0)
        self.players[actor].discard.remove(card)
        message = ("Возрождение возвращает «{0}»." if LEADERS[self.players[actor].leader]["faction"] == "udul"
                   else "Лекарь возвращает «{0}».")
        self._log(message, CATALOG[card.key].name, translate=(0,))
        self._place_unit(actor, card, row)

    def _leader(self, actor: int, action: dict) -> None:
        player = self.players[actor]
        if player.leader_used or player.leader_blocked:
            raise RuleError("Способность лидера использована или заблокирована.")
        if player.leader.startswith("udul_"):
            kind = {"udul_rite": "weather", "udul_sacrifice": "sacrifice",
                    "udul_necromancy": "necromancy", "udul_spirit": "horn", "udul_souls": "draw"}[player.leader]
            if player.leader == "udul_souls":
                if player.souls < SOUL_LIMIT:
                    raise RuleError("Для способности нужно собрать не менее трёх душ.")
                player.souls = 0
            if kind != "sacrifice" or sum(self._can_use_card(player, card) for card in player.hand) >= 2:
                self.selection = {"kind": kind, "remaining": 2 if kind == "sacrifice" else 1,
                                  "source": LEADERS[player.leader]["name"]}
        elif player.leader == "academy":
            self._leader_boost(actor, Row.SIEGE)
        elif player.leader == "sun":
            self._clear_weather()
        elif player.leader in {"mortar", "war"}:
            row = Row.RANGED if player.leader == "mortar" else Row.SIEGE
            if self.row_total(1 - actor, row) >= 10:
                self._scorch(1 - actor, row)
        elif player.leader == "fog":
            self.weather.append(WeatherEffect(actor, "fog"))
        elif player.leader == "shiron_rain":
            self.weather.append(WeatherEffect(actor, "rain"))
        elif player.leader == "shiron_hand":
            targets = self._medic_targets(actor)
            if targets:
                card = self.rng.choice(targets)
                player.discard.remove(card)
                self._place_unit(actor, card, CATALOG[card.key].rows[0])
        elif player.leader == "shiron_spy":
            hand = self.players[1 - actor].hand
            player.revealed = self.rng.sample(hand, min(3, len(hand)))
        elif player.leader == "shiron_levy":
            self.pending_levy = bool(self._discard_units(1 - actor))
        elif player.leader == "skone_storm":
            self.weather.append(WeatherEffect(actor, "storm"))
        elif player.leader == "skone_horn":
            row = self._row(action.get("row"))
            self._leader_boost(actor, row)
        elif player.leader == "skone_rage":
            self._transform(instant_side=actor)
        elif player.leader == "skone_chaos":
            for owner in self.players:
                owner.deck.extend(owner.discard)
                owner.discard.clear()
                self.rng.shuffle(owner.deck)
        elif player.leader == "ellifarn_trade":
            self._draw(player, 1)
        elif player.leader == "ellifarn_aim":
            self._leader_boost(actor, Row.RANGED)
        elif player.leader == "ellifarn_fury":
            self._scorch(1 - actor, Row.MELEE)
        elif player.leader == "ellifarn_logistics":
            for item in self._agile_units(player):
                original = item.row
                strength = self.strengths(actor)[item.card.id]
                item.row = next(row for row in CATALOG[item.card.key].rows if row != original)
                if self.strengths(actor)[item.card.id] <= strength:
                    item.row = original
        elif LEADERS[player.leader].get("passive"):
            raise RuleError("Эта способность лидера действует пассивно с начала матча.")
        player.leader_used = True
        self.leader_played = actor
        self._log("{0}: {1}.", player.name, LEADERS[player.leader]['name'], translate=(1,))

    def _selection_targets(self, actor: int) -> list[CardInstance]:
        player = self.players[actor]
        kind = self.selection["kind"]
        if kind == "sacrifice":
            return [card for card in player.hand if self._can_use_card(player, card)]
        if kind == "necromancy":
            return [card for card in self._discard_units(actor) if self._can_use_card(player, card)]
        if kind == "weather":
            return [card for card in player.deck if CATALOG[card.key].kind == "weather"]
        if kind == "horn":
            return [card for card in player.deck if card.key == "horn"] if any(
                self._slot_free(actor, row) and row not in player.leader_horn for row in ROWS) else []
        return [card for card in player.deck if self._can_use_card(player, card)]

    def _choose_selection(self, actor: int, action: dict) -> None:
        card = self._find(self._selection_targets(actor), action.get("card_id"))
        player, kind = self.players[actor], self.selection["kind"]
        if kind == "sacrifice":
            player.hand.remove(card)
            player.discard.append(card)
        elif kind == "necromancy":
            row = self._row(action.get("row"), CATALOG[card.key].rows)
            player.discard.remove(card)
            self._place_unit(actor, card, row)
        elif kind == "draw":
            player.deck.remove(card)
            player.hand.append(card)
        elif kind == "weather":
            player.deck.remove(card)
            self.played = {"actor": actor, "card": self._card_view(card), "row": None, "side": actor}
            if card.key == "clear":
                player.discard.append(card)
                self._clear_weather()
            else:
                self.weather.append(WeatherEffect(actor, card.key, card))
        elif kind == "horn":
            row = self._row(action.get("row"))
            if not self._slot_free(actor, row) or row in player.leader_horn:
                raise RuleError("Место усиления этого ряда уже занято.")
            player.deck.remove(card)
            player.specials.append(PlacedCard(card, row))
            self.played = {"actor": actor, "card": self._card_view(card), "row": row.value, "side": actor}
        if kind == "draw":
            self._log("{0}: {1} берёт одну карту из колоды.", self.selection["source"], player.name, translate=(0,))
        else:
            self._log("{0}: выбрана карта «{1}».", self.selection["source"], CATALOG[card.key].name, translate=(0, 1))
        self.selection["remaining"] -= 1
        if self.selection["remaining"] == 0:
            if kind == "sacrifice":
                self.selection.update(kind="draw", remaining=1)
            else:
                self.selection = None

    def _leader_boost(self, actor: int, row: Row) -> None:
        # An occupied slot makes the effect a no-op, but the leader is still spent.
        if self._slot_free(actor, row):
            self.players[actor].leader_horn.add(row)

    @staticmethod
    def _agile_units(player: MatchPlayer) -> list[PlacedCard]:
        return [item for item in player.board
                if not CATALOG[item.card.key].hero and len(CATALOG[item.card.key].rows) == 2]

    def _finish_action(self, actor: int) -> None:
        if self._resolve_pending():
            return
        if self.round_resume_turn is not None:
            self.turn, self.round_resume_turn = self.round_resume_turn, None
            self._start_round_turn()
            return
        self._auto_pass_empty()
        if all(player.passed for player in self.players):
            self._end_round()
            return
        opponent = 1 - actor
        self.turn = opponent if not self.players[opponent].passed else actor

    def _resolve_pending(self) -> bool:
        if self.selection:
            if self._selection_targets(self.turn):
                return True
            self.selection = None
        # В третьем раунде лекари обеих сторон могут ждать выбора одновременно.
        while self.pending and not self._medic_targets(self.pending_actors[0] if self.pending_actors else self.turn):
            self.pending.pop(0)
            if self.pending_actors:
                self.pending_actors.pop(0)
        if self.pending:
            if self.pending_actors:
                self.turn = self.pending_actors[0]
            return True
        return self.pending_levy

    def _start_round_turn(self) -> None:
        self._auto_pass_empty()
        if all(player.passed for player in self.players):
            self._end_round()
        elif self.players[self.turn].passed:
            self.turn = 1 - self.turn

    def _auto_pass_empty(self) -> None:
        for index, player in enumerate(self.players):
            if not player.passed and (player.leader_used or player.leader_blocked or (
                    player.leader == "udul_souls" and player.souls < SOUL_LIMIT)) and not self._play_moves(index):
                player.passed = True
                self._log("{0}: доступные карты закончились, автоматический пас.", player.name)

    def _end_round(self) -> None:
        scores = [self.total(0), self.total(1)]
        winner = None if scores[0] == scores[1] else int(scores[1] > scores[0])
        if winner is None:
            empires = [side for side, player in enumerate(self.players)
                       if LEADERS[player.leader]["faction"] == "shiron"]
            if len(empires) == 1:
                winner = empires[0]
                self._log("Широн: {0} выигрывает при равной силе.", self.players[winner].name)
        self.history.append({"round": self.round_number, "scores": scores, "winner": winner})
        for index, player in enumerate(self.players):
            if winner is None or index != winner:
                player.lives -= 1
        self._log("Раунд {0}: {1} : {2}.", self.round_number, scores[0], scores[1])
        if winner is not None and LEADERS[self.players[winner].leader]["faction"] == "burgundy":
            drawn = self._draw(self.players[winner], 1)
            self._log("Бургундия: {0} добирает карт: {1}.", self.players[winner].name, drawn)
        # Завершённый матч сохраняет последний стол вместе с погодой и усилениями.
        if any(player.lives <= 0 for player in self.players):
            self.phase = "finished"
            self.winner = None if all(player.lives <= 0 for player in self.players) else (
                0 if self.players[0].lives > 0 else 1)
            if self.winner is None:
                self._log("Матч завершён ничьей.")
            else:
                self._log("Победа: {0}.", self.players[self.winner].name)
            return
        summons = []
        for index, player in enumerate(self.players):
            player.revealed.clear()
            candidates = [item for item in player.board if CATALOG[item.card.key].kind == "unit"]
            survivor = self.rng.choice(candidates) if candidates and LEADERS[player.leader]["faction"] == "udul" else None
            for item in player.board:
                if item is survivor:
                    self._log("Удул Сурэг: «{0}» остаётся на следующий раунд.", CATALOG[item.card.key].name, translate=(0,))
                    continue
                definition = CATALOG[item.card.key]
                if definition.summon_to:
                    summons.append((index, definition.summon_to))
                player.discard.append(item.card)
            player.discard.extend(item.card for item in player.specials)
            player.board.clear()
            if survivor is not None:
                player.board.append(survivor)
            player.specials.clear()
            player.leader_horn.clear()
        self._clear_weather()
        self.round_number += 1
        self.turn = self.round_starter = winner if winner is not None else 1 - self.round_starter
        for player in self.players:
            player.passed = False
            if LEADERS[player.leader]["faction"] == "udul":
                player.leader_used = False
        for index, key in summons:
            self._place_unit(index, self._new_card(key), CATALOG[key].rows[0])
        self._log("Раунд {0}. Первый ход: {1}.", self.round_number, self.players[self.turn].name)
        if self.round_number == 3:
            self._revive_skone()
        if self.pending:
            self.round_resume_turn = self.round_starter
            if self._resolve_pending():
                return
            self.round_resume_turn = None
        self._start_round_turn()

    def _revive_skone(self) -> None:
        selected = []
        # Сначала выбираем и извлекаем обе карты каждой стороны. Лекарь и Казнь
        # не должны менять выбор второго отряда в ходе разрешения способности.
        for side, player in enumerate(self.players):
            if LEADERS[player.leader]["faction"] != "skone":
                continue
            targets = self._medic_targets(side)
            cards = self.rng.sample(targets, min(2, len(targets)))
            for card in cards:
                player.discard.remove(card)
                selected.append((side, card))
            self._log("Сконе: {0} возвращает отрядов из отбоя: {1}.", player.name, len(cards))
        for side, card in selected:
            self._place_unit(side, card, CATALOG[card.key].rows[0])

    def _play_moves(self, actor: int) -> list[dict]:
        player = self.players[actor]
        moves = []
        for card in player.hand:
            if not self._can_use_card(player, card):
                continue
            definition = CATALOG[card.key]
            base = {"type": "play", "card_id": card.id}
            if definition.kind == "unit":
                moves.extend({**base, "row": row.value} for row in definition.rows)
            elif card.key == "horn":
                moves.extend({**base, "row": row.value} for row in ROWS
                             if self._slot_free(actor, row) and row not in player.leader_horn)
            elif card.key == "mushroom":
                moves.extend({**base, "row": row.value} for row in ROWS)
            elif card.key == "decoy":
                moves.extend({**base, "target_id": item.card.id} for item in player.board
                             if CATALOG[item.card.key].kind == "unit" and not CATALOG[item.card.key].hero)
            else:
                moves.append(base)
        return moves

    def legal_moves(self, actor: int) -> list[dict]:
        if self.phase == "finished":
            return []
        concede = [{"type": "concede"}]
        player = self.players[actor]
        if self.phase == "mulligan":
            if player.mulligan_done:
                return concede
            move = {"type": "mulligan", "card_ids": []}
            if actor == self.starter_chooser:
                return [{**move, "starter": side} for side in (actor, 1 - actor)] + concede
            return [move, *concede]
        if actor != self.turn or player.passed:
            return concede
        if self.selection:
            choices = []
            for card in self._selection_targets(actor):
                base = {"type": "choose", "card_id": card.id}
                if self.selection["kind"] == "horn":
                    choices.extend({**base, "row": row.value} for row in ROWS
                                   if self._slot_free(actor, row) and row not in player.leader_horn)
                elif self.selection["kind"] == "necromancy":
                    choices.extend({**base, "row": row.value} for row in CATALOG[card.key].rows)
                else:
                    choices.append(base)
            return choices + concede
        if self.pending_levy:
            return [{"type": "choose", "card_id": card.id}
                    for card in self._discard_units(1 - actor)] + concede
        if self.pending:
            return [{"type": "choose", "card_id": card.id, "row": row.value}
                    for card in self._medic_targets(actor) for row in CATALOG[card.key].rows] + concede
        moves = self._play_moves(actor)
        if not player.leader_used and not player.leader_blocked and not LEADERS[player.leader].get("passive") and (
                player.leader != "udul_souls" or player.souls >= SOUL_LIMIT):
            if player.leader == "skone_horn":
                moves.extend({"type": "leader", "row": row.value} for row in ROWS)
            else:
                moves.append({"type": "leader"})
        return moves + [{"type": "pass"}, *concede]

    @staticmethod
    def _card_view(card: CardInstance) -> dict:
        return {**card_definition_view(CATALOG[card.key]), "id": card.id}

    def view(self, viewer: int) -> dict:
        players = []
        for side, player in enumerate(self.players):
            powers = self.strengths(side)
            data = {
                "name": player.name, "leader": player.leader,
                "faction": LEADERS[player.leader]["faction"],
                "leader_used": player.leader_used, "lives": player.lives,
                "souls": min(SOUL_LIMIT, player.souls),
                "leader_blocked": player.leader_blocked,
                "passed": player.passed, "mulligan_done": player.mulligan_done,
                "deck_count": len(player.deck), "hand_count": len(player.hand),
                "discard": [self._card_view(card) for card in player.discard],
                "board": [{**self._card_view(item.card), "row": item.row.value,
                           "strength": powers[item.card.id]} for item in player.board],
                "specials": [{**self._card_view(item.card), "row": item.row.value}
                             for item in player.specials],
                "leader_horn": [row.value for row in ROWS if row in player.leader_horn],
                "rows": {row.value: self.row_total(side, row) for row in ROWS},
                "score": sum(powers.values()),
            }
            if side == viewer:
                data["mulligan_limit"] = 4 if self._is_ellifarn(player) else 2
                data["can_choose_starter"] = self.phase == "mulligan" and side == self.starter_chooser and not player.mulligan_done
                data["hand"] = [self._card_view(card) for card in player.hand]
                data["revealed"] = [self._card_view(card) for card in player.revealed
                                    if any(other.id == card.id for other in self.players[1 - side].hand)]
            players.append(data)
        return {
            "match_id": self.match_id,
            "phase": self.phase, "version": self.version, "turn": self.turn,
            "round": self.round_number, "winner": self.winner, "players": players,
            "weather": [{"key": effect.key, "name": CATALOG[effect.key].name}
                        for effect in self.weather],
            "pending": {"actor": self.turn, **deepcopy(self.selection),
                        "cards": [self._card_view(card) for card in self._selection_targets(viewer)] if viewer == self.turn else []}
                       if self.selection else {"actor": self.turn, "source": "Посмертная повинность", "kind": "levy"} if self.pending_levy else (
                {"actor": self.turn, "source": self.pending[0], "kind": "medic"} if self.pending else None),
            "history": deepcopy(self.history), "events": self.events,
            "event_messages": deepcopy(self.event_messages),
            "scorched": list(self.scorched),
            "executed_on_arrival": deepcopy(self.executed_on_arrival),
            "played": deepcopy(self.played),
            "leader_played": self.leader_played,
            "moves": self.legal_moves(viewer),
        }
