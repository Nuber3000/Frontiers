"""Рука и поле одного игрока, выкладывание обычного отряда."""

from dataclasses import dataclass, field

from frontiers.cards import CombatRow, UnitCard


@dataclass
class PlayerState:
    """Текущее расположение карт на руке и стороне поля одного игрока."""

    hand: list[UnitCard] = field(default_factory=list)
    board: list[UnitCard] = field(default_factory=list)

    def play_unit(self, hand_index: int, row: CombatRow) -> UnitCard:
        """Переносит карту из руки на допустимую линию, отсчитывая индексы с нуля."""
        if hand_index < 0 or hand_index >= len(self.hand):
            raise ValueError("В руке нет карты с таким индексом.")

        card = self.hand[hand_index]
        if card.row != row:
            raise ValueError("Отряд нельзя выложить на выбранную линию.")

        self.hand.pop(hand_index)
        self.board.append(card)
        return card
