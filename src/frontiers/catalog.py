"""Авторский набор Бургундии, специальные карты и готовые колоды."""

from collections import Counter

from frontiers.cards import CombatRow as Row
from frontiers.models import CardDefinition
from frontiers.shiron import SHIRON_CARDS, SHIRON_DECK


ROWS = tuple(Row)
ABILITY_NAMES = {
    "spy": "Шпион", "medic": "Лекарь", "bond": "Сплочённость",
    "morale": "Прилив сил", "muster": "Призыв", "horn": "Штандарт",
    "mushroom": "Мухомор", "berserker": "Берсерк", "avenger": "Наследие",
    "scorch_melee": "Казнь: ближний бой", "scorch_ranged": "Казнь: дальний бой",
    "scorch_siege": "Казнь: осада",
}


def unit(key, name, strength, row, *, abilities=(), hero=False, copies=1,
         group="", transform_to="", summon_to="", collectible=True):
    rows = row if isinstance(row, tuple) else (row,)
    return CardDefinition(key, name, strength=strength, rows=rows,
                          abilities=abilities, hero=hero, copies=copies,
                          group=group, transform_to=transform_to,
                          summon_to=summon_to, collectible=collectible)


_CARDS = [
    unit("blue_guard", "Лазурная стража", 4, Row.MELEE,
         abilities=("bond",), group="blue_guard", copies=3),
    unit("crossbow", "Пограничные арбалетчики", 5, Row.RANGED,
         abilities=("bond",), group="crossbow", copies=3),
    unit("catapult", "Королевская баллиста", 8, Row.SIEGE,
         abilities=("bond",), group="catapult", copies=2),
    unit("siege_expert", "Мастер орудий", 1, Row.SIEGE,
         abilities=("morale",), copies=3),
    unit("spy_scribe", "Королевский писарь", 4, Row.MELEE, abilities=("spy",)),
    unit("spy_port", "Портовый осведомитель", 5, Row.MELEE, abilities=("spy",)),
    unit("spy_cartographer", "Седой картограф", 1, Row.SIEGE, abilities=("spy",)),
    unit("field_medic", "Полковой хирург", 5, Row.SIEGE, abilities=("medic",)),
    unit("trebuchet", "Требушет", 6, Row.SIEGE, copies=2),
    unit("ballista", "Полевое орудие", 6, Row.SIEGE, copies=2),
    unit("siege_tower", "Осадная башня", 6, Row.SIEGE),
    unit("knight", "Бургундский рыцарь", 5, Row.MELEE),
    unit("veteran", "Ветеран королевской гвардии", 6, Row.MELEE),
    unit("infantry", "Городской ополченец", 1, Row.MELEE,
         abilities=("bond",), group="infantry", copies=3),
    unit("scout", "Дозорный", 4, Row.RANGED, copies=2),
    unit("ranger", "Лесной стрелок", 6, Row.RANGED),
    unit("regent", "Аделина, щит короны", 10, Row.MELEE, hero=True),
    unit("champion", "Ориан, клинок рубежей", 15, Row.MELEE, hero=True),
    unit("archivist", "Этьен, хранитель клятв", 10, Row.RANGED, hero=True),
    unit("healer_hero", "Мирель, хранительница жизни", 7, Row.RANGED,
         abilities=("medic",), hero=True),
    unit("spy_hero", "Безымянный посол", 0, Row.MELEE,
         abilities=("spy",), hero=True),
    unit("banner_bearer", "Знаменосец Франциска", 2, Row.MELEE,
         abilities=("horn",)),
    unit("herald", "Габриэль фон Ард", 6, (Row.MELEE, Row.RANGED),
         abilities=("morale",)),
    unit("fire_walker", "Пламенный странник", 7, Row.MELEE,
         abilities=("scorch_melee",)),
    unit("fire_hunter", "Огненный ловчий", 7, Row.RANGED,
         abilities=("scorch_ranged",)),
    unit("demolitionist", "Королевский подрывник", 8, Row.SIEGE,
         abilities=("scorch_siege",)),
    unit("road_company", "Дорожная дружина", 4, Row.MELEE,
         abilities=("muster",), group="road_company", copies=3),
    unit("company_captain", "Капитан дорожной дружины", 10, Row.MELEE,
         abilities=("muster",), hero=True, group="road_company"),
    unit("berserker", "Бешеный ратник", 4, Row.MELEE,
         abilities=("berserker",), transform_to="war_bear"),
    unit("young_berserker", "Лесной берсерк", 2, Row.RANGED,
         abilities=("berserker",), transform_to="young_bear", copies=3),
    unit("war_bear", "Великий медведь", 14, Row.MELEE,
         abilities=("morale",), collectible=False),
    unit("young_bear", "Лесной медведь", 8, Row.RANGED,
         abilities=("bond",), group="young_bear", collectible=False),
    unit("druid", "Альбан, лесной мудрец", 8, Row.RANGED,
         abilities=("mushroom",), hero=True),
    unit("watchman", "Последний дозорный", 0, Row.MELEE,
         abilities=("avenger",), summon_to="avenger"),
    unit("avenger", "Клятва дозора", 8, Row.MELEE, collectible=False),
]

