"""Удул Сурэг: орда, следующая за шаманом Гауром сквозь миры."""

from frontiers.cards import CombatRow as Row
from frontiers.models import CardDefinition


SOUL_LIMIT = 3


def unit(key, name, strength, row, *, copies=1, abilities=(), hero=False):
    key = "udul_" + key
    return CardDefinition(key, name, strength=strength, rows=(row,),
                          abilities=abilities, hero=hero,
                          copies=copies, faction="udul",
                          group=key if "bond" in abilities or "muster" in abilities else "")


UDUL_CARDS = [
    unit("mauler", "Крушитель миров", 6, Row.MELEE, copies=3, abilities=("bond",)),
    unit("spears", "Копейщики Чёрной тропы", 5, Row.MELEE, copies=3, abilities=("bond",)),
    unit("horde", "Рубаки Бесчисленной орды", 4, Row.MELEE, copies=4, abilities=("muster",)),
    unit("hunters", "Охотники Пепельного клана", 5, Row.RANGED, copies=3, abilities=("bond",)),
    unit("healer", "Шаманка костяного круга", 3, Row.RANGED, copies=2, abilities=("medic",)),
    unit("drummer", "Барабанщик похода", 2, Row.MELEE, copies=2, abilities=("morale",)),
    unit("engine", "Костяной камнемёт", 7, Row.SIEGE, copies=3, abilities=("bond",)),
    unit("executioner", "Ургат, палач орды", 7, Row.MELEE, abilities=("scorch_melee",)),
    unit("hero_warlord", "Громар, покоритель миров", 12, Row.MELEE, hero=True),
    unit("hero_huntress", "Шарга, копьё пустошей", 10, Row.RANGED, abilities=("scorch_ranged",), hero=True),
    unit("hero_shaman", "Морга, голос прародителей", 10, Row.RANGED, abilities=("medic",), hero=True),
    unit("hero_scout", "Таруг, идущий сквозь миры", 12, Row.MELEE, abilities=("scorch_melee",), hero=True),
    CardDefinition("udul_portal", "Портал", kind="special", copies=3, faction="udul",
                   description="Призывает из вашей колоды два случайных отряда или героя прямо на поле. Их способности срабатывают."),
]

UDUL_DECK = (
    ["udul_mauler"] * 3 + ["udul_spears"] * 3 + ["udul_horde"] * 4
    + ["udul_hunters"] * 3 + ["udul_healer"] * 2 + ["udul_drummer"] * 2
    + ["udul_engine"] * 3 + ["udul_executioner", "udul_hero_warlord",
       "udul_hero_huntress", "udul_hero_shaman", "udul_hero_scout"]
    + ["scorch"] * 4 + ["udul_portal"] * 3 + ["horn", "frost", "clear"]
)

UDUL_LEADERS = {
    "udul_rite": {"name": "Обряд", "description": "Выберите любую погодную карту из своей колоды и немедленно сыграйте её."},
    "udul_sacrifice": {"name": "Жертвоприношение", "description": "Выберите две карты из своей руки и сбросьте их в отбой, затем возьмите одну карту по выбору из своей колоды."},
    "udul_necromancy": {"name": "Некромантия", "description": "Верните в руку до двух выбранных обычных отрядов из своего отбоя. Герои недоступны."},
    "udul_spirit": {"name": "Боевой дух", "description": "Возьмите командный рог из своей колоды и немедленно установите на выбранную свободную линию."},
    "udul_souls": {"name": "Собиратель душ", "description": "Казнь любого игрока даёт одну душу за уничтоженную карту, максимум три. Потратьте три души, чтобы взять карту по выбору из своей колоды. Души сразу начинают копиться заново и сохраняются между раундами. Способность можно использовать один раз за раунд."},
}
for key, leader in UDUL_LEADERS.items():
    leader.update(faction="udul", portrait=f"leader_{key}.webp")

UDUL_FACTION = {
    "name": "Удул Сурэг", "leader": "Гаур", "playable": True,
    "description": "Бесчисленная орда орков из перенаселённого мира. Гаур, шаман четвёртого поколения, ведёт её через порталы к новым войнам.",
    "ability": "Способность лидера восстанавливается каждый раунд. Один случайный собственный отряд, включая героя, остаётся на следующий раунд. Все шпионы, попавшие на вашу сторону, немедленно казнятся. Удул Сурэг не может брать, разыгрывать или выбирать шпионов для своих способностей.",
    "emblem": "◉", "default_leader": "udul_rite", "card_limits": {"decoy": 0, "scorch": 4},
    "forbidden_abilities": ["spy"],
}
