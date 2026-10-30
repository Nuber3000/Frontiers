"""Сконе: возвращение отрядов, пять лидеров и взаимодействие фракций."""

import random
import unittest

from frontiers.cards import CombatRow as Row
from frontiers.catalog import CATALOG, LEADERS, STARTER_DECK, catalog_view, validate_deck
from frontiers.engine import Game, RuleError, WeatherEffect
from frontiers.skone import SKONE_DECK
from frontiers.shiron import SHIRON_DECK
from test_engine import fixture, put, play


class SkoneTests(unittest.TestCase):
    def leader(self, game, row=None):
        action = {"type": "leader"}
        if row:
            action["row"] = row.value
        return game.act(game.turn, action, game.version)

    def third_round(self, game):
        game.round_number = 2
        # Обе стороны сохраняют по жизни после выигрышей разных раундов.
        game.players[0].lives = 1
        game.players[1].lives = 2
        put(game, 0, "skone_heir")
        game.players[0].passed = game.players[1].passed = True
        game._end_round()
        return game

    def test_catalog_decks_and_faction_boundaries(self):
        for leader in LEADERS:
            if LEADERS[leader]["faction"] == "skone":
                validate_deck(list(SKONE_DECK), leader)
        data = catalog_view()
        self.assertTrue(data["factions"]["skone"]["playable"])
        for key in ("berserker", "young_berserker", "ranger", "druid", "mushroom", "storm"):
            self.assertEqual(CATALOG[key].faction, "skone")
            self.assertTrue(next(c for c in data["cards"] if c["key"] == key)["available"])
            with self.assertRaises(ValueError):
                validate_deck(list(STARTER_DECK) + [key], "sun")
        with self.assertRaises(ValueError):
            validate_deck(list(SKONE_DECK) + ["knight"], "skone_storm")
        with self.assertRaises(ValueError):
            validate_deck(list(SKONE_DECK) + ["skone_ancestor"], "skone_rage")

    def test_resilience_is_passive_halves_before_bonuses_and_preserves_zero(self):
        game = Game.create(["A", "B"], [list(SKONE_DECK), list(STARTER_DECK)], ["skone_resilience", "sun"], seed=2)
        self.assertTrue(game.players[0].leader_used)
        game.phase = "playing"
        game.turn = 0
        with self.assertRaises(RuleError):
            self.leader(game)
        plain = put(game, 0, "skone_heir")
        odd = put(game, 0, "knight")
        zero = put(game, 0, "skone_rooster")
        hero = put(game, 0, "skone_shieldhero")
        enemy = put(game, 1, "knight")
        game.weather = [WeatherEffect(1, "frost"), WeatherEffect(1, "frost")]
        self.assertEqual([game.strengths(0)[card.id] for card in (plain, odd, zero, hero)], [2, 3, 0, 10])
        self.assertEqual(game.strengths(1)[enemy.id], 1)
        game.players[0].leader_horn.add(Row.MELEE)
        self.assertEqual(game.strengths(0)[odd.id], 6)
        game.players[0].leader_blocked = True
        self.assertEqual(game.strengths(0)[odd.id], 2)

    def test_nullifier_blocks_resilience_and_active_leaders(self):
        for key in LEADERS:
            if LEADERS[key]["faction"] != "skone":
                continue
            game = Game.create(["A", "B"], [list(SKONE_DECK), list(SHIRON_DECK)], [key, "shiron_nullify"], seed=4)
            game.phase, game.turn = "playing", 0
            self.assertTrue(game.players[0].leader_blocked)
            self.assertFalse(any(m["type"] == "leader" for m in game.legal_moves(0)))
            with self.assertRaises(RuleError):
                self.leader(game, Row.MELEE)

    def test_storm_affects_both_ranged_and_siege_not_melee_or_heroes(self):
        game = fixture(["skone_heir"], ["knight"], "skone_storm")
        own = put(game, 0, "skone_lightship")
        enemy = put(game, 1, "ballista")
        melee = put(game, 1, "knight")
        hero = put(game, 0, "druid")
        game = self.leader(game)
        self.assertEqual(game.strengths(0)[own.id], 1)
        self.assertEqual(game.strengths(1)[enemy.id], 1)
        self.assertEqual(game.strengths(1)[melee.id], 5)
        self.assertEqual(game.strengths(0)[hero.id], 8)
        self.assertTrue(game.players[0].leader_used)

    def test_battlecry_requires_free_chosen_row_and_does_not_stack(self):
        for row in Row:
            game = fixture(["horn", "skone_heir"], ["knight"], "skone_horn")
            ordinary = put(game, 0, "skone_heir", row)
            hero = put(game, 0, "skone_shieldhero", row)
            with self.assertRaises(RuleError):
                self.leader(game)
            self.assertFalse(game.players[0].leader_used)
            game = self.leader(game, row)
            self.assertEqual(game.strengths(0)[ordinary.id], 8)
            self.assertEqual(game.strengths(0)[hero.id], 10)
            game.turn = 0
            self.assertFalse(any(m.get("row") == row.value for m in game.legal_moves(0) if m["type"] == "play" and m["card_id"] == game.players[0].hand[0].id))
            with self.assertRaises(RuleError):
                play(game, 0, "horn", row)
        game = fixture(["horn", "skone_heir"], ["knight"], "skone_horn")
        game = play(game, 0, "horn", Row.SIEGE)
        game.turn = 0
        with self.assertRaises(RuleError):
            self.leader(game, Row.SIEGE)
        self.assertNotIn({"type": "leader", "row": "siege"}, game.legal_moves(0))

    def test_rage_transforms_only_own_berserkers_on_all_lines(self):
        for actor in (0, 1):
            game = fixture(["berserker"], ["berserker"], "skone_rage", "skone_rage")
            game.turn = actor
            for side in (0, 1):
                put(game, side, "berserker")
                put(game, side, "young_berserker")
                put(game, side, "skone_ghost", Row.RANGED)
                game.players[side].discard = [game._new_card("skone_ghost")]
            game = self.leader(game)
            self.assertEqual([c.card.key for c in game.players[actor].board], ["war_bear", "young_bear", "skone_bear"])
            self.assertEqual([c.card.key for c in game.players[1-actor].board], ["berserker", "young_berserker", "skone_ghost"])
            self.assertEqual(sum("Превращение" in event for event in game.events), 3)
            for player in game.players:
                self.assertEqual(player.hand[0].key, "berserker")
                self.assertEqual(player.discard[0].key, "skone_ghost")

    def test_ivar_is_agile_berserker_and_urs_is_only_a_second_form(self):
        self.assertEqual(CATALOG["skone_ghost"].rows, (Row.MELEE, Row.RANGED))
        self.assertEqual(CATALOG["skone_ghost"].transform_to, "skone_bear")
        self.assertEqual(CATALOG["skone_ghost"].abilities, ("berserker",))
        self.assertFalse(CATALOG["skone_bear"].collectible)
        self.assertIn("skone_ghost", SKONE_DECK)
        self.assertNotIn("skone_bear", SKONE_DECK)
        with self.assertRaises(ValueError):
            validate_deck(list(SKONE_DECK) + ["skone_bear"], "skone_rage")
        for row in (Row.MELEE, Row.RANGED):
            game = fixture(["skone_ghost", "mushroom", "decoy"], ["knight"], "skone_storm")
            ivar = game.players[0].hand[0]
            self.assertEqual({m["row"] for m in game.legal_moves(0) if m.get("card_id") == ivar.id}, {"melee", "ranged"})
            game = play(game, 0, "skone_ghost", row)
            game.turn = 0
            game = play(game, 0, "mushroom", row)
            bear = game.players[0].board[0]
            self.assertEqual((bear.card.id, bear.card.key, bear.row), (ivar.id, "skone_bear", row))
            self.assertEqual(game.strengths(0)[ivar.id], 12)
            game.turn = 0
            game = play(game, 0, "decoy", target=bear.card)
            self.assertEqual(next(c.key for c in game.players[0].hand if c.id == ivar.id), "skone_bear")

    def test_bragi_morale_boosts_others_but_not_himself_or_heroes(self):
        game = fixture(["skone_skald"], ["knight"], "skone_storm")
        ally = put(game, 0, "skone_heir")
        hero = put(game, 0, "skone_shieldhero")
        remote = put(game, 0, "ranger")
        game = play(game, 0, "skone_skald", Row.MELEE)
        bard = next(c.card for c in game.players[0].board if c.card.key == "skone_skald")
        self.assertEqual([game.strengths(0)[c.id] for c in (ally, hero, remote, bard)], [5, 10, 6, 4])
        self.assertEqual(CATALOG["berserker"].name, "Хельм Безумный")

    def test_stormborn_ignores_weather_and_multiple_storms_double_only_once(self):
        for leader in ("skone_storm", "skone_resilience"):
            game = fixture(["skone_heir"], ["knight"], leader)
            game.players[0].leader_blocked = True
            rolf = put(game, 0, "skone_sailor")
            enemy = put(game, 1, "skone_sailor")
            for keys, expected in (([], 4), (["rain"], 4), (["frost", "fog", "rain"], 4),
                                   (["storm"], 8), (["rain", "frost", "fog", "storm", "storm"], 8)):
                game.weather = [WeatherEffect(i % 2, key) for i, key in enumerate(keys)]
                self.assertEqual(game.strengths(0)[rolf.id], expected)
                self.assertEqual(game.strengths(1)[enemy.id], expected)
            game._clear_weather()
            self.assertEqual(game.strengths(0)[rolf.id], 4)

    def test_stormborn_stacks_with_card_leader_and_unit_row_boosts(self):
        for source in ("card", "leader", "unit"):
            game = fixture(["horn", "skone_heir"], ["knight"], "skone_horn")
            rolf = put(game, 0, "skone_sailor")
            if source == "card":
                game = play(game, 0, "horn", Row.SIEGE)
            elif source == "leader":
                game = self.leader(game, Row.SIEGE)
            else:
                put(game, 0, "skone_bard")
            game.weather = [WeatherEffect(1, "storm"), WeatherEffect(1, "rain")]
            self.assertEqual(game.strengths(0)[rolf.id], 16)
            # Прилив сил входит в силу, удваиваемую Штормом и усилением ряда.
            put(game, 0, "siege_expert")
            self.assertEqual(game.strengths(0)[rolf.id], 20)
            game._clear_weather()
            self.assertEqual(game.strengths(0)[rolf.id], 10)

    def test_stormborn_can_be_destroyed_by_scorch(self):
        game = fixture(["scorch"], ["knight"], "skone_storm")
        rolf = put(game, 1, "skone_sailor")
        weaker = put(game, 0, "scout")
        game.weather = [WeatherEffect(0, "storm")]
        game = play(game, 0, "scorch")
        self.assertIn(rolf.id, game.scorched)
        self.assertNotIn(weaker.id, game.scorched)

    def test_yara_and_harald_are_stormborn_on_ranged_and_melee_lines(self):
        self.assertEqual(CATALOG["ranger"].name, "Воительница Яра")
        self.assertEqual(CATALOG["young_berserker"].name, "Воительница Сконе")
        self.assertEqual(CATALOG["skone_raider"].name, "Торстен")
        self.assertEqual(CATALOG["young_berserker"].transform_to, "young_bear")
        game = fixture(["skone_heir"], ["knight"], "skone_storm")
        cards = [put(game, 0, key) for key in ("ranger", "skone_jarl", "skone_sailor")]
        for card in cards:
            self.assertIn("stormborn", CATALOG[card.key].abilities)
        game.weather = [WeatherEffect(1, key) for key in ("frost", "fog", "rain")]
        self.assertEqual([game.strengths(0)[c.id] for c in cards], [6, 4, 4])
        game.weather.append(WeatherEffect(1, "storm"))
        self.assertEqual([game.strengths(0)[c.id] for c in cards], [12, 8, 8])
        game.players[0].leader_horn.update(Row)
        self.assertEqual([game.strengths(0)[c.id] for c in cards], [24, 16, 16])

    def test_chaos_returns_all_discards_including_heroes_and_specials(self):
        game = fixture(["skone_heir"], ["knight"], "skone_chaos")
        expected = []
        for side, player in enumerate(game.players):
            player.deck = [game._new_card("skone_lightship")]
            player.discard = [game._new_card(key) for key in ("scorch", "druid", "young_bear", "rain")]
            expected.append({c.id for c in player.deck + player.discard})
            put(game, side, "skone_heir")
        game = self.leader(game)
        for side, player in enumerate(game.players):
            self.assertEqual({c.id for c in player.deck}, expected[side])
            self.assertEqual(player.discard, [])
            self.assertEqual(len(player.board), 1)

    def test_third_round_returns_two_ordinary_units_not_heroes_or_specials(self):
        game = fixture(["skone_heir"], ["knight"], "skone_storm")
        game.players[0].discard = [game._new_card(key) for key in ("druid", "storm", "horn", "skone_raider", "ranger")]
        game = self.third_round(game)
        self.assertEqual(game.round_number, 3)
        self.assertEqual(len(game.players[0].board), 2)
        self.assertTrue(all(not CATALOG[c.card.key].hero and CATALOG[c.card.key].kind == "unit" for c in game.players[0].board))
        self.assertTrue({"druid", "storm", "horn"}.issubset({c.key for c in game.players[0].discard}))
        self.assertEqual(len(game.players[1].board), 0)

    def test_third_round_replays_muster_and_medic_and_restores_starter(self):
        game = fixture(["skone_heir"], ["knight"], "skone_storm")
        game.round_number = 2
        game.players[0].lives, game.players[1].lives = 2, 1
        put(game, 1, "knight")  # Соперник начинает третий раунд.
        # Выберем воспроизводимый seed, где лекарь и корабль входят в двойку.
        game.players[0].discard = [game._new_card(key) for key in ("skone_medic", "skone_lightship", "ranger")]
        game.rng = random.Random(1)  # sample([0,1,2],2) -> [0,2]
        game.players[0].deck = [game._new_card("skone_lightship") for _ in range(2)]
        game.players[0].passed = game.players[1].passed = True
        game._end_round()
        self.assertEqual(game.round_starter, 1)
        self.assertEqual(game.turn, 0)
        self.assertEqual(game.view(0)["pending"]["actor"], 0)
        with self.assertRaises(RuleError):
            game.act(0, {"type": "pass"}, game.version)
        target = next(c for c in game.players[0].discard if c.key == "skone_lightship")
        game = game.act(0, {"type": "choose", "card_id": target.id, "row": "ranged"}, game.version)
        self.assertEqual(sum(c.card.key == "skone_lightship" for c in game.players[0].board), 3)
        self.assertFalse(game.pending)
        self.assertEqual(game.turn, 1)
        self.assertIsNone(game.round_resume_turn)

    def test_both_skone_resolve_medics_for_correct_owners_without_losing_turn(self):
        game = fixture(["skone_heir"], ["skone_heir"], "skone_storm", "skone_rage")
        game.round_number = 2
        game.players[0].lives, game.players[1].lives = 1, 2
        put(game, 0, "skone_heir")
        # Три обычных отряда: лекарь + 2 запасных. Seed выбирает обоих лекарей.
        for player in game.players:
            player.discard = [game._new_card(k) for k in ("skone_medic", "ranger", "skone_bard")]
            player.passed = True
        game.rng = random.Random(2)
        game._end_round()
        actors = []
        while game.pending:
            actor = game.turn
            actors.append(actor)
            move = next(m for m in game.legal_moves(actor) if m["type"] == "choose")
            game = game.act(actor, move, game.version)
        self.assertEqual(actors, [0, 1])
        self.assertEqual(game.turn, game.round_starter)
        self.assertEqual([len(p.board) for p in game.players], [3, 3])

    def test_resurrection_with_empty_or_single_discard_and_no_hands(self):
        for keys in ([], ["ranger"]):
            game = fixture([], ["knight"], "skone_resilience")
            game.players[0].leader_used = True
            game.players[0].discard = [game._new_card(k) for k in keys]
            game = self.third_round(game)
            # В сброс также уходит отряд со стола второго раунда.
            self.assertEqual(len(game.players[0].board), min(2, len(keys) + 1))
            self.assertTrue(game.players[0].passed)
            self.assertEqual(game.turn, 1)

    def test_nullifier_does_not_cancel_faction_resurrection(self):
        game = fixture(["skone_heir"], ["shiron_eck"], "skone_resilience", "shiron_nullify")
        game.players[0].leader_blocked = True
        game.players[0].discard = [game._new_card("ranger")]
        game = self.third_round(game)
        self.assertEqual(len(game.players[0].board), 2)

    def test_second_round_does_not_resurrect_and_skone_gets_no_victory_draw(self):
        game = fixture(["skone_heir"], ["knight"], "skone_storm")
        game.players[0].deck = [game._new_card("ranger")]
        game.players[0].discard = [game._new_card("skone_raider")]
        put(game, 0, "skone_heir")
        game.players[0].passed = game.players[1].passed = True
        game._end_round()
        self.assertEqual(game.round_number, 2)
        self.assertFalse(game.players[0].board)
        self.assertEqual(len(game.players[0].deck), 1)

    def test_avenger_summons_noncollectible_hero_on_scorch_or_round_end(self):
        game = fixture(["scorch"], ["knight"], "skone_storm")
        raven = put(game, 0, "skone_rooster")
        game = play(game, 0, "scorch")
        self.assertIn(raven.id, game.scorched)
        self.assertEqual(game.players[0].board[0].card.key, "skone_ancestor")
        game = fixture(["skone_heir"], ["knight"], "skone_storm")
        put(game, 0, "skone_rooster")
        game.players[0].passed = game.players[1].passed = True
        game._end_round()
        self.assertEqual(game.players[0].board[0].card.key, "skone_ancestor")

    def test_one_hundred_matches_with_all_factions_and_card_conservation(self):
        presets = {"burgundy": STARTER_DECK, "skone": SKONE_DECK, "shiron": SHIRON_DECK}
        keys = list(LEADERS)
        for seed in range(100):
            rng = random.Random(seed)
            leaders = ["skone_" + ("resilience", "storm", "horn", "rage", "chaos")[seed % 5], rng.choice(keys)]
            decks = [list(presets[LEADERS[key]["faction"]]) for key in leaders]
            game = Game.create(["A", "B"], decks, leaders, seed)
            original = {c.id for p in game.players for c in p.deck + p.hand}
            for side in (0, 1):
                game = game.act(side, {"type": "mulligan", "card_ids": []}, game.version)
            for _ in range(300):
                if game.phase == "finished":
                    break
                moves = [m for m in game.legal_moves(game.turn) if m["type"] != "concede"]
                choices = [m for m in moves if m["type"] != "pass"]
                game = game.act(game.turn, rng.choice(choices if choices and rng.random() > .12 else moves), game.version)
                ids = [c.id for p in game.players for c in p.hand + p.deck + p.discard]
                ids += [c.card.id for p in game.players for c in p.board + p.specials]
                ids += [w.card.id for w in game.weather if w.card]
                self.assertEqual(len(ids), len(set(ids)), seed)
                self.assertTrue(original.issubset(ids), seed)
            self.assertEqual(game.phase, "finished", seed)
            self.assertLessEqual(len(game.history), 3)


if __name__ == "__main__":
    unittest.main()
