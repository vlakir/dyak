"""
Подсистема склонения (T002+).

T002: ФИО через `petrovich` (`PetrovichInflector`, `Fio`, `NamePart`,
`Initials`) + автоопределение пола (`detect_gender`). T003: должности через
`pymorphy3` (`PymorphyInflector`, `Position`) — за тем же портом
`Declinable`, общий `MorphAnalyzer` из `morph.py`.
"""

from __future__ import annotations

from dyak.inflection.fio import Fio, Initials, NamePart
from dyak.inflection.gender import detect_gender, parse_gender
from dyak.inflection.petrovich_fio import PetrovichInflector
from dyak.inflection.ports import Declinable
from dyak.inflection.pymorphy_phrase import Position, PymorphyInflector

__all__ = [
    'Declinable',
    'Fio',
    'Initials',
    'NamePart',
    'PetrovichInflector',
    'Position',
    'PymorphyInflector',
    'detect_gender',
    'parse_gender',
]
