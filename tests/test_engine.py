"""Контракты игровых правил, скрытой информации и завершения матчей."""

import json
import random
import unittest

from frontiers.cards import CombatRow as Row
from frontiers.catalog import CATALOG, DECKS, STARTER_DECK, validate_deck
from frontiers.engine import Game, RuleError, StaleState, WeatherEffect
from frontiers.models import MatchPlayer, PlacedCard


def fixture(hand0=(), hand1=(), leader0="sun", leader1="sun"):
    game = Game([MatchPlayer("Первый", leader0), MatchPlayer("Второй", leader1)],
                random.Random(42), phase="playing")
    game.players[0].hand = [game._new_card(key) for key in hand0]
    game.players[1].hand = [game._new_card(key) for key in hand1]
    return game


def put(game, side, key, row=None):
    row = row or CATALOG[key].rows[0]
    card = game._new_card(key)
    game.players[side].board.append(PlacedCard(card, row))
    return card


def play(game, side, key, row=None, target=None):
    card = next(card for card in game.players[side].hand if card.key == key)
    action = {"type": "play", "card_id": card.id}
    if row:
        action["row"] = row.value
    if target:
        action["target_id"] = target.id
    return game.act(side, action, game.version)


class PreparationTests(unittest.TestCase):
    def test_templates_are_valid_and_deal_ten(self):
        for template in DECKS.values():
            with self.subTest(template=template["name"]):
                validate_deck(template["cards"], "sun")
                game = Game.create(["A", "B"], [template["cards"], STARTER_DECK], ["sun", "fog"], seed=1)
                self.assertEqual(len(game.players[0].hand), 10)
                self.assertEqual(len(game.players[0].deck), len(template["cards"]) - 10)

    def test_mulligan_excludes_returned_cards_from_replacements(self):
        game = Game.create(["A", "B"], [STARTER_DECK, STARTER_DECK], ["sun", "sun"], seed=2)
        selected = [card.id for card in game.players[0].hand[:2]]
        updated = game.act(0, {"type": "mulligan", "card_ids": selected}, game.version)
        self.assertTrue(set(selected).isdisjoint(card.id for card in updated.players[0].hand))
        self.assertEqual(len(updated.players[0].hand), 10)
        self.assertEqual(len(game.players[0].hand), 10)
        updated = updated.act(1, {"type": "mulligan", "card_ids": []}, updated.version)
        self.assertEqual(updated.phase, "playing")

    def test_duplicate_or_excess_mulligan_rejected(self):
        game = Game.create(["A", "B"], [STARTER_DECK, STARTER_DECK], ["sun", "sun"], seed=2)
        ids = [card.id for card in game.players[0].hand]
        for selected in ([ids[0], ids[0]], ids[:3], ["missing"]):
            with self.subTest(selected=selected), self.assertRaises(RuleError):
                game.act(0, {"type": "mulligan", "card_ids": selected}, game.version)
        self.assertFalse(game.players[0].mulligan_done)

    def test_invalid_deck_and_leader_rejected(self):
        too_many_specials = [key for key in STARTER_DECK if CATALOG[key].kind == "unit"] + ["frost"] * 3 + ["fog"] * 3 + ["rain"] * 3 + ["clear"] * 2
        for keys, leader in [(["infantry"] * 22, "sun"), (STARTER_DECK, "unknown"),
                             (["war_bear"] * 22, "sun"), (STARTER_DECK[:10], "sun"),
                             (too_many_specials, "sun")]:
            with self.subTest(leader=leader, count=len(keys)), self.assertRaises(ValueError):
                validate_deck(keys, leader)


