"""A legal active leader can be spent even when there are no useful targets."""

from copy import deepcopy
import unittest

from frontiers.cards import CombatRow as Row
from frontiers.catalog import LEADERS
from frontiers.engine import RuleError
from frontiers.models import PlacedCard
from test_engine import fixture, put


class LeaderNoEffectTests(unittest.TestCase):
    def test_every_active_leader_can_be_used_on_an_empty_field(self):
        for leader, definition in LEADERS.items():
            if definition.get("passive"):
                continue
            with self.subTest(leader=leader):
                game = fixture(["knight"], ["knight"], leader)
                if leader == "udul_souls":
                    game.players[0].souls = 3
                move = {"type": "leader"}
                if leader == "skone_horn":
                    move["row"] = "melee"
                self.assertIn(move, game.legal_moves(0))
                after = game.act(0, move, game.version)
                self.assertTrue(after.players[0].leader_used)
                self.assertFalse(game.players[0].leader_used)
                self.assertEqual(after.version, game.version + 1)
                self.assertEqual(after.turn, 1)
                self.assertFalse(after.pending or after.pending_levy)
                after.turn = 0
                self.assertFalse(any(m["type"] == "leader" for m in after.legal_moves(0)))
                with self.assertRaises(RuleError):
                    after.act(0, move, after.version)

    def test_logistics_without_agile_units_is_a_turn_and_not_a_pass(self):
        game = fixture(["ellifarn_captain"], ["knight"], "ellifarn_logistics")
        put(game, 0, "ellifarn_captain")
        board = deepcopy(game.players[0].board)
        after = game.act(0, {"type": "leader"}, game.version)
        self.assertEqual(after.players[0].board, board)
        self.assertEqual(after.players[0].hand, game.players[0].hand)
        self.assertEqual(after.turn, 1)
        self.assertFalse(after.players[0].passed)

    def test_occupied_boost_slot_spends_leader_without_extra_boost(self):
        for leader, rows in (("academy", [Row.SIEGE]), ("ellifarn_aim", [Row.RANGED]),
                             ("skone_horn", list(Row))):
            for row in rows:
                for existing in ("card", "leader"):
                    with self.subTest(leader=leader, row=row, existing=existing):
                        game = fixture(["knight"], ["knight"], leader)
                        unit = put(game, 0, "knight", row)
                        if existing == "card":
                            game.players[0].specials.append(PlacedCard(game._new_card("horn"), row))
                        else:
                            game.players[0].leader_horn.add(row)
                        original = deepcopy(game.players[0])
                        move = {"type": "leader"}
                        if leader == "skone_horn":
                            move["row"] = row.value
                        self.assertIn(move, game.legal_moves(0))
                        after = game.act(0, move, game.version)
                        self.assertTrue(after.players[0].leader_used)
                        self.assertEqual(after.players[0].specials, original.specials)
                        self.assertEqual(after.players[0].leader_horn, original.leader_horn)
                        self.assertEqual(after.strengths(0)[unit.id], 10)

    def test_empty_or_ineligible_discards_do_not_leave_a_pending_choice(self):
        for leader in ("shiron_hand", "shiron_levy"):
            for cards in ([], ["champion", "horn", "rain"]):
                with self.subTest(leader=leader, cards=cards):
                    game = fixture(["knight"], ["knight"], leader)
                    owner = 0 if leader == "shiron_hand" else 1
                    game.players[owner].discard = [game._new_card(key) for key in cards]
                    before = deepcopy(game.players[owner].discard)
                    after = game.act(0, {"type": "leader"}, game.version)
                    self.assertEqual(after.players[owner].discard, before)
                    self.assertFalse(after.pending or after.pending_levy)
                    self.assertEqual(after.turn, 1)
                    self.assertIn({"type": "pass"}, after.legal_moves(1))

    def test_used_blocked_passive_wrong_turn_and_passed_leaders_stay_unavailable(self):
        for reason in ("used", "blocked", "passive", "wrong_turn", "passed"):
            with self.subTest(reason=reason):
                game = fixture(["knight"], ["knight"], "skone_resilience" if reason == "passive" else "ellifarn_trade")
                if reason == "used":
                    game.players[0].leader_used = True
                elif reason == "blocked":
                    game.players[0].leader_blocked = True
                elif reason == "wrong_turn":
                    game.turn = 1
                elif reason == "passed":
                    game.players[0].passed = True
                self.assertNotIn({"type": "leader"}, game.legal_moves(0))
                with self.assertRaises(RuleError):
                    game.act(0, {"type": "leader"}, game.version)
