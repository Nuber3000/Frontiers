"""Stable locations of bundled artwork, shared by the catalog and art tooling."""

from pathlib import PurePosixPath


_SKONE_ART = {"berserker", "young_berserker", "war_bear", "young_bear", "ranger", "druid", "mushroom", "ting", "valknut"}
_COMMON_ART = {"card-art", "decoy", "rain", "scorch", "horn", "wood", "favicon"}


def image_path(filename: str) -> str:
    """Return a path relative to static; names and artwork bytes stay unchanged."""
    name = PurePosixPath(filename).name
    stem = PurePosixPath(name).stem
    key = stem.removeprefix("leader_")
    faction = next((group for group in ("shiron", "skone", "ellifarn", "udul") if key.startswith(group + "_")), None)
    if faction is None:
        faction = "common" if stem in _COMMON_ART else "skone" if stem in _SKONE_ART else "burgundy"
    return f"images/{faction}/{name}"
