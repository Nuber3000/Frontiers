"""Отряды, герои и колода Союза Эллифарн."""

from frontiers.cards import CombatRow as Row
from frontiers.models import CardDefinition


def unit(key, name, strength, rows, *, copies=1, ability=None, hero=False):
    key = f"ellifarn_{key}"
    return CardDefinition(
        key, name, strength=strength, rows=rows if isinstance(rows, tuple) else (rows,),
        abilities=(ability,) if ability else (), copies=copies, hero=hero,
        group=key if ability in {"muster", "bond"} else "", faction="ellifarn",
    )


ELLIFARN_UNITS = [
    unit("healer", "Полевые лекари Лангинса", 0, Row.RANGED, copies=3, ability="medic"),
    unit("scout", "Дозорный Миринорма", 1, Row.RANGED, ability="medic"),
    unit("archers", "Стрелки Серебряной рощи", 2, (Row.RANGED, Row.MELEE), copies=3, ability="muster"),
    unit("sappers", "Сапёры Эмбера", 3, Row.MELEE, copies=3, ability="muster"),
    unit("shield", "Добровольцы Медного щита", 5, Row.MELEE, copies=5),
    unit("escort", "Караванный эскорт Лангинса", 5, Row.MELEE, copies=3, ability="muster"),
    unit("riders", "Всадники Миринорма", 5, (Row.MELEE, Row.RANGED), copies=2),
    unit("tracker", "Рысьи следопыты", 6, (Row.MELEE, Row.RANGED), copies=3),
    unit("marksman", "Лучница Янтарной долины", 4, (Row.RANGED, Row.MELEE)),
    unit("captain", "Бранн, капитан Эмбера", 6, Row.MELEE),
    unit("warden", "Варг, страж Великого Леса", 6, (Row.MELEE, Row.RANGED)),
    unit("engine", "Баллиста Эмбера", 6, Row.SIEGE, copies=2, ability="bond"),
    unit("outrider", "Дозорная Лангинса", 4, (Row.MELEE, Row.RANGED)),
    unit("fire", "Кирен, огнемётчик Лангинса", 8, Row.SIEGE, ability="scorch_siege"),
    unit("hero_ember", "Дорин Медный Молот", 10, Row.MELEE, ability="morale", hero=True),
    unit("hero_grove", "Лиара, голос Великого Леса", 10, Row.RANGED, ability="medic", hero=True),
    unit("hero_langins", "Марта, щит Лангинса", 10, Row.RANGED, hero=True),
    unit("hero_mirinorm", "Элери, стрела Миринорма", 10, Row.RANGED, hero=True),
]

ELLIFARN_DECK = (
    ["ellifarn_healer"] * 2 + ["ellifarn_archers"] * 3 + ["ellifarn_sappers"] * 3
    + ["ellifarn_shield"] * 3 + ["ellifarn_escort"] * 3 + ["ellifarn_riders"] * 2
    + ["ellifarn_tracker"] * 2 + ["ellifarn_engine"] * 2
    + ["ellifarn_warden", "ellifarn_marksman", "ellifarn_fire", "ellifarn_hero_ember",
       "ellifarn_hero_grove", "ellifarn_hero_mirinorm", "ellifarn_hero_langins"]
    + ["horn", "scorch", "decoy", "fog", "frost", "clear"]
)

ELLIFARN_LEADERS = {
    "ellifarn_trade": {"name": "Торговые привилегии", "description": "Возьмите одну карту из своей колоды."},
    "ellifarn_aim": {"name": "Эльфийская меткость", "description": "Ставит командный рог на вашу дальнобойную линию и удваивает силу обычных отрядов. Усиления ряда не складываются."},
    "ellifarn_fury": {"name": "Ярость Великого Леса", "description": "Уничтожает сильнейший обычный рукопашный отряд соперника. При равной силе уничтожает все такие отряды."},
    "ellifarn_logistics": {"name": "Логистика", "description": "Перемещает ваши обычные отряды с двумя доступными линиями туда, где их текущая сила выше. При равной силе отряд остаётся на месте."},
}
for key, leader in ELLIFARN_LEADERS.items():
    leader.update(faction="ellifarn", portrait=f"leader_{key}.webp")
