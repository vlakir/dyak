"""
Склонение частей ФИО через `petrovich` (§7.1).

Обёртка решает три расхождения движка с нашими требованиями:

1. **Именительный падеж** `petrovich` не знает (его `Case` без `nominative`)
   — `Case.NOMN` возвращает исходный текст без обращения к движку.
2. **Пустые части** (`firstname=''`) `petrovich` отвергает `ValueError`
   — пустую часть возвращаем как `''` сразу (нет отчества → пустая
   подстановка, не ошибка).
3. **UPPERCASE** движок не склоняет (правила не матчат верхний регистр и
   текст возвращается как есть). Если часть записана капсом (`ИВАНОВ`) —
   склоняем `.capitalize()`-форму и поднимаем результат в `.upper()`
   (`ИВАНОВА`). Это и есть «сохранение регистра» из acceptance T002.

`MorphAnalyzer` тут не нужен — petrovich самодостаточен; несклоняемые
фамилии (Дюма, женское «Ким», `-ко`) он отдаёт без изменений сам.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from petrovich.enums import Case as PCase
from petrovich.enums import Gender as PGender
from petrovich.main import Petrovich

from dyak.domain import Case, Gender

if TYPE_CHECKING:
    from collections.abc import Callable

    from dyak.inflection.fio import NameKind

# Наш падеж → константа petrovich. Именительного у petrovich нет (passthrough).
_PETROVICH_CASE: dict[Case, int] = {
    Case.GENT: PCase.GENITIVE,
    Case.DATV: PCase.DATIVE,
    Case.ACCS: PCase.ACCUSATIVE,
    Case.ABLT: PCase.INSTRUMENTAL,
    Case.LOCT: PCase.PREPOSITIONAL,
}

_PETROVICH_GENDER: dict[Gender, str] = {
    Gender.MALE: PGender.MALE,
    Gender.FEMALE: PGender.FEMALE,
}


class PetrovichInflector:
    """Склоняет фамилию/имя/отчество с учётом пола, регистра и пустых строк."""

    def __init__(self) -> None:
        self._petrovich = Petrovich()

    def inflect(self, text: str, kind: NameKind, case: Case, gender: Gender) -> str:
        """Просклонять часть ФИО `kind` к падежу `case` для пола `gender`."""
        if not text:
            return ''
        if case is Case.NOMN:
            return text
        method = self._method(kind)
        is_upper = text.isupper()
        source = text.capitalize() if is_upper else text
        result = method(source, _PETROVICH_CASE[case], _PETROVICH_GENDER[gender])
        return result.upper() if is_upper else result

    def _method(self, kind: NameKind) -> Callable[[str, int, str], str]:
        return {
            'surname': self._petrovich.lastname,
            'name': self._petrovich.firstname,
            'patronymic': self._petrovich.middlename,
        }[kind]
