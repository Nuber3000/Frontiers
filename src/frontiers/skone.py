"""Кланы Сконе: авторские отряды, герои и готовая колода."""

from frontiers.cards import CombatRow as Row
from frontiers.models import CardDefinition


def unit(key, name, strength, row, **options):
    rows = row if isinstance(row, tuple) else (row,)
    return CardDefinition(key, name, strength=strength, rows=rows, faction="skone", **options)


SKONE_UNITS = [
    unit("skone_rooster", "Ворон последней зари", 0, Row.MELEE,
         abilities=("avenger",), summon_to="skone_ancestor"),
    unit("skone_ancestor", "Эйнар, страж предков", 11, Row.MELEE,
         hero=True, collectible=False),
    unit("skone_medic", "Астрид, целительница клана", 2, Row.MELEE, abilities=("medic",)),
    unit("skone_bard", "Сверре, голос саг", 2, Row.SIEGE, abilities=("horn",)),
    unit("skone_heir", "Лейф, наследник ярла", 4, Row.MELEE),
    unit("skone_raider", "Торстен", 4, Row.MELEE),
    unit("skone_jarl", "Ярл Харальд", 4, Row.MELEE, abilities=("stormborn",)),
    unit("skone_sailor", "Рольф Чёрный Парус", 4, Row.SIEGE, abilities=("stormborn",)),
    unit("skone_smith", "Хакон, кузнец клана", 4, Row.MELEE),
    unit("skone_skald", "Браги, скальд фьордов", 4, Row.MELEE, abilities=("morale",)),
    unit("skone_shieldmaidens", "Щитоносицы Ясеневого клана", 4, Row.MELEE,
         abilities=("bond",), group="skone_shieldmaidens", copies=3),
    unit("skone_lightship", "Дозорный драккар", 4, Row.RANGED,
         abilities=("muster",), group="skone_lightship", copies=3),
    unit("skone_redaxe", "Бьёрн Красный Топор", 6, Row.MELEE),
    unit("skone_ghost", "Ивар, слышащий предков", 6, (Row.MELEE, Row.RANGED),
         abilities=("berserker",), transform_to="skone_bear"),
    unit("skone_warship", "Боевой драккар", 6, Row.SIEGE,
         abilities=("bond",), group="skone_warship", copies=3),
    unit("skone_clan", "Воины Каменного Волка", 6, Row.MELEE,
         abilities=("bond",), group="skone_clan", copies=3),
    unit("skone_pirate", "Кьелль, гроза побережья", 6, Row.RANGED,
         abilities=("scorch_melee",)),
    unit("skone_bear", "Урс, хранитель чащи", 12, (Row.MELEE, Row.RANGED),
         abilities=("morale",), collectible=False),
    unit("skone_shieldhero", "Сигрун, щит Сконе", 10, Row.MELEE, hero=True,
         abilities=("muster",), group="skone_shieldmaidens"),
    unit("skone_hero_archer", "Рагнар Грозовая Стрела", 10, Row.RANGED, hero=True),
]

SKONE_DECK = (
    ["young_berserker"] * 3 + ["berserker", "druid", "ranger"]
    + ["skone_shieldmaidens"] * 3 + ["skone_lightship"] * 3
    + ["skone_warship"] * 3 + ["skone_clan"] * 3
    + ["skone_medic", "skone_bard", "skone_rooster", "skone_ghost",
       "skone_pirate", "skone_shieldhero", "skone_hero_archer"]
    + ["horn", "mushroom", "mushroom", "storm", "clear", "scorch", "decoy"]
)
