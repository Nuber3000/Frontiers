"""Проверки переноса карт и сохранности состояния при ошибочном ходе."""

import unittest

from frontiers.cards import CombatRow, UnitCard, row_strength
from frontiers.player import PlayerState


class PlayerStateTests(unittest.TestCase):
    def test_play_moves_selected_card_and_changes_row_strength(self) -> None:
        infantry = UnitCard("Infantry", 5, CombatRow.MELEE)
        archer = UnitCard("Archer", 4, CombatRow.RANGED)
        player = PlayerState(hand=[infantry, archer])

        played = player.play_unit(hand_index=1, row=CombatRow.RANGED)

        self.assertIs(played, archer)
        self.assertEqual(player.hand, [infantry])
        self.assertEqual(player.board, [archer])
        self.assertEqual(row_strength(player.board, CombatRow.RANGED), 4)
        self.assertEqual(row_strength(player.board, CombatRow.MELEE), 0)

    def test_wrong_row_leaves_hand_and_board_unchanged(self) -> None:
        archer = UnitCard("Archer", 4, CombatRow.RANGED)
        infantry = UnitCard("Infantry", 5, CombatRow.MELEE)
        player = PlayerState(hand=[archer], board=[infantry])

        with self.assertRaises(ValueError):
            player.play_unit(hand_index=0, row=CombatRow.SIEGE)

        self.assertEqual(player.hand, [archer])
        self.assertEqual(player.board, [infantry])

    def test_invalid_index_leaves_state_unchanged(self) -> None:
        infantry = UnitCard("Infantry", 5, CombatRow.MELEE)
        player = PlayerState(hand=[infantry])

        for index in (-1, 1, 10):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    player.play_unit(hand_index=index, row=CombatRow.MELEE)

                self.assertEqual(player.hand, [infantry])
                self.assertEqual(player.board, [])

    def test_identical_cards_are_selected_by_position(self) -> None:
        first = UnitCard("Infantry", 5, CombatRow.MELEE)
        second = UnitCard("Infantry", 5, CombatRow.MELEE)
        player = PlayerState(hand=[first, second])

        player.play_unit(hand_index=1, row=CombatRow.MELEE)

        self.assertEqual(len(player.hand), 1)
        self.assertEqual(len(player.board), 1)
        self.assertIs(player.hand[0], first)
        self.assertIs(player.board[0], second)

    def test_players_have_independent_hands_and_boards(self) -> None:
        first = PlayerState()
        second = PlayerState()
        first.hand.append(UnitCard("Infantry", 5, CombatRow.MELEE))

        self.assertEqual(second.hand, [])
        first.play_unit(hand_index=0, row=CombatRow.MELEE)

        self.assertEqual(len(first.board), 1)
        self.assertEqual(second.board, [])


if __name__ == "__main__":
    unittest.main()
