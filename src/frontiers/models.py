"""Данные полноценного матча. Эти классы не зависят от веб-сервера."""

from dataclasses import dataclass, field

from frontiers.cards import CombatRow


@dataclass(frozen=True)
class CardDefinition:
    key: str
    name: str
    kind: str = "unit"
    strength: int = 0
    rows: tuple[CombatRow, ...] = ()
    abilities: tuple[str, ...] = ()
    hero: bool = False
    group: str = ""
    transform_to: str = ""
    summon_to: str = ""
    copies: int = 1
    collectible: bool = True
    description: str = ""
    faction: str = "burgundy"


@dataclass
class CardInstance:
    id: str
    key: str


@dataclass
class PlacedCard:
    card: CardInstance
    row: CombatRow


@dataclass
class MatchPlayer:
    name: str
    leader: str
    deck: list[CardInstance] = field(default_factory=list)
    hand: list[CardInstance] = field(default_factory=list)
    discard: list[CardInstance] = field(default_factory=list)
    board: list[PlacedCard] = field(default_factory=list)
    specials: list[PlacedCard] = field(default_factory=list)
    lives: int = 2
    passed: bool = False
    mulligan_done: bool = False
    leader_used: bool = False
    leader_horn: set[CombatRow] = field(default_factory=set)
    leader_blocked: bool = False
    revealed: list[CardInstance] = field(default_factory=list)