for key, name, description in [
    ("frost", "Мороз", "Сила рукопашных отрядов обоих игроков становится 1."),
    ("fog", "Туман", "Сила дальнобойных отрядов обоих игроков становится 1."),
    ("rain", "Ливень", "Сила осадных отрядов обоих игроков становится 1."),
    ("storm", "Шторм", "Сила дальнобойных и осадных отрядов обоих игроков становится 1."),
    ("clear", "Ясное небо", "Снимает все погодные эффекты."),
    ("scorch", "Казнь", "Уничтожает самую сильную карту или карты на всём поле боя."),
    ("horn", "Штандарт", "Удваивает силу ваших отрядов в ряду, кроме героев."),
    ("decoy", "Чучело", "Заменяет дружественный отряд и возвращает его в руку. Герои недоступны."),
    ("mushroom", "Мухомор", "Обращает текущих Берсерков выбранного вашего ряда во вторую форму, затем уходит в сброс. Штандарт не мешает применению."),
]:
    kind = "weather" if key in {"frost", "fog", "rain", "storm", "clear"} else "special"
    _CARDS.append(CardDefinition(key, name, kind=kind, copies=3,
                                 description=description, faction="skone" if key in {"storm", "mushroom"} else "neutral"))

_CARDS.extend(SHIRON_CARDS)

CATALOG = {card.key: card for card in _CARDS}

# Карты сохранены для будущей Сконе, но недоступны в колодах Бургундии.
SKONE_CARDS = frozenset({
    "berserker", "young_berserker", "war_bear", "young_bear", "mushroom", "ranger", "druid", "storm",
})
FACTIONS = {
    "burgundy": {"name": "Королевство Бургундия", "leader": "Франциск II Мудрый", "playable": True},
    "skone": {
        "name": "Сконе", "leader": "Конунг Ульфрик Синезубый", "playable": False,
        "description": "Земля викингов, где правят несколько ярлов и великий конунг.",
    },
}

FACTIONS["burgundy"].update(ability="После каждого выигранного раунда возьмите карту из своей колоды.", emblem="⚜", default_leader="sun")
FACTIONS["shiron"] = {
    "name": "Империя Широн", "leader": "Император Альбрехт Тироль", "playable": True,
    "ability": "При равной силе побеждает в раунде. Если оба игрока выбрали Широн, раунд заканчивается ничьей.",
    "emblem": "✹", "default_leader": "shiron_hand",
}

LEADERS = {
    "sun": {"name": "Солнцеликий", "description": "Отменяет Мороз, Ливень, Туман и Шторм."},
    "mortar": {"name": "Королевская мортира", "description": "Казнит сильнейшие дальнобойные отряды противника, если сила ряда не меньше 10."},
    "war": {"name": "Бог войны", "description": "Казнит сильнейшие осадные отряды противника, если сила ряда не меньше 10."},
    "academy": {"name": "Военная академия", "description": "Удваивает силу ваших осадных отрядов, кроме героев. Не складывается со штандартом."},
    "fog": {"name": "Туман войны", "description": "Накладывает Туман на дальний бой обеих сторон."},
}

