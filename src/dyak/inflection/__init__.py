"""
Подсистема склонения (T002+).

T002: ФИО через `petrovich` (`PetrovichInflector`, `Fio`, `NamePart`,
`Initials`) + автоопределение пола (`detect_gender`). Должности через
`pymorphy3` придут в T003 рядом, за тем же портом `Declinable`.
"""

from __future__ import annotations

from dyak.inflection.fio import Fio, Initials, NamePart
from dyak.inflection.gender import detect_gender, parse_gender
from dyak.inflection.petrovich_fio import PetrovichInflector
from dyak.inflection.ports import Declinable

__all__ = [
    'Declinable',
    'Fio',
    'Initials',
    'NamePart',
    'PetrovichInflector',
    'detect_gender',
    'parse_gender',
]
