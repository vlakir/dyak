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
    POSITION,
    RANK,
    SURNAME,
    split_fullname,
)
from dyak.inflection import (
    Fio,
    NamePart,
    Position,
    Rank,
    detect_gender,
    resolve_gender,
)

if TYPE_CHECKING:
    from dyak.config import CaseForms
    from dyak.domain import Gender, Person
    from dyak.inflection import (
        GenderResolution,
        PetrovichInflector,
        PymorphyInflector,
        RankInflector,
    )

# Канонический ключ целого ФИО в контексте (`{{ ФИО | вн }}`).
KEY_FULLNAME = 'ФИО'

_WHITESPACE = re.compile(r'\s+')

# Роль части ФИО → канонический ключ контекста, под который её кладём.
_PART_KEYS = {SURNAME: KEY_SURNAME, NAME: KEY_NAME, PATRONYMIC: KEY_PATRONYMIC}


def normalize_lookup_key(text: str) -> str:
    """Нормализовать текст к ключу поиска override (нижний регистр, пробелы)."""
    return _WHITESPACE.sub(' ', text).strip().lower()


def _fullname_key(surname: str, name: str, patronymic: str) -> str:
    """Нормализованный ключ ФИО для поиска ручного пола в `gender_overrides`."""
    joined = ' '.join(part for part in (surname, name, patronymic) if part)
    return normalize_lookup_key(joined)


def resolve_row_gender(
    person: Person,
    *,
    roles: dict[str, str],
    fullname_source: str | None,
    gender_overrides: dict[str, Gender],
) -> GenderResolution:
    """Определить пол строки с источником (для отчёта `check`)."""
    surname_t, name_t, patronymic_t = _part_texts(person, roles, fullname_source)
    override = gender_overrides.get(_fullname_key(surname_t, name_t, patronymic_t))
    return resolve_gender(name_t, patronymic_t, override=override)


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


def _add_fio(
    context: dict[str, object],
    person: Person,
    roles: dict[str, str],
    fullname_source: str | None,
    inflector: PetrovichInflector,
    gender_overrides: dict[str, Gender],
) -> None:
    """Положить склоняемые ФИО (`NamePart`/`Fio`) в контекст (если есть)."""
    surname_t, name_t, patronymic_t = _part_texts(person, roles, fullname_source)
    if not (surname_t or name_t or patronymic_t):
        return  # в строке нет ФИО — склонять нечего

    override = gender_overrides.get(_fullname_key(surname_t, name_t, patronymic_t))
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


def _add_position(
    context: dict[str, object],
    person: Person,
    roles: dict[str, str],
    inflector: PymorphyInflector,
    position_overrides: dict[str, CaseForms],
) -> None:
    """Положить склоняемую должность (`Position`) под её колонку (если есть)."""
    key = roles.get(POSITION)
    if key is None:
        return
    text = person.cells.get(key, '')
    if not text:
        return
    forms = position_overrides.get(normalize_lookup_key(text), {})
    context[key] = Position(text, inflector, forms)


def _add_rank(
    context: dict[str, object],
    person: Person,
    roles: dict[str, str],
    inflector: RankInflector,
    rank_overrides: dict[str, CaseForms],
) -> None:
    """Положить склоняемое звание (`Rank`) под его колонку (если есть)."""
    key = roles.get(RANK)
    if key is None:
        return
    text = person.cells.get(key, '')
    if not text:
        return
    forms = rank_overrides.get(normalize_lookup_key(text), {})
    context[key] = Rank(text, inflector, forms)


def build_context(
    person: Person,
    *,
    fullname_source: str | None = None,
    roles: dict[str, str] | None = None,
    inflector: PetrovichInflector | None = None,
    gender_overrides: dict[str, Gender] | None = None,
    position_inflector: PymorphyInflector | None = None,
    position_overrides: dict[str, CaseForms] | None = None,
    rank_inflector: RankInflector | None = None,
    rank_overrides: dict[str, CaseForms] | None = None,
) -> dict[str, object]:
    """Построить контекст; с движками — склоняемые ФИО/должность/звание."""
    context: dict[str, object] = dict(person.cells)
    roles = roles or {}

    if inflector is None:
        # Старый путь (без движка ФИО): части — строками (поведение T006).
        if fullname_source is not None:
            surname_t, name_t, patronymic_t = _part_texts(
                person, roles, fullname_source
            )
            context[KEY_SURNAME] = surname_t
            context[KEY_NAME] = name_t
            context[KEY_PATRONYMIC] = patronymic_t
    else:
        _add_fio(
            context, person, roles, fullname_source, inflector, gender_overrides or {}
        )

    if position_inflector is not None:
        _add_position(
            context, person, roles, position_inflector, position_overrides or {}
        )
    if rank_inflector is not None:
        _add_rank(context, person, roles, rank_inflector, rank_overrides or {})
    return context
