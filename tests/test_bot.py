"""Local bot decisions, hidden-information boundaries and adapter validation."""

from copy import deepcopy
import json
import random
import unittest
from unittest.mock import patch

from frontiers.bot import BOT, DIFFICULTIES, _knowledge_game, choose_bot_move
from frontiers.catalog import CATALOG, DECKS
from frontiers.engine import Game, WeatherEffect
from frontiers.cards import CombatRow as Row
from frontiers.local_match import LocalMatch
from test_engine import fixture, put


class BotTests(unittest.TestCase):
    def game(self, hand, opponent=("knight",), leader="sun", enemy="sun"):
        game = fixture(opponent, hand, enemy, leader)
        game.turn = BOT
        return game

    def test_difficulty_is_validated_and_retained_for_rematch(self):
        match = LocalMatch()
        invalid = json.loads(match.dispatch(json.dumps({"type": "create", "name": "A", "difficulty": "expert"})))
        self.assertIn("error", invalid)
        self.assertIsNone(match.room)
        for difficulty in DIFFICULTIES:
            result = json.loads(match.dispatch(json.dumps({"type": "create", "name": "A", "difficulty": difficulty})))
            self.assertEqual(result["state"]["bot_difficulty"], difficulty)
            preset = next(deck for deck in DECKS.values() if deck["faction"] == "burgundy")
            result = json.loads(match.dispatch(json.dumps({"type": "ready", "leader": "sun", "deck": preset["cards"]})))
            self.assertEqual(result["state"]["bot_difficulty"], difficulty)
            self.assertEqual(match.difficulty, difficulty)

    def test_simulations_ignore_hidden_hand_and_deck_order_and_preserve_source(self):
        game = self.game(["spy_scribe", "knight", "scorch"])
        game.players[BOT].deck = [game._new_card(key) for key in ("champion", "crossbow", "knight")]
        game.players[0].deck = [game._new_card("blue_guard")]
        game.players[0].hand.append(game._new_card("crossbow"))
        game.players[BOT].revealed = [game.players[0].hand[0]]
        changed = deepcopy(game)
        changed.players[0].hand[1].key = "champion"
        changed.players[0].deck[0].key = "scorch"
        changed.players[BOT].deck.reverse()
        changed.rng.seed(98765)
        before = deepcopy(game)
        first = _knowledge_game(game, random.Random(7))
        second = _knowledge_game(changed, random.Random(7))
        for side in (0, BOT):
            self.assertEqual(first.players[side].hand, second.players[side].hand)
            self.assertEqual(first.players[side].deck, second.players[side].deck)
        self.assertEqual(first.players[0].hand[0], game.players[0].hand[0])
        with patch("frontiers.bot.time.monotonic", return_value=0):
            self.assertEqual(choose_bot_move(game, "hard"), choose_bot_move(changed, "hard"))
        self.assertEqual(game.players, before.players)
        self.assertEqual(game.rng.getstate(), before.rng.getstate())

    def test_winning_after_opponent_pass_saves_cards_including_shiron_tie(self):
        for leader, enemy, own_key, enemy_key in (("sun", "sun", "veteran", "knight"),
                                                   ("shiron_spy", "sun", "knight", "knight")):
            game = self.game(["champion"], leader=leader, enemy=enemy)
            game.players[0].passed = True
            put(game, BOT, own_key)
            put(game, 0, enemy_key)
            for difficulty in DIFFICULTIES:
                self.assertEqual(choose_bot_move(game, difficulty), {"type": "pass"})

    def test_bot_does_not_pass_a_shiron_opponent_at_equal_score(self):
        game = self.game(["veteran"], enemy="shiron_spy")
        game.players[BOT].lives = 1
        game.players[0].passed = True
        put(game, BOT, "knight")
        put(game, 0, "knight")
        for difficulty in ("normal", "hard"):
            move = choose_bot_move(game, difficulty)
            self.assertNotEqual(move["type"], "pass")
            if move["type"] == "leader":
                # A no-effect leader is now a legal tempo move; it must still
                # be followed by a scoring card rather than a losing pass.
                after = game.act(BOT, move, game.version)
                self.assertEqual(choose_bot_move(after, difficulty)["type"], "play")

    def test_medic_resolves_best_target_and_agile_row_avoids_weather(self):
        game = self.game(["field_medic"])
        game.players[BOT].discard = [game._new_card(key) for key in ("knight", "catapult")]
        game.pending, game.pending_actors = ["test-medic"], [BOT]
        for difficulty in ("normal", "hard"):
            move = choose_bot_move(game, difficulty)
            self.assertEqual(move["card_id"], game.players[BOT].discard[1].id)
        game = self.game(["herald"])
        for player in game.players:
            player.leader_used = True
        game.weather.append(WeatherEffect(0, "frost"))
        for difficulty in ("normal", "hard"):
            self.assertEqual(choose_bot_move(game, difficulty).get("row"), "ranged")

    def test_avoids_scoring_own_scorch_and_uses_profitable_enemy_scorch(self):
        for own, enemy, expect_scorch in (("veteran", "knight", False), ("knight", "catapult", True)):
            game = self.game(["scorch", "infantry"])
            if expect_scorch:
                game.players[0].passed = True
                game.players[BOT].lives = game.players[0].lives = 1
            put(game, BOT, own)
            put(game, 0, enemy)
            for difficulty in ("normal", "hard"):
                move = choose_bot_move(game, difficulty)
                key = next((c.key for c in game.players[BOT].hand if c.id == move.get("card_id")), None)
                self.assertEqual(key == "scorch", expect_scorch)

    def test_small_lead_is_not_a_reason_to_risk_last_life(self):
        game = self.game(["veteran", "champion"])
        put(game, BOT, "veteran")
        put(game, 0, "knight")
        game.players[BOT].lives = 1
        for difficulty in ("normal", "hard"):
            self.assertNotEqual(choose_bot_move(game, difficulty), {"type": "pass"})

    def test_mulligan_exchanges_muster_duplicates_and_respects_faction_limit(self):
        game = self.game(["ellifarn_shield"] * 5, leader="ellifarn_trade")
        game.phase, game.starter_chooser = "mulligan", BOT
        move = choose_bot_move(game)
        self.assertEqual(len(move["card_ids"]), 4)
        self.assertEqual(move["starter"], 0)
        updated = game.act(BOT, move, game.version)
        self.assertEqual(len(updated.players[BOT].hand), 1)

    def test_combinations_spies_draw_and_stormborn(self):
        game = self.game(["spy_hero", "knight"])
        game.players[BOT].deck = [game._new_card("crossbow") for _ in range(4)]
        self.assertEqual(choose_bot_move(game).get("card_id"), game.players[BOT].hand[0].id)
        game = self.game(["storm", "skone_heir"], leader="skone_resilience")
        put(game, BOT, "skone_jarl")
        put(game, BOT, "ranger")
        self.assertEqual(choose_bot_move(game).get("card_id"), game.players[BOT].hand[0].id)

    def test_sacrifices_costly_round_but_never_its_last_life(self):
        game = self.game(["knight", "veteran"])
        put(game, 0, "champion")
        put(game, 0, "regent")
        self.assertEqual(choose_bot_move(game), {"type": "pass"})
        game.players[BOT].lives = 1
        self.assertNotEqual(choose_bot_move(game), {"type": "pass"})

    def test_mixed_faction_games_produce_only_legal_moves_and_finish(self):
        leaders = {"burgundy": "sun", "shiron": "shiron_hand", "skone": "skone_rage", "ellifarn": "ellifarn_trade"}
        for index, preset in enumerate(DECKS.values()):
            for difficulty in DIFFICULTIES:
                with self.subTest(preset=preset["name"], difficulty=difficulty):
                    game = Game.create(["Human", "Bot"], [preset["cards"]] * 2,
                                       [leaders[preset["faction"]]] * 2, seed=index)
                    for _ in range(180):
                        if game.phase == "finished":
                            break
                        side = BOT if game.phase == "mulligan" and not game.players[BOT].mulligan_done else game.turn
                        if game.phase == "mulligan" and game.players[BOT].mulligan_done:
                            side = 0
                        if side == BOT:
                            action = choose_bot_move(game, difficulty)
                            # Mulligan choices can contain swaps beyond the empty legal-move template.
                            if game.phase != "mulligan":
                                self.assertIn(action, game.legal_moves(BOT))
                        else:
                            moves = [m for m in game.legal_moves(0) if m["type"] != "concede"]
                            action = moves[0]
                        game = game.act(side, action, game.version)
                    self.assertEqual(game.phase, "finished")


if __name__ == "__main__":
    unittest.main()
