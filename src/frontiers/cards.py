"""Обычные отряды и подсчёт их базовой силы."""

from dataclasses import dataclass
from enum import Enum


class CombatRow(Enum):
    """Три боевые линии, на которых можно размещать отряды."""

    MELEE = "melee"
    RANGED = "ranged"
    SIEGE = "siege"


@dataclass(frozen=True)
class UnitCard:
    """Описание обычной карты отряда с неизменяемой базовой силой."""

    name: str
    base_strength: int
    row: CombatRow


def row_strength(cards: list[UnitCard], row: CombatRow) -> int:
    """Суммирует базовую силу переданных отрядов выбранной линии."""
    return sum(card.base_strength for card in cards if card.row == row)
