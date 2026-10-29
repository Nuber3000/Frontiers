"""Авторский набор Империи Широн. Референсы определяют роли, но не имена и рисунки."""

from frontiers.cards import CombatRow as Row
from frontiers.models import CardDefinition

SHIRON_CARDS = [
    CardDefinition("shiron_siege_medic", "Обозный лекарь", strength=0, rows=(Row.SIEGE,),
                   abilities=("medic",), copies=1, faction="shiron"),
    CardDefinition("shiron_archer_medic", "Санитар Чёрной хоругви", strength=1, rows=(Row.RANGED,),
                   abilities=("medic",), copies=2, faction="shiron"),
    CardDefinition("shiron_eck", "Рупрехт фон Экк", strength=2, rows=(Row.MELEE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_riders", "Всадники Вороньего крыла", strength=2, rows=(Row.MELEE,),
                   abilities=("bond",), copies=3, group="shiron_riders", faction="shiron"),
    CardDefinition("shiron_marksman", "Курт, стрелок гарнизона", strength=2, rows=(Row.RANGED,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_pyromancer", "Освальд, придворный пиромант", strength=2, rows=(Row.RANGED,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_viscount", "Виконт Рейнхард", strength=3, rows=(Row.MELEE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_guard", "Когорта Обсидиана", strength=3, rows=(Row.MELEE,),
                   abilities=("bond",), copies=4, group="shiron_guard", faction="shiron"),
    CardDefinition("shiron_cadet", "Кадет Вальтер", strength=3, rows=(Row.RANGED,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_mangonel", "Старая камнемётная машина", strength=3, rows=(Row.SIEGE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_warden", "Страж Ночной башни", strength=4, rows=(Row.MELEE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_spy", "Каспар, тайный советник", strength=4, rows=(Row.MELEE,),
                   abilities=("spy",), copies=1, faction="shiron"),
    CardDefinition("shiron_fire_advisor", "Советник Фалькен", strength=4, rows=(Row.RANGED,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_sorceress", "Леония, придворная чародейка", strength=4, rows=(Row.RANGED,),
                   abilities=("horn",), copies=1, faction="shiron"),
    CardDefinition("shiron_envoys", "Молодые легаты", strength=5, rows=(Row.MELEE,),
                   abilities=("bond",), copies=2, group="shiron_envoys", faction="shiron"),
    CardDefinition("shiron_captain", "Капитан Чёрной стражи", strength=5, rows=(Row.RANGED,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_scorpion", "Алхимический скорпион", strength=5, rows=(Row.SIEGE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_knight", "Рыцарь Ястребиного ордена", strength=6, rows=(Row.MELEE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_ruby", "Аурелия, рубиновая ведьма", strength=6, rows=(Row.RANGED,),
                   abilities=("medic",), copies=1, faction="shiron"),
    CardDefinition("shiron_amber", "Магда, хранительница янтаря", strength=6, rows=(Row.RANGED,),
                   abilities=("medic",), copies=1, faction="shiron"),
    CardDefinition("shiron_pioneer", "Имперский сапёр", strength=6, rows=(Row.SIEGE,),
                   abilities=(), copies=1, faction="shiron"),
    CardDefinition("shiron_ambassador", "Герман фон Вальд", strength=7, rows=(Row.MELEE,),
                   abilities=("spy",), copies=1, faction="shiron"),
    CardDefinition("shiron_chancellor", "Канцлер Дитрих", strength=9, rows=(Row.MELEE,),
                   abilities=("spy",), copies=1, faction="shiron"),
    CardDefinition("shiron_archers", "Арбалетчики Чёрной хоругви", strength=10, rows=(Row.RANGED,),
                   abilities=(), copies=2, faction="shiron"),
    CardDefinition("shiron_grand_scorpion", "Большой алхимический скорпион", strength=10, rows=(Row.SIEGE,),
                   abilities=(), copies=2, faction="shiron"),
    CardDefinition("shiron_spy_hero", "Северин, тень Императора", strength=0, rows=(Row.MELEE,),
                   abilities=("spy",), copies=1, hero=True, faction="shiron"),
    CardDefinition("shiron_executioner", "Бруно, императорский палач", strength=10, rows=(Row.MELEE,),
                   abilities=(), copies=1, hero=True, faction="shiron"),
    CardDefinition("shiron_marshal", "Фельдмаршал Готфрид", strength=10, rows=(Row.MELEE,),
                   abilities=("medic",), copies=1, hero=True, faction="shiron"),
    CardDefinition("shiron_regent", "Регент Максимилиан", strength=10, rows=(Row.RANGED,),
                   abilities=(), copies=1, hero=True, faction="shiron"),
    CardDefinition("shiron_duke", "Герцог Людвиг фон Тироль", strength=10, rows=(Row.SIEGE,),
                   abilities=(), copies=1, hero=True, faction="shiron"),
]

SHIRON_DECK = (
    ["shiron_riders"] * 3 + ["shiron_guard"] * 4 + ["shiron_envoys"] * 2
    + ["shiron_archers"] * 2 + ["shiron_archer_medic"] * 2
    + ["shiron_siege_medic", "shiron_spy", "shiron_ambassador", "shiron_chancellor"]
    + ["shiron_executioner", "shiron_marshal", "shiron_regent", "shiron_duke"]
    + ["shiron_pioneer", "shiron_scorpion"]
    + ["shiron_spy_hero", "shiron_amber", "shiron_ruby", "shiron_sorceress"]
    + ["shiron_grand_scorpion"] * 2
    + ["horn", "horn", "decoy", "decoy", "clear", "scorch"]
)

