import unittest

from frontiers.cards import CombatRow as Row
from frontiers.catalog import STARTER_DECK
from frontiers.ellifarn import ELLIFARN_DECK
from frontiers.engine import Game, RuleError, WeatherEffect
from frontiers.models import PlacedCard


class EllifarnTests(unittest.TestCase):
    def game(self, leader="ellifarn_trade", opponent="sun"):
        other_deck = ELLIFARN_DECK if opponent.startswith("ellifarn_") else STARTER_DECK
        return Game.create(["Council", "Opponent"], [ELLIFARN_DECK, other_deck],
                           [leader, opponent], seed=7)

    def playing(self, leader):
        game = self.game(leader)
        game = game.act(0, {"type": "mulligan", "starter": 0}, game.version)
        return game.act(1, {"type": "mulligan"}, game.version)

    def place(self, game, side, key, row):
        item = PlacedCard(game._new_card(key), row)
        game.players[side].board.append(item)
        return item.card.id

    def test_opening_hand_and_chosen_starter(self):
        game = self.game()
        hand, other = (player.hand for player in game.players)
        self.assertEqual((len(hand), len(other)), (11, 10))
        self.assertTrue(game.view(0)["players"][0]["can_choose_starter"])
        self.assertFalse(game.view(1)["players"][1]["can_choose_starter"])
        for side, cards, count in ((0, hand, 5), (1, other, 3)):
            with self.assertRaises(RuleError):
                game.act(side, {"type": "mulligan", "card_ids": [card.id for card in cards[:count]]},
                         game.version)
        with self.assertRaises(RuleError):
            game.act(1, {"type": "mulligan", "starter": 1}, game.version)
        selected = [card.id for card in hand[:4]]
        game = game.act(0, {"type": "mulligan", "card_ids": selected, "starter": 1}, game.version)
        self.assertFalse(set(selected) & {card.id for card in game.players[0].hand})
        game = game.act(1, {"type": "mulligan"}, game.version)
        self.assertEqual((game.phase, game.turn, game.round_starter), ("playing", 1, 1))
        self.assertEqual(len(game.players[0].hand), 11)

    def test_mirror_has_one_chooser(self):
        game = self.game(opponent="ellifarn_aim")
        chooser = game.starter_chooser
        self.assertEqual([len(player.hand) for player in game.players], [11, 11])
        self.assertEqual({move["starter"] for move in game.legal_moves(chooser) if "starter" in move}, {0, 1})
        self.assertFalse(any("starter" in move for move in game.legal_moves(1 - chooser)))

    def test_trade_draws_one(self):
        game = self.playing("ellifarn_trade")
        next_card = game.players[0].deck[0].id
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual(game.players[0].hand[-1].id, next_card)
        self.assertTrue(game.players[0].leader_used)

    def test_aim_uses_ranged_slot_and_spares_heroes(self):
        game = self.playing("ellifarn_aim")
        regular = self.place(game, 0, "ellifarn_marksman", Row.RANGED)
        hero = self.place(game, 0, "ellifarn_hero_mirinorm", Row.RANGED)
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual(game.players[0].leader_horn, {Row.RANGED})
        self.assertEqual(game.strengths(0), {regular: 8, hero: 10})

    def test_fury_destroys_all_tied_enemies_without_minimum(self):
        game = self.playing("ellifarn_fury")
        victims = [self.place(game, 1, "blue_guard", Row.MELEE) for _ in range(2)]
        own = self.place(game, 0, "ellifarn_captain", Row.MELEE)
        hero = self.place(game, 1, "champion", Row.MELEE)
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertCountEqual(game.scorched, victims)
        self.assertEqual(list(game.strengths(0)), [own])
        self.assertEqual(list(game.strengths(1)), [hero])

    def test_logistics_moves_only_for_an_improvement(self):
        game = self.playing("ellifarn_logistics")
        self.place(game, 0, "ellifarn_tracker", Row.MELEE)
        self.place(game, 0, "ellifarn_riders", Row.RANGED)
        self.place(game, 0, "ellifarn_captain", Row.MELEE)
        game.weather.append(WeatherEffect(1, "frost"))
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual([item.row for item in game.players[0].board],
                         [Row.RANGED, Row.RANGED, Row.MELEE])

    def test_scout_and_liara_can_revive_a_unit(self):
        for key in ("ellifarn_scout", "ellifarn_hero_grove", "ellifarn_hero_langins"):
            with self.subTest(card=key):
                game = self.playing("ellifarn_trade")
                player = game.players[0]
                medic = game._new_card(key)
                target = game._new_card("ellifarn_captain")
                player.hand.append(medic)
                player.discard.append(target)
                game = game.act(0, {"type": "play", "card_id": medic.id, "row": "ranged"}, game.version)
                revive = {"type": "choose", "card_id": target.id, "row": "melee"}
                self.assertIn(revive, game.legal_moves(0))
                game = game.act(0, revive, game.version)
                self.assertIn(target.id, game.strengths(0))

    def test_archers_and_marksman_can_play_in_either_row(self):
        for row in (Row.MELEE, Row.RANGED):
            for key in ("ellifarn_archers", "ellifarn_marksman"):
                with self.subTest(card=key, row=row):
                    game = self.playing("ellifarn_trade")
                    player = game.players[0]
                    card = game._new_card(key)
                    player.hand = [card]
                    player.deck = [game._new_card("ellifarn_archers")]
                    game = game.act(0, {"type": "play", "card_id": card.id, "row": row.value}, game.version)
                    expected = [row, row] if key == "ellifarn_archers" else [row]
                    self.assertEqual([item.row for item in game.players[0].board], expected)

    def test_riders_summon_four_copies_into_the_selected_row(self):
        self.assertEqual(ELLIFARN_DECK.count("ellifarn_riders"), 4)
        for row in (Row.MELEE, Row.RANGED):
            with self.subTest(row=row):
                game = self.playing("ellifarn_trade")
                player = game.players[0]
                player.hand = [game._new_card("ellifarn_riders") for _ in range(2)]
                player.deck = [game._new_card("ellifarn_riders") for _ in range(2)]
                discarded = game._new_card("ellifarn_riders")
                player.discard = [discarded]
                game = game.act(0, {"type": "play", "card_id": player.hand[0].id,
                                    "row": row.value}, game.version)
                self.assertEqual([item.row for item in game.players[0].board], [row] * 4)
                self.assertEqual(game.row_total(0, row), 20)
                self.assertFalse(game.players[0].hand)
                self.assertFalse(game.players[0].deck)
                self.assertEqual([card.id for card in game.players[0].discard], [discarded.id])

    def test_tracker_bond_morale_and_wardens_horn(self):
        game = self.playing("ellifarn_trade")
        pair = [self.place(game, 0, "ellifarn_tracker", Row.MELEE) for _ in range(2)]
        separate = self.place(game, 0, "ellifarn_tracker", Row.RANGED)
        self.assertEqual([game.strengths(0)[card] for card in pair], [12, 12])
        self.assertEqual(game.strengths(0)[separate], 6)
        warden = self.place(game, 0, "ellifarn_warden", Row.MELEE)
        hero = self.place(game, 0, "ellifarn_hero_mirinorm", Row.MELEE)
        marksman = self.place(game, 0, "ellifarn_marksman", Row.MELEE)
        outrider = self.place(game, 0, "ellifarn_outrider", Row.MELEE)
        values = game.strengths(0)
        self.assertEqual([values[card] for card in pair], [28, 28])
        self.assertEqual((values[warden], values[marksman], values[outrider], values[hero]),
                         (8, 10, 10, 10))
        game.players[0].leader_horn.add(Row.MELEE)
        values = game.strengths(0)
        self.assertEqual([values[card] for card in pair], [28, 28])
        self.assertEqual(values[warden], 16)
        self.assertEqual(values[hero], 10)
        self.assertEqual(values[separate], 6)

    def test_brann_and_eleri_scorch_only_the_enemy_target_row_at_ten(self):
        cases = (("ellifarn_captain", Row.MELEE, "knight", "blue_guard", "scout"),
                 ("ellifarn_hero_mirinorm", Row.RANGED, "crossbow", "scout", "veteran"))
        for key, row, first, weaker, other in cases:
            for threshold in (9, 10, 20):
                with self.subTest(card=key, total=threshold):
                    game = self.playing("ellifarn_trade")
                    card = game._new_card(key)
                    game.players[0].hand = [card]
                    game.players[0].board.clear()
                    game.players[1].board.clear()
                    victims = [self.place(game, 1, first, row)]
                    victims.append(self.place(game, 1, weaker if threshold == 9 else "ellifarn_riders", row))
                    self.assertEqual(game.row_total(1, row), min(threshold, 10))
                    other_row = Row.RANGED if row == Row.MELEE else Row.MELEE
                    spared = self.place(game, 1, other, other_row)
                    ally = self.place(game, 0, "knight", Row.MELEE)
                    if threshold == 20:
                        # Heroes contribute strength but cannot be executed.
                        protected = self.place(game, 1, "regent", row)
                        self.assertEqual(game.row_total(1, row), 20)
                    game = game.act(0, {"type": "play", "card_id": card.id,
                                        "row": row.value}, game.version)
                    self.assertCountEqual(game.scorched, victims if threshold >= 10 else [])
                    self.assertIn(spared, game.strengths(1))
                    self.assertIn(ally, game.strengths(0))
                    self.assertIn(card.id, game.strengths(0))
                    if threshold == 20:
                        self.assertIn(protected, game.strengths(1))
