"""
Подсистема склонения (T002+).

T002: ФИО через `petrovich` (`PetrovichInflector`, `Fio`, `NamePart`,
`Initials`) + автоопределение пола (`detect_gender`). T003: должности через
`pymorphy3` (`PymorphyInflector`, `Position`) — за тем же портом
`Declinable`, общий `MorphAnalyzer` из `morph.py`. T016 фаза B: звания
(`RankInflector`, `Rank`) — голова склоняется, генитивный хвост замирает.
"""

from __future__ import annotations

from dyak.inflection.fio import Fio, Initials, NamePart
from dyak.inflection.gender import (
    GenderResolution,
    GenderSource,
    detect_gender,
    parse_gender,
    resolve_gender,
)
from dyak.inflection.petrovich_fio import PetrovichInflector
from dyak.inflection.ports import Declinable
from dyak.inflection.pymorphy_phrase import Position, PymorphyInflector
from dyak.inflection.rank import Rank, RankInflector

__all__ = [
    'Declinable',
    'Fio',
    'GenderResolution',
    'GenderSource',
    'Initials',
    'NamePart',
    'PetrovichInflector',
    'Position',
    'PymorphyInflector',
    'Rank',
    'RankInflector',
    'detect_gender',
    'parse_gender',
    'resolve_gender',
]
