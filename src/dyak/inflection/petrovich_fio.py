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

import functools
import json
from pathlib import Path
from typing import TYPE_CHECKING

from petrovich.enums import Case as PCase
from petrovich.enums import Gender as PGender
from petrovich.main import DEFAULT_RULES_PATH, Petrovich

from dyak.domain import Case, Gender
from dyak.inflection.morph import get_analyzer

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


@functools.lru_cache(maxsize=4096)
def is_known_surname(text: str) -> bool:
    """
    Опознаёт ли pymorphy слово как фамилию (грамема `Surn`).

    Фамилии-нарицательные (Бивень, Кузнец, Заяц) грамемы `Surn` не имеют —
    pymorphy знает их только как обычные слова. В официальных документах такие
    фамилии не склоняют (T027): petrovich для них даёт спорные и порой неверные
    формы (Кузн**ц**у, Пал**ц**у), а именительный всегда безопасен. Сигнал
    точный — у обычных фамилий (Иванов, Соколов, …) `Surn` есть всегда.
    """
    return any('Surn' in parse.tag for parse in get_analyzer().parse(text))


class _Utf8Petrovich(Petrovich):
    """
    `Petrovich`, читающий `rules.json` явным UTF-8 (фикс T021).

    Штатный `Petrovich.__init__` открывает `rules.json` через `open(path, 'r')`
    без указания кодировки — берётся локальная (`locale.getpreferredencoding`).
    На русской Windows это `cp1251`, и UTF-8-кириллица в суффиксах правил
    мис-декодируется: тесты правил перестают совпадать, фамилия молча проходит
    несклонённой (ПУПКИН вместо ПУПКИНУ) — баг проявился в Windows-сборке
    v0.3.0, тогда как Linux (UTF-8 по умолчанию) не затронут. Грузим правила
    сами с `encoding='utf-8'`, поэтому фикс не зависит от окружения и работает
    как из GUI, так и при прямом запуске exe (без `PYTHONUTF8`).
    """

    def __init__(self) -> None:
        with Path(DEFAULT_RULES_PATH).open(encoding='utf-8') as fp:
            self.data = json.load(fp)


class PetrovichInflector:
    """Склоняет фамилию/имя/отчество с учётом пола, регистра и пустых строк."""

    def __init__(self) -> None:
        self._petrovich = _Utf8Petrovich()

    def inflect(
        self,
        text: str,
        kind: NameKind,
        case: Case,
        gender: Gender,
        *,
        force_decline: bool = False,
    ) -> str:
        """Просклонять часть ФИО `kind` к падежу `case` для пола `gender`."""
        if not text:
            return ''
        if case is Case.NOMN:
            return text
        if kind == 'surname' and not force_decline and not is_known_surname(text):
            # Фамилия-нарицательное (Бивень, Кузнец) — не опознана как фамилия;
            # в официальных документах не склоняется (T027). `force_decline`
            # (список `decline_surnames` конфига) переопределяет.
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
