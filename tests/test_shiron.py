"""Фракционные ограничения, разрешение ничьей и приватные эффекты Империи."""

import json
import unittest

from frontiers.catalog import CATALOG, STARTER_DECK, validate_deck
from frontiers.engine import Game, RuleError
from frontiers.shiron import SHIRON_CARDS, SHIRON_DECK
from test_engine import fixture, put, play


class ShironTests(unittest.TestCase):
    def test_zero_strength_hero_spy_draws_two_and_keeps_hero_immunity(self):
        from frontiers.engine import WeatherEffect
        game = fixture(["shiron_spy_hero"], ["decoy"], "shiron_rain")
        game.players[0].deck = [game._new_card("shiron_eck") for _ in range(2)]
        game.weather.append(WeatherEffect(1, "frost"))
        hero = game.players[0].hand[0]
        game = play(game, 0, "shiron_spy_hero")
        self.assertEqual(len(game.players[0].hand), 2)
        self.assertEqual(game.players[1].board[0].card.id, hero.id)
        self.assertEqual(game.total(1), 0)
        with self.assertRaises(RuleError):
            play(game, 1, "decoy", target=hero)
        game._scorch()
        self.assertEqual(game.players[1].board[0].card.id, hero.id)
        self.assertEqual(SHIRON_DECK.count("shiron_spy_hero"), 1)
        self.assertEqual(SHIRON_DECK.count("shiron_grand_scorpion"), 2)

    def test_amber_and_ruby_resurrect_normal_units(self):
        for key in ("shiron_amber", "shiron_ruby"):
            with self.subTest(key=key):
                game = fixture([key], ["knight"], "shiron_rain")
                target = game._new_card("shiron_eck")
                game.players[0].discard.append(target)
                game = play(game, 0, key)
                self.assertTrue(game.pending)
                move = next(m for m in game.legal_moves(0) if m["type"] == "choose")
                game = game.act(0, move, game.version)
                self.assertEqual({item.card.key for item in game.players[0].board}, {key, "shiron_eck"})

    def test_leonia_doubles_other_units_without_stacking_standards(self):
        from frontiers.cards import CombatRow as Row
        from frontiers.models import PlacedCard
        game = fixture(["shiron_sorceress"], ["knight"], "shiron_rain")
        ally = put(game, 0, "shiron_ruby")
        hero = put(game, 0, "shiron_regent")
        game = play(game, 0, "shiron_sorceress")
        self.assertEqual(game.strengths(0)[ally.id], 12)
        self.assertEqual(game.strengths(0)[hero.id], 10)
        self.assertEqual(next(game.strengths(0)[item.card.id] for item in game.players[0].board if item.card.key == "shiron_sorceress"), 4)
        game.players[0].specials.append(PlacedCard(game._new_card("horn"), Row.RANGED))
        self.assertEqual(game.strengths(0)[ally.id], 12)

    def test_complete_mixed_matches_with_every_leader(self):
        import random
        leaders = ["shiron_hand", "shiron_rain", "shiron_spy", "shiron_nullify", "shiron_levy"]
        for side in (0, 1):
            for seed, leader in enumerate(leaders):
                with self.subTest(side=side, leader=leader):
                    factions = [(SHIRON_DECK, leader), (STARTER_DECK, "academy")]
                    if side:
                        factions.reverse()
                    game = Game.create(["A", "B"], [f[0] for f in factions], [f[1] for f in factions], seed=seed)
                    for actor in (0, 1):
                        game = game.act(actor, {"type": "mulligan", "card_ids": []}, game.version)
                    choices = random.Random(seed)
                    for _ in range(400):
                        if game.phase == "finished":
                            break
                        moves = [m for m in game.legal_moves(game.turn) if m["type"] != "concede"]
                        self.assertTrue(moves)
                        game = game.act(game.turn, choices.choice(moves), game.version)
                    self.assertEqual(game.phase, "finished")

    def test_collection_and_cross_faction_decks(self):
        self.assertEqual(len(SHIRON_CARDS), 30)
        self.assertEqual(sum(card.hero for card in SHIRON_CARDS), 5)
        validate_deck(SHIRON_DECK, "shiron_rain")
        for deck, leader in [(STARTER_DECK, "shiron_rain"), (SHIRON_DECK, "sun")]:
            with self.assertRaises(ValueError):
                validate_deck(deck, leader)

    def end_tied_round(self, first="shiron_rain", second="sun"):
        game = fixture(["knight"], ["knight"], first, second)
        put(game, 0, "knight")
        put(game, 1, "knight")
        for player in game.players:
            player.deck = [game._new_card("knight")]
        game.players[1].passed = True
        return game.act(0, {"type": "pass"}, 0)

    def test_shiron_wins_ties_from_both_seats_without_burgundy_draw(self):
        for side in (0, 1):
            game = self.end_tied_round(*(["shiron_rain", "sun"] if side == 0 else ["sun", "shiron_rain"]))
            self.assertEqual(game.history[0]["winner"], side)
            self.assertEqual([p.lives for p in game.players], [2, 1] if side == 0 else [1, 2])
            self.assertEqual(len(game.players[side].deck), 1)

    def test_shiron_mirror_still_draws(self):
        game = self.end_tied_round("shiron_rain", "shiron_spy")
        self.assertIsNone(game.history[0]["winner"])
        self.assertEqual([p.lives for p in game.players], [1, 1])

    def test_passive_blocks_leaders_from_start_and_mutually_in_mirror(self):
        for leaders in (["shiron_nullify", "sun"], ["shiron_nullify", "shiron_nullify"]):
            decks = [SHIRON_DECK, SHIRON_DECK if leaders[1].startswith("shiron") else STARTER_DECK]
            game = Game.create(["A", "B"], decks, leaders, seed=1)
            self.assertTrue(game.players[1].leader_blocked)
            if leaders[1] == "shiron_nullify":
                self.assertTrue(game.players[0].leader_blocked)
            game.phase, game.turn = "playing", 1
            self.assertNotIn({"type": "leader"}, game.legal_moves(1))
            with self.assertRaises(RuleError):
                game.act(1, {"type": "leader"}, game.version)

    def test_rain_affects_both_siege_rows_but_not_heroes(self):
        game = fixture([], [], "shiron_rain")
        for side in (0, 1):
            put(game, side, "shiron_scorpion")
            put(game, side, "shiron_duke")
        game = game.act(0, {"type": "leader"}, 0)
        self.assertEqual([game.total(side) for side in (0, 1)], [11, 11])
        self.assertEqual(game.weather[0].key, "rain")

    def test_random_resurrection_excludes_heroes_and_retriggers_spy(self):
        game = fixture([], ["knight"], "shiron_hand")
        spy = game._new_card("shiron_spy")
        game.players[0].discard = [spy, game._new_card("shiron_duke"), game._new_card("scorch")]
        game.players[0].deck = [game._new_card("knight") for _ in range(3)]
        revived = game.act(0, {"type": "leader"}, 0)
        self.assertIn(spy.id, [item.card.id for item in revived.players[1].board])
        self.assertEqual(len(revived.players[0].hand), 2)
        self.assertEqual(len(game.players[0].discard), 3)

    def test_resurrected_medic_opens_follow_up_choice(self):
        game = fixture([], [], "shiron_hand")
        game.players[0].discard = [game._new_card("shiron_siege_medic") for _ in range(2)]
        game = game.act(0, {"type": "leader"}, 0)
        self.assertTrue(game.pending)
        self.assertEqual(game.turn, 0)
        move = next(move for move in game.legal_moves(0) if move["type"] == "choose")
        game = game.act(0, move, game.version)
        self.assertFalse(game.pending)
        self.assertEqual(len(game.players[0].board), 2)

    def test_spy_reveals_at_most_three_cards_only_to_owner(self):
        for count in (0, 1, 2, 5):
            game = fixture([], ["knight"] * count, "shiron_spy")
            game = game.act(0, {"type": "leader"}, 0)
            revealed = game.view(0)["players"][0]["revealed"]
            self.assertEqual(len(revealed), min(3, count))
            opponent = game.view(1)
            self.assertNotIn("revealed", opponent["players"][0])
            for card in revealed:
                self.assertNotIn(card["id"], json.dumps(opponent["players"][0]))
            if count:
                selected = game.players[1].hand[0]
                game = play(game, 1, selected.key)
                self.assertNotIn(selected.id, [card["id"] for card in game.view(0)["players"][0]["revealed"]])

    def test_levy_selects_enemy_nonhero_then_transfers_to_hand(self):
        game = fixture([], [], "shiron_levy")
        target = game._new_card("knight")
        hero = game._new_card("champion")
        special = game._new_card("horn")
        game.players[1].discard = [target, hero, special]
        game = game.act(0, {"type": "leader"}, 0)
        self.assertEqual(game.view(0)["pending"]["kind"], "levy")
        moves = [m for m in game.legal_moves(0) if m["type"] == "choose"]
        self.assertEqual(moves, [{"type": "choose", "card_id": target.id}])
        for card in (hero, special):
            with self.assertRaises(RuleError):
                game.act(0, {"type": "choose", "card_id": card.id}, game.version)
        game = game.act(0, moves[0], game.version)
        self.assertFalse(game.pending_levy)
        self.assertIn(target.id, [c.id for c in game.players[0].hand])
        self.assertNotIn(target.id, [c.id for c in game.players[1].discard])
        self.assertEqual(game.turn, 1)

    def test_empty_discard_has_no_leader_move_and_rejects_forged_action(self):
        for leader in ("shiron_hand", "shiron_levy"):
            game = fixture([], [], leader)
            self.assertNotIn({"type": "leader"}, game.legal_moves(0))
            with self.assertRaises(RuleError):
                game.act(0, {"type": "leader"}, 0)
            self.assertFalse(game.players[0].leader_used)