class ActionTests(unittest.TestCase):
    def test_move_is_atomic_and_turn_changes(self):
        game = fixture(["knight"], ["knight"])
        card_id = game.players[0].hand[0].id
        with self.assertRaises(RuleError):
            game.act(0, {"type": "play", "card_id": card_id, "row": "siege"}, 0)
        self.assertEqual(len(game.players[0].hand), 1)
        updated = play(game, 0, "knight")
        self.assertEqual(updated.turn, 1)
        self.assertEqual(updated.version, 1)
        self.assertEqual(game.version, 0)
        with self.assertRaises(RuleError):
            updated.act(0, {"type": "pass"}, updated.version)
        with self.assertRaises(StaleState):
            updated.act(1, {"type": "pass"}, 0)

    def test_spy_draws_two_and_goes_to_opponent_discard(self):
        game = fixture(["spy_scribe"], ["knight"])
        spy_id = game.players[0].hand[0].id
        game.players[0].deck = [game._new_card("knight"), game._new_card("scout")]
        game = play(game, 0, "spy_scribe")
        self.assertEqual(game.total(1), 4)
        self.assertEqual(len(game.players[0].hand), 2)
        game = game.act(1, {"type": "pass"}, game.version)
        game = game.act(0, {"type": "pass"}, game.version)
        self.assertIn(spy_id, [card.id for card in game.players[1].discard])

    def test_decoy_retrieves_enemy_spy_without_triggering_effect(self):
        game = fixture(["decoy"], [])
        spy = put(game, 0, "spy_scribe")
        game = play(game, 0, "decoy", target=spy)
        self.assertEqual(game.players[0].hand[0].id, spy.id)
        self.assertEqual(game.players[0].board[0].card.key, "decoy")
        self.assertEqual(game.total(0), 0)

    def test_hero_cannot_be_decoyed(self):
        game = fixture(["decoy"], [])
        target = put(game, 0, "regent")
        with self.assertRaises(RuleError):
            play(game, 0, "decoy", target=target)
        self.assertEqual(len(game.players[0].hand), 1)

    def test_medic_waits_for_choice_and_chains(self):
        game = fixture(["healer_hero"], ["knight"])
        medic = game._new_card("field_medic")
        infantry = game._new_card("knight")
        game.players[0].discard = [medic, infantry, game._new_card("regent")]
        game = play(game, 0, "healer_hero")
        self.assertEqual(game.turn, 0)
        self.assertTrue(game.pending)
        game = game.act(0, {"type": "choose", "card_id": medic.id}, game.version)
        self.assertTrue(game.pending)
        game = game.act(0, {"type": "choose", "card_id": infantry.id}, game.version)
        self.assertFalse(game.pending)
        self.assertEqual(game.turn, 1)
        self.assertEqual(game.total(0), 17)

    def test_medic_cannot_restore_hero_or_special(self):
        game = fixture(["field_medic"], [])
        hero = game._new_card("regent")
        game.players[0].discard = [hero, game._new_card("knight")]
        game = play(game, 0, "field_medic")
        with self.assertRaises(RuleError):
            game.act(0, {"type": "choose", "card_id": hero.id}, game.version)
        self.assertTrue(game.pending)

    def test_muster_pulls_hand_and_deck_but_not_captain(self):
        game = fixture(["road_company", "road_company", "company_captain"], [])
        game.players[0].deck = [game._new_card("road_company"), game._new_card("knight")]
        game = play(game, 0, "road_company")
        self.assertEqual(len(game.players[0].board), 3)
        self.assertEqual([card.key for card in game.players[0].hand], ["company_captain"])
        self.assertEqual([card.key for card in game.players[0].deck], ["knight"])

    def test_agile_unit_accepts_both_rows(self):
        for row in (Row.MELEE, Row.RANGED):
            game = play(fixture(["herald"], []), 0, "herald", row)
            self.assertEqual(game.players[0].board[0].row, row)

    def test_private_view_never_exposes_opponent_hand_or_deck(self):
        game = Game.create(["A", "B"], [STARTER_DECK, STARTER_DECK], ["sun", "sun"], seed=3)
        view = game.view(0)
        self.assertNotIn("hand", view["players"][1])
        self.assertNotIn("deck", view["players"][0])
        payload = json.dumps(view)
        for card in game.players[1].hand + game.players[1].deck + game.players[0].deck:
            self.assertNotIn(card.id, payload)


