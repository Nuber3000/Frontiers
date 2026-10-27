"""Пример успешного и отклонённого выкладывания обычного отряда."""

from frontiers.cards import CombatRow, UnitCard, row_strength
from frontiers.player import PlayerState


def main() -> None:
    player = PlayerState(
        hand=[
            UnitCard(name="Пехотинец", base_strength=5, row=CombatRow.MELEE),
            UnitCard(name="Лучник", base_strength=4, row=CombatRow.RANGED),
        ]
    )
    print("В начале: в руке", len(player.hand), "на поле", len(player.board))

    try:
        player.play_unit(hand_index=1, row=CombatRow.MELEE)
    except ValueError as error:
        print("Ход отклонён:", error)

    print("После ошибки: в руке", len(player.hand), "на поле", len(player.board))

    card = player.play_unit(hand_index=1, row=CombatRow.RANGED)
    print("Выложен отряд:", card.name)
    print("После хода: в руке", len(player.hand), "на поле", len(player.board))
    print("Сила дальнего боя:", row_strength(player.board, CombatRow.RANGED))


if __name__ == "__main__":
    main()
