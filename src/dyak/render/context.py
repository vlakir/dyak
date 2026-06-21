"""
Сборка контекста для Jinja/docxtpl (T006 + склонение T002).

Базовый контекст плоский: ключ = нормализованный заголовок колонки,
значение = строка ячейки (`{{ Дата_начала }}`). Поверх этого T002
навешивает склонение: распознанные колонки ФИО (`Table.roles`) становятся
склоняемыми объектами `NamePart`, а целое ФИО доступно под ключом `ФИО`
как `Fio`. Пол определяется автоматически (`detect_gender`) и может быть
переопределён вручную через `gender_overrides` (секция `genders` конфига).

Без `inflector` (старый путь / простые тесты) поведение T006 сохраняется:
части ФИО кладутся строками, склонения нет.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dyak.columns import (
    KEY_NAME,
    KEY_PATRONYMIC,
    KEY_SURNAME,
    NAME,
    PATRONYMIC,
    SURNAME,
    split_fullname,
)
from dyak.inflection import Fio, NamePart, detect_gender

if TYPE_CHECKING:
    from dyak.domain import Gender, Person
    from dyak.inflection import PetrovichInflector

# Канонический ключ целого ФИО в контексте (`{{ ФИО | вн }}`).
KEY_FULLNAME = 'ФИО'

_WHITESPACE = re.compile(r'\s+')

# Роль части ФИО → канонический ключ контекста, под который её кладём.
_PART_KEYS = {SURNAME: KEY_SURNAME, NAME: KEY_NAME, PATRONYMIC: KEY_PATRONYMIC}


def normalize_fullname_key(text: str) -> str:
    """Нормализовать ФИО к ключу поиска ручного пола (нижний регистр, пробелы)."""
    return _WHITESPACE.sub(' ', text).strip().lower()


def _fullname_key(surname: str, name: str, patronymic: str) -> str:
    """Нормализованный ключ ФИО для поиска ручного пола в `gender_overrides`."""
    joined = ' '.join(part for part in (surname, name, patronymic) if part)
    return normalize_fullname_key(joined)


def _part_texts(
    person: Person,
    roles: dict[str, str],
    fullname_source: str | None,
) -> tuple[str, str, str]:
    """Достать тексты фамилии/имени/отчества из строки (колонки или ФИО)."""
    if fullname_source is not None:
        return split_fullname(person.cells.get(fullname_source, ''))
    return (
        person.cells.get(roles.get(SURNAME, ''), ''),
        person.cells.get(roles.get(NAME, ''), ''),
        person.cells.get(roles.get(PATRONYMIC, ''), ''),
    )


def build_context(
    person: Person,
    *,
    fullname_source: str | None = None,
    roles: dict[str, str] | None = None,
    inflector: PetrovichInflector | None = None,
    gender_overrides: dict[str, Gender] | None = None,
) -> dict[str, object]:
    """Построить контекст; при наличии `inflector` — со склоняемыми ФИО."""
    context: dict[str, object] = dict(person.cells)
    roles = roles or {}

    surname_t, name_t, patronymic_t = _part_texts(person, roles, fullname_source)

    # Старый путь (без движка): части ФИО — простыми строками (поведение T006).
    if inflector is None:
        if fullname_source is not None:
            context[KEY_SURNAME] = surname_t
            context[KEY_NAME] = name_t
            context[KEY_PATRONYMIC] = patronymic_t
        return context

    if not (surname_t or name_t or patronymic_t):
        return context  # в строке нет ФИО — склонять нечего

    override = (gender_overrides or {}).get(
        _fullname_key(surname_t, name_t, patronymic_t)
    )
    gender = detect_gender(name_t, patronymic_t, override=override)

    parts = {
        SURNAME: NamePart(surname_t, 'surname', gender, inflector),
        NAME: NamePart(name_t, 'name', gender, inflector),
        PATRONYMIC: NamePart(patronymic_t, 'patronymic', gender, inflector),
    }
    fio = Fio(parts[SURNAME], parts[NAME], parts[PATRONYMIC])
    context[KEY_FULLNAME] = fio
    if fullname_source is not None:
        # Колонка «ФИО» теперь склоняется (вместо сырой строки T006).
        context[fullname_source] = fio
        for role, key in _PART_KEYS.items():
            context[key] = parts[role]
    else:
        # Отдельные колонки — кладём NamePart под их фактические заголовки.
        for role, key in roles.items():
            if role in parts:
                context[key] = parts[role]
    return context