for _leader in LEADERS.values():
    _leader["faction"] = "burgundy"
LEADERS.update({
    "shiron_hand": {"name": "Божья Длань", "description": "Воскрешает случайный обычный отряд из своего отбоя на его линию. Способность отряда срабатывает повторно."},
    "shiron_rain": {"name": "Торжество стихии", "description": "Накладывает Ливень на осадные линии обоих игроков."},
    "shiron_spy": {"name": "Шпионские игры", "description": "Показывает вам три случайные карты из руки противника или всю руку, если карт меньше трёх."},
    "shiron_nullify": {"name": "Натиск Империи", "description": "Пассивно запрещает использование способности вражеского лидера с начала матча.", "passive": True},
    "shiron_levy": {"name": "Посмертная повинность", "description": "Позволяет выбрать обычный отряд из отбоя соперника и взять его в руку. Герои недоступны."},
})
for _key, _leader in LEADERS.items():
    if _key.startswith("shiron_"):
        _leader.update(faction="shiron", portrait=f"leader_{_key}.png")

STARTER_DECK = (
    ["blue_guard"] * 3 + ["crossbow"] * 3 + ["catapult"] * 2
    + ["siege_expert"] * 2
    + ["spy_scribe", "spy_port", "spy_cartographer", "field_medic"]
    + ["trebuchet"] * 2 + ["ballista"] * 2
    + ["champion", "regent", "healer_hero", "banner_bearer"]
    + ["horn"] * 2 + ["decoy"] * 2 + ["clear", "scorch"]
)
DECKS = {
    "guard": {"name": "Королевская гвардия", "cards": STARTER_DECK, "faction": "burgundy"},
    "imperial": {"name": "Императорский легион", "cards": SHIRON_DECK, "faction": "shiron"},
}


def validate_deck(keys: list[str], leader: str) -> None:
    if leader not in LEADERS:
        raise ValueError("Неизвестная способность лидера.")
    if not isinstance(keys, list) or not 22 <= len(keys) <= 60:
        raise ValueError("Колода должна содержать от 22 до 60 карт.")
    counts = Counter(keys)
    for key, count in counts.items():
        card = CATALOG.get(key)
        if card is None or not card.collectible:
            raise ValueError("Колода содержит недоступную карту.")
        if key in SKONE_CARDS:
            raise ValueError(f"Карта «{card.name}» сохранена для будущей фракции Сконе.")
        if card.faction not in {"neutral", LEADERS[leader]["faction"]}:
            raise ValueError(f"Карта «{card.name}» недоступна выбранной фракции.")
        if count > card.copies:
            raise ValueError(f"Слишком много копий карты «{card.name}».")
    units = sum(CATALOG[key].kind == "unit" for key in keys)
    if units < 22:
        raise ValueError("В колоде должно быть не менее 22 отрядов.")
    if len(keys) - units > 10:
        raise ValueError("В колоде может быть не более 10 особых и погодных карт.")


def card_definition_view(card: CardDefinition) -> dict:
    return {
        "key": card.key, "name": card.name, "kind": card.kind,
        "base_strength": card.strength, "rows": [row.value for row in card.rows],
        "abilities": list(card.abilities), "hero": card.hero,
        "copies": card.copies, "collectible": card.collectible,
        "faction": "skone" if card.key in SKONE_CARDS else card.faction,
        "available": card.collectible and card.key not in SKONE_CARDS,
        "description": card.description,
        "transform_to": card.transform_to, "summon_to": card.summon_to,
    }


def catalog_view() -> dict:
    return {
        "faction": "Королевство Бургундия", "leader": "Франциск II Мудрый",
        "faction_ability": "После победы в раунде доберите одну карту.",
        "factions": FACTIONS,
        "cards": [card_definition_view(card) for card in CATALOG.values()],
        "leaders": LEADERS, "decks": DECKS, "ability_names": ABILITY_NAMES,
    }