class EffectTests(unittest.TestCase):
    def test_weather_then_bond_then_morale_then_horn(self):
        game = fixture(["horn"], [])
        put(game, 0, "catapult")
        put(game, 0, "catapult")
        put(game, 0, "siege_expert")
        game.weather.append(WeatherEffect(1, "rain"))
        game = play(game, 0, "horn", Row.SIEGE)
        self.assertEqual(game.total(0), 14)

    def test_weather_and_horn_do_not_modify_hero(self):
        game = fixture(["horn"], [])
        hero = put(game, 0, "regent")
        put(game, 0, "knight")
        game.weather.append(WeatherEffect(1, "frost"))
        game = play(game, 0, "horn", Row.MELEE)
        self.assertEqual(game.strengths(0)[hero.id], 10)
        self.assertEqual(game.total(0), 12)

    def test_storm_affects_both_rows_on_both_sides(self):
        game = fixture(["storm"], [])
        for side in (0, 1):
            put(game, side, "knight")
            put(game, side, "scout")
            put(game, side, "trebuchet")
        game = play(game, 0, "storm")
        self.assertEqual([game.total(0), game.total(1)], [7, 7])

    def test_clear_removes_all_weather_and_discards_their_cards(self):
        game = fixture(["clear"], [])
        weather_card = game._new_card("frost")
        game.weather = [WeatherEffect(1, "frost", weather_card), WeatherEffect(0, "fog")]
        game = play(game, 0, "clear")
        self.assertEqual(game.weather, [])
        self.assertIn(weather_card.id, [card.id for card in game.players[1].discard])

    def test_scorch_hits_tied_maximum_on_both_sides_ignoring_heroes(self):
        game = fixture(["scorch"], [])
        put(game, 0, "regent")
        put(game, 0, "trebuchet")
        put(game, 1, "ballista")
        put(game, 1, "knight")
        game = play(game, 0, "scorch")
        self.assertEqual([item.card.key for item in game.players[0].board], ["regent"])
        self.assertEqual([item.card.key for item in game.players[1].board], ["knight"])
        self.assertIn("scorch", [card.key for card in game.players[0].discard])

    def test_horn_only_boosts_own_row_and_cannot_stack(self):
        game = fixture(["horn", "horn"], ["knight"])
        put(game, 0, "knight")
        put(game, 1, "knight")
        game = play(game, 0, "horn", Row.MELEE)
        self.assertEqual([game.total(0), game.total(1)], [10, 5])
        game.turn = 0
        with self.assertRaises(RuleError):
            play(game, 0, "horn", Row.MELEE)

    def test_scorch_reports_only_public_victims_and_resets_next_action(self):
        game = fixture(["scorch"], ["knight"])
        hero = put(game, 0, "regent")
        own = put(game, 0, "trebuchet")
        enemy = put(game, 1, "ballista")
        survivor = put(game, 1, "knight")
        burned = play(game, 0, "scorch")
        self.assertEqual(set(burned.scorched), {own.id, enemy.id})
        self.assertNotIn(hero.id, burned.scorched)
        self.assertNotIn(survivor.id, burned.scorched)
        self.assertEqual(game.scorched, [])
        for side in (0, 1):
            view = burned.view(side)
            self.assertEqual(set(view["scorched"]), {own.id, enemy.id})
            view["scorched"].clear()
            self.assertEqual(len(burned.scorched), 2)
        following = play(burned, 1, "knight")
        self.assertEqual(following.scorched, [])
        self.assertEqual(len(burned.scorched), 2)
        with self.assertRaises(StaleState):
            burned.act(1, {"type": "pass"}, 0)
        self.assertEqual(len(burned.scorched), 2)

    def test_decoy_and_round_cleanup_do_not_report_scorch(self):
        game = fixture(["decoy"], [])
        target = put(game, 0, "knight")
        game = play(game, 0, "decoy", target=target)
        self.assertEqual(game.scorched, [])
        game = game.act(1, {"type": "pass"}, game.version)
        game = game.act(0, {"type": "pass"}, game.version)
        self.assertEqual(game.scorched, [])

    def test_consecutive_scorches_report_only_the_latest_victims(self):
        game = fixture(["scorch"], ["scorch"])
        own = put(game, 0, "knight")
        enemies = [put(game, 1, "crossbow") for _ in range(2)]
        game = play(game, 0, "scorch")
        self.assertEqual(set(game.scorched), {card.id for card in enemies})
        game = play(game, 1, "scorch")
        self.assertEqual(game.scorched, [own.id])

    def test_unit_scorch_reports_its_victims(self):
        game = fixture(["fire_walker"], [])
        targets = [put(game, 1, "knight") for _ in range(2)]
        game = play(game, 0, "fire_walker")
        self.assertEqual(set(game.scorched), {card.id for card in targets})

    def test_empty_scorch_and_unmet_leader_threshold_report_no_victims(self):
        self.assertEqual(play(fixture(["scorch"], []), 0, "scorch").scorched, [])
        game = fixture([], [], leader0="mortar")
        put(game, 1, "scout")
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual(game.scorched, [])

    def test_unit_horn_does_not_boost_itself(self):
        game = fixture(["banner_bearer", "horn"], [])
        put(game, 0, "knight")
        game = play(game, 0, "banner_bearer")
        self.assertEqual(game.total(0), 12)
        game.turn = 0
        game = play(game, 0, "horn", Row.MELEE)
        self.assertEqual(game.total(0), 14)

    def test_mushroom_is_discarded_and_only_transforms_present_units(self):
        game = fixture(["mushroom", "young_berserker"], [])
        put(game, 0, "young_berserker")
        game = play(game, 0, "mushroom", Row.RANGED)
        game.turn = 0
        game = play(game, 0, "young_berserker")
        self.assertEqual([item.card.key for item in game.players[0].board], ["young_bear", "young_berserker"])
        self.assertEqual(game.total(0), 10)
        self.assertEqual(game.players[0].specials, [])
        self.assertEqual([card.key for card in game.players[0].discard], ["mushroom"])

    def test_mushroom_works_on_a_row_with_a_standard(self):
        game = fixture(["horn", "mushroom"], [])
        put(game, 0, "young_berserker")
        put(game, 0, "young_berserker")
        put(game, 1, "young_berserker")
        game = play(game, 0, "horn", Row.RANGED)
        game.turn = 0
        mushroom_id = next(card.id for card in game.players[0].hand if card.key == "mushroom")
        moves = [move for move in game.legal_moves(0) if move.get("card_id") == mushroom_id]
        self.assertEqual({move["row"] for move in moves}, {row.value for row in Row})
        game = play(game, 0, "mushroom", Row.RANGED)
        self.assertEqual(game.total(0), 64)
        self.assertEqual([item.card.key for item in game.players[0].specials], ["horn"])
        self.assertEqual(game.players[1].board[0].card.key, "young_berserker")

    def test_mushroom_does_not_block_a_subsequent_standard(self):
        game = fixture(["mushroom", "horn"], [])
        put(game, 0, "berserker")
        game = play(game, 0, "mushroom", Row.MELEE)
        game.turn = 0
        game = play(game, 0, "horn", Row.MELEE)
        self.assertEqual(game.total(0), 28)

    def test_mushroom_can_be_played_on_any_empty_row(self):
        for row in Row:
            with self.subTest(row=row):
                game = play(fixture(["mushroom"], []), 0, "mushroom", row)
                self.assertEqual(game.players[0].specials, [])
                self.assertEqual([card.key for card in game.players[0].discard], ["mushroom"])

    def test_druid_still_transforms_future_berserkers(self):
        game = fixture(["druid", "young_berserker"], [])
        put(game, 0, "young_berserker")
        game = play(game, 0, "druid")
        game.turn = 0
        game = play(game, 0, "young_berserker")
        self.assertEqual([item.card.key for item in game.players[0].board], ["young_bear", "druid", "young_bear"])
        self.assertEqual(game.total(0), 40)

    def test_transformation_survives_decoy(self):
        game = fixture(["decoy"], [])
        bear = put(game, 0, "war_bear")
        game = play(game, 0, "decoy", target=bear)
        self.assertEqual(game.players[0].hand[0].key, "war_bear")

    def test_avenger_appears_next_round(self):
        game = fixture([], [])
        put(game, 0, "watchman")
        game = game.act(0, {"type": "pass"}, game.version)
        game = game.act(1, {"type": "pass"}, game.version)
        self.assertEqual(game.round_number, 2)
        self.assertEqual(game.players[0].board[0].card.key, "avenger")


