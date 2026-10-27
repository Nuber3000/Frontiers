"""Пример подсчёта силы обычных отрядов; названия и значения временные."""

from frontiers.cards import CombatRow, UnitCard, row_strength


def main() -> None:
    cards = [
        UnitCard(name="Пехотинец", base_strength=5, row=CombatRow.MELEE),
        UnitCard(name="Лучник", base_strength=4, row=CombatRow.RANGED),
        UnitCard(name="Арбалетчик", base_strength=6, row=CombatRow.RANGED),
    ]

    print("Ближний бой:", row_strength(cards, CombatRow.MELEE))
    print("Дальний бой:", row_strength(cards, CombatRow.RANGED))
    print("Осада:", row_strength(cards, CombatRow.SIEGE))


if __name__ == "__main__":
    main()
