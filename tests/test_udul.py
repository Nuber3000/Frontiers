"""Udul's multi-step choices, hidden information, portals and round persistence."""
from copy import deepcopy
import unittest

from frontiers.bot import choose_bot_move
from frontiers.cards import CombatRow as Row
from frontiers.catalog import LEADERS, STARTER_DECK, validate_deck
from frontiers.engine import Game, RuleError
from frontiers.models import PlacedCard
from frontiers.udul import UDUL_DECK
from test_engine import fixture, put, play


class UdulTests(unittest.TestCase):
    def game(self, leader="udul_rite", hand=("udul_mauler",), deck=()):
        game = fixture(hand, ["knight"], leader)
        game.players[0].deck = [game._new_card(key) for key in deck]
        return game

    def leader(self, game):
        return game.act(0, {"type": "leader"}, game.version)

    def choose(self, game, key, row=None):
        move = next(move for move in game.legal_moves(0) if move["type"] == "choose"
                    and next(card for card in game._selection_targets(0) if card.id == move["card_id"]).key == key
                    and (row is None or move.get("row") == row))
        return game.act(0, move, game.version)

    def test_incoming_spies_are_executed_and_cannot_be_revived(self):
        for key in ("spy_scribe", "shiron_spy_hero"):
            with self.subTest(key=key):
                game = fixture([key], ["udul_healer"], "sun", "udul_souls")
                game.players[0].deck = [game._new_card("knight") for _ in range(2)]
                friendly = put(game, 1, "udul_mauler")
                spy = game.players[0].hand[0]
                game = play(game, 0, key)
                player = game.players[1]
                self.assertEqual([item.card.id for item in player.board], [friendly.id])
                self.assertEqual([card.id for card in player.discard], [spy.id])
                self.assertEqual(game.scorched, [spy.id])
                arrival = game.view(0)["executed_on_arrival"][0]
                self.assertEqual((arrival["card"]["id"], arrival["side"], arrival["row"]),
                                 (spy.id, 1, "melee"))
                self.assertEqual(player.souls, 1)
                self.assertEqual(len(game.players[0].hand), 2)
                self.assertFalse(game._medic_targets(1))
                game = play(game, 1, "udul_healer")
                self.assertFalse(game.pending)

    def test_udul_cannot_use_spies_from_hand_deck_or_discard(self):
        game = self.game("udul_necromancy", ("spy_scribe", "udul_portal"), ("spy_port", "udul_mauler"))
        player = game.players[0]
        spy = game._new_card("spy_cartographer")
        player.discard.append(spy)
        self.assertNotIn(player.hand[0].id, {move.get("card_id") for move in game.legal_moves(0)})
        with self.assertRaises(RuleError):
            play(game, 0, "spy_scribe")
        self.assertFalse(game._medic_targets(0))
        after_leader = self.leader(game)
        self.assertIsNone(after_leader.selection)
        after_portal = play(game, 0, "udul_portal")
        self.assertEqual([item.card.key for item in after_portal.players[0].board], ["udul_mauler"])
        self.assertEqual([card.key for card in after_portal.players[0].deck], ["spy_port"])
        self.assertEqual(after_portal._draw(after_portal.players[0], 1), 0)

    def test_spy_placed_on_another_faction_survives(self):
        game = fixture(["spy_scribe"], ["knight"], "sun", "sun")
        game = play(game, 0, "spy_scribe")
        self.assertEqual([item.card.key for item in game.players[1].board], ["spy_scribe"])
        self.assertFalse(game.scorched)

    def test_collection_limits_apply_only_to_udul(self):
        for leader in LEADERS:
            if leader.startswith("udul_"):
                validate_deck(UDUL_DECK, leader)
        with self.assertRaises(ValueError):
            validate_deck(UDUL_DECK + ["decoy"], "udul_rite")
        with self.assertRaises(ValueError):
            validate_deck(UDUL_DECK + ["scorch"], "udul_rite")
        with self.assertRaises(ValueError):
            validate_deck([key for key in STARTER_DECK if key != "scorch"] + ["scorch"] * 4, "sun")

    def test_rite_selects_weather_without_exposing_either_deck(self):
        game = self.leader(self.game(deck=("frost", "clear", "udul_mauler")))
        own, enemy = game.view(0), game.view(1)
        self.assertEqual({card["key"] for card in own["pending"]["cards"]}, {"frost", "clear"})
        self.assertEqual(enemy["pending"]["cards"], [])
        self.assertNotIn("deck", enemy["players"][0])
        with self.assertRaises(RuleError):
            game.act(0, {"type": "choose", "card_id": game.players[0].deck[-1].id}, game.version)
        game = self.choose(game, "frost")
        self.assertEqual([effect.key for effect in game.weather], ["frost"])
        self.assertEqual(len(game.players[0].hand), 1)
        self.assertTrue(game.players[0].leader_used)
        self.assertIsNone(game.selection)
        self.assertEqual(game.turn, 1)

    def test_sacrifice_requires_two_distinct_discards_then_one_deck_card(self):
        game = self.leader(self.game("udul_sacrifice", ("udul_mauler", "frost", "udul_horde"), ("udul_hero_warlord",)))
        discarded = game.players[0].hand[0].id
        game = self.choose(game, "udul_mauler")
        self.assertEqual(game.turn, 0)
        self.assertEqual(game.selection["remaining"], 1)
        with self.assertRaises(RuleError):
            game.act(0, {"type": "choose", "card_id": discarded}, game.version)
        game = self.choose(game, "frost")
        self.assertEqual(game.selection["kind"], "draw")
        self.assertEqual(game.turn, 0)
        game = self.choose(game, "udul_hero_warlord")
        self.assertEqual([card.key for card in game.players[0].hand], ["udul_horde", "udul_hero_warlord"])
        self.assertEqual([card.key for card in game.players[0].discard], ["udul_mauler", "frost"])
        self.assertEqual(game.turn, 1)
        self.assertFalse(any("Громар" in line for line in game.view(1)["events"]), "A secret deck choice leaked into the log")

    def test_scorch_units_and_leaders_also_collect_souls(self):
        game = fixture(["udul_mauler"], ["udul_executioner"], "udul_souls", "ellifarn_fury")
        game.turn = 1
        put(game, 0, "udul_mauler")
        put(game, 0, "udul_spears")
        game = play(game, 1, "udul_executioner", Row.MELEE)
        self.assertEqual(game.players[0].souls, 1)
        game.turn = 1
        game = game.act(1, {"type": "leader"}, game.version)
        self.assertEqual(game.players[0].souls, 2)

    def test_necromancy_returns_only_regular_units_and_does_not_play_them(self):
        game = self.game("udul_necromancy")
        game.players[0].discard = [game._new_card(key) for key in ("udul_healer", "udul_horde", "udul_hero_warlord", "scorch")]
        game = self.leader(game)
        game = self.choose(game, "udul_healer")
        self.assertEqual([card["key"] for card in game.view(0)["pending"]["cards"]], ["udul_horde"])
        game = self.choose(game, "udul_horde")
        self.assertFalse(game.players[0].board)
        self.assertFalse(game.pending)
        self.assertEqual([card.key for card in game.players[0].discard], ["udul_hero_warlord", "scorch"])

    def test_spirit_plays_an_actual_deck_horn_in_a_free_slot(self):
        game = self.game("udul_spirit", deck=("horn",))
        game.players[0].specials.append(PlacedCard(game._new_card("horn"), Row.SIEGE))
        game = self.leader(game)
        self.assertEqual({move["row"] for move in game.legal_moves(0) if move["type"] == "choose"}, {"melee", "ranged"})
        game = self.choose(game, "horn", "ranged")
        self.assertFalse(game.players[0].deck)
        self.assertEqual(len(game.players[0].specials), 2)
        self.assertEqual(game.players[0].specials[-1].row, Row.RANGED)
        self.assertFalse(game.players[0].leader_horn)

    def test_souls_count_both_sides_and_all_scorch_sources(self):
        game = self.game("udul_souls", ("scorch",), ("udul_mauler",))
        self.assertNotIn({"type": "leader"}, game.legal_moves(0))
        for side in (0, 0, 1, 1):
            put(game, side, "knight")
        put(game, 1, "regent")
        game = play(game, 0, "scorch")
        self.assertEqual(game.players[0].souls, 3)
        game.turn = 0
        game = self.leader(game)
        self.assertEqual(game.players[0].souls, 0)
        game = self.choose(game, "udul_mauler")
        game.players[1].hand.append(game._new_card("scorch"))
        for _ in range(3):
            put(game, 0, "veteran")
        game = play(game, 1, "scorch")
        self.assertEqual(game.players[0].souls, 3)
        game.turn = 0
        self.assertNotIn({"type": "leader"}, game.legal_moves(0))
        with self.assertRaises(RuleError):
            self.leader(game)

    def test_survivor_can_be_a_hero_and_leader_and_souls_reset_independently(self):
        game = self.game("udul_souls")
        hero = put(game, 0, "udul_hero_warlord")
        game.players[0].leader_used = True
        game.players[0].souls = 3
        game.players[1].passed = True
        game = game.act(0, {"type": "pass"}, game.version)
        self.assertEqual(game.round_number, 2)
        self.assertEqual([item.card.id for item in game.players[0].board], [hero.id])
        self.assertFalse(game.players[0].leader_used)
        self.assertEqual(game.players[0].souls, 3)
        self.assertIn({"type": "leader"}, game.legal_moves(0))

    def test_only_one_unit_survives_without_retriggering_its_ability(self):
        game = self.game()
        cards = [put(game, 0, key) for key in ("udul_mauler", "udul_hero_warlord", "udul_healer")]
        game.players[0].specials.append(PlacedCard(game._new_card("horn"), Row.MELEE))
        game.players[1].passed = True
        before = deepcopy(game)
        game = game.act(0, {"type": "pass"}, game.version)
        again = before.act(0, {"type": "pass"}, before.version)
        self.assertEqual(len(game.players[0].board), 1)
        self.assertEqual(game.players[0].board, again.players[0].board)
        self.assertEqual(len([card for card in game.players[0].discard if card.id in {c.id for c in cards}]), 2)
        self.assertFalse(game.players[0].specials or game.pending)

    def test_portal_resolves_muster_and_hero_scorch_and_skips_specials(self):
        game = self.game(hand=("udul_portal", "udul_horde"), deck=("udul_horde", "udul_hero_scout", "scorch", "horn"))
        put(game, 1, "knight")
        put(game, 1, "knight")
        game = play(game, 0, "udul_portal")
        self.assertCountEqual([item.card.key for item in game.players[0].board],
                              ["udul_horde", "udul_horde", "udul_hero_scout"])
        self.assertFalse(game.players[1].board)
        self.assertEqual([card.key for card in game.players[1].discard], ["knight", "knight"])
        self.assertFalse(game.players[0].hand)
        self.assertEqual([card.key for card in game.players[0].deck], ["scorch", "horn"])
        self.assertEqual([card.key for card in game.players[0].discard], ["udul_portal"])

    def test_portal_two_medics_keep_the_turn_until_both_choices_finish(self):
        game = self.game(hand=("udul_portal",), deck=("udul_healer", "udul_hero_shaman"))
        game.players[0].discard = [game._new_card(key) for key in ("udul_mauler", "udul_engine")]
        game = play(game, 0, "udul_portal")
        self.assertEqual(len(game.pending), 2)
        for remaining in (1, 0):
            move = next(move for move in game.legal_moves(0) if move["type"] == "choose")
            game = game.act(0, move, game.version)
            self.assertEqual(len(game.pending), remaining)
        self.assertEqual(len(game.players[0].board), 4)

    def test_empty_targets_do_not_stall_the_game(self):
        for leader in ("udul_rite", "udul_sacrifice", "udul_necromancy", "udul_spirit", "udul_souls"):
            with self.subTest(leader=leader):
                game = self.game(leader)
                game.players[0].souls = 3
                game = self.leader(game)
                self.assertIsNone(game.selection)
                self.assertTrue(game.players[0].leader_used)
                self.assertEqual(game.turn, 1)

    def test_bot_can_complete_each_new_selection(self):
        for leader, hand, deck, discard in (
                ("udul_rite", ["udul_mauler"], ["frost", "rain"], []),
                ("udul_sacrifice", ["udul_mauler", "frost"], ["udul_hero_warlord"], []),
                ("udul_necromancy", ["udul_mauler"], [], ["udul_mauler", "udul_horde"]),
                ("udul_spirit", ["udul_mauler"], ["horn"], []),
                ("udul_souls", ["udul_mauler"], ["udul_hero_warlord"], [])):
            with self.subTest(leader=leader):
                game = fixture(["knight"], hand, "sun", leader)
                game.turn = 1
                game.players[1].deck = [game._new_card(key) for key in deck]
                game.players[1].discard = [game._new_card(key) for key in discard]
                game.players[1].souls = 3
                game = game.act(1, {"type": "leader"}, game.version)
                for _ in range(3):
                    if not game.selection:
                        break
                    move = choose_bot_move(game, "normal")
                    self.assertIn(move, game.legal_moves(1))
                    self.assertEqual(move["type"], "choose")
                    game = game.act(1, move, game.version)
                self.assertIsNone(game.selection)