class LeaderAndRoundTests(unittest.TestCase):
    def test_leader_clear_weather_and_once_per_match(self):
        game = fixture([], [], leader0="sun")
        game.weather.append(WeatherEffect(1, "storm"))
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertFalse(game.weather)
        game.turn = 0
        with self.assertRaises(RuleError):
            game.act(0, {"type": "leader"}, game.version)

    def test_leader_fog(self):
        game = fixture([], [], leader0="fog")
        put(game, 1, "scout")
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual(game.total(1), 1)

    def test_leader_scorch_threshold_and_hero_immunity(self):
        for leader, row, first, second in [("mortar", Row.RANGED, "scout", "ranger"),
                                            ("war", Row.SIEGE, "trebuchet", "ballista")]:
            with self.subTest(leader=leader):
                game = fixture([], [], leader0=leader)
                put(game, 1, first)
                put(game, 1, second)
                game = game.act(0, {"type": "leader"}, game.version)
                expected = ["scout"] if row == Row.RANGED else []
                self.assertEqual([item.card.key for item in game.players[1].board], expected)

    def test_academy_boost_and_horn_do_not_stack(self):
        game = fixture(["horn"], [], leader0="academy")
        put(game, 0, "trebuchet")
        game = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual(game.total(0), 12)
        game.turn = 0
        with self.assertRaises(RuleError):
            play(game, 0, "horn", Row.SIEGE)

    def test_passed_opponent_can_no_longer_act_and_winner_draws(self):
        game = fixture(["knight"], ["knight"])
        game.players[1].deck = [game._new_card("scout")]
        game = game.act(0, {"type": "pass"}, game.version)
        game = play(game, 1, "knight")
        self.assertEqual(game.turn, 1)
        game = game.act(1, {"type": "pass"}, game.version)
        self.assertEqual(game.players[0].lives, 1)
        self.assertEqual(game.round_number, 2)
        self.assertEqual(game.turn, 1)
        self.assertEqual(game.players[1].hand[0].key, "scout")

    def test_two_ties_end_in_draw_and_swap_starter(self):
        game = fixture(["knight"], ["knight"])
        for _ in range(2):
            actor = game.turn
            game = game.act(actor, {"type": "pass"}, game.version)
            game = game.act(game.turn, {"type": "pass"}, game.version)
        self.assertEqual(game.phase, "finished")
        self.assertIsNone(game.winner)
        self.assertEqual(game.round_starter, 1)

    def test_concede_works_while_other_player_is_selecting(self):
        game = fixture(["field_medic"], [])
        game.players[0].discard = [game._new_card("knight")]
        game = play(game, 0, "field_medic")
        game = game.act(1, {"type": "concede"}, game.version)
        self.assertEqual(game.winner, 0)
        self.assertEqual(game.phase, "finished")

    def test_automatic_pass_and_match_end_when_no_actions_remain(self):
        game = fixture(["knight"], [])
        game.players[0].leader_used = game.players[1].leader_used = True
        game = play(game, 0, "knight")
        self.assertEqual(game.phase, "finished")
        self.assertEqual(game.winner, 0)


class SimulationTests(unittest.TestCase):
    def test_one_hundred_complete_matches_using_legal_commands(self):
        for seed in range(100):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                decks = [list(STARTER_DECK), list(STARTER_DECK)]
                leaders = rng.sample(["sun", "mortar", "war", "academy", "fog"], 2)
                game = Game.create(["A", "B"], decks, leaders, seed=seed)
                initial_ids = {card.id for player in game.players for card in player.hand + player.deck}
                for side in (0, 1):
                    selected = [card.id for card in game.players[side].hand[:rng.randrange(3)]]
                    game = game.act(side, {"type": "mulligan", "card_ids": selected}, game.version)
                steps = 0
                while game.phase != "finished" and steps < 250:
                    moves = [move for move in game.legal_moves(game.turn) if move["type"] != "concede"]
                    productive = [move for move in moves if move["type"] != "pass"]
                    move = rng.choice(productive if productive and rng.random() > 0.12 else moves)
                    game = game.act(game.turn, move, game.version)
                    ids = []
                    for player in game.players:
                        ids.extend(card.id for card in player.deck + player.hand + player.discard)
                        ids.extend(item.card.id for item in player.board + player.specials)
                    ids.extend(effect.card.id for effect in game.weather if effect.card)
                    self.assertEqual(len(ids), len(set(ids)), "Экземпляр карты дублируется между зонами")
                    self.assertTrue(initial_ids.issubset(ids), "Экземпляр карты потерян между зонами")
                    steps += 1
                self.assertEqual(game.phase, "finished")
                self.assertLessEqual(len(game.history), 3)


if __name__ == "__main__":
    unittest.main()
