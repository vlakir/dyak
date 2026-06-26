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
    RANK,
    SURNAME,
    is_literal_value,
    split_fullname,
)
from dyak.inflection import (
    Fio,
    NamePart,
    Phrase,
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
        PhraseInflector,
        RankInflector,
    )

# Канонический ключ целого ФИО в контексте (`{{ ФИО | вн }}`).
KEY_FULLNAME = 'ФИО'

# Производные формы ФИО, доступные ПЛОСКИМИ тегами наравне с `{{ Фамилия }}`
# (ADR 2026-06-26, T031), а не только через `{{ ФИО.* }}`. Ключ контекста →
# атрибут `Fio` (одиночные инициалы → строка, составные → `Initials`).
# Точечная форма `{{ ФИО.инициалы }}` тоже остаётся рабочей (обратная
# совместимость с шаблонами 0.3.x).
_FIO_DERIVED_KEYS = {
    'Инициалы': 'инициалы',
    'Инициалы_впереди': 'инициалы_впереди',
    'Инициалы_слитно': 'инициалы_слитно',
    'Фамилия_инициал': 'фамилия_инициал',
    'Имя_инициал': 'имя_инициал',
    'Отчество_инициал': 'отчество_инициал',
}

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
    decline_surnames: set[str],
) -> None:
    """Положить склоняемые ФИО (`NamePart`/`Fio`) в контекст (если есть)."""
    surname_t, name_t, patronymic_t = _part_texts(person, roles, fullname_source)
    if not (surname_t or name_t or patronymic_t):
        return  # в строке нет ФИО — склонять нечего

    override = gender_overrides.get(_fullname_key(surname_t, name_t, patronymic_t))
    gender = detect_gender(name_t, patronymic_t, override=override)
    # Принудительное склонение фамилии-нарицательного (обход правила T027).
    force = normalize_lookup_key(surname_t) in decline_surnames

    parts = {
        SURNAME: NamePart(surname_t, 'surname', gender, inflector, force_decline=force),
        NAME: NamePart(name_t, 'name', gender, inflector),
        PATRONYMIC: NamePart(patronymic_t, 'patronymic', gender, inflector),
    }
    fio = Fio(parts[SURNAME], parts[NAME], parts[PATRONYMIC])
    context[KEY_FULLNAME] = fio
    # Инициалы — плоскими тегами (наравне с Фамилия/Имя/Отчество), не только
    # через `ФИО.*` (T031). Точечная форма продолжает работать через `__getattr__`.
    for key, attr in _FIO_DERIVED_KEYS.items():
        context[key] = getattr(fio, attr)
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


def _add_phrases(
    context: dict[str, object],
    person: Person,
    inflector: PhraseInflector,
    position_overrides: dict[str, CaseForms],
) -> None:
    """
    Обернуть каждую текстовую ячейку склоняемой `Phrase` (T024).

    Модель «склонение по умолчанию»: склоняется ЛЮБАЯ колонка (должность,
    подразделение, произвольный текст), а не только распознанная по роли.
    Пропускаются ячейки, уже обёрнутые специализациями (ФИО → `NamePart`/`Fio`,
    звание → `Rank`: их значение в контексте — не `str`), и литералы по форме
    (коды/личные номера/даты — `is_literal_value`). Ручной `overrides.position`
    по тексту фразы имеет приоритет над движком.
    """
    for key in person.cells:
        if not isinstance(context.get(key), str):
            continue  # уже обёрнуто ФИО/званием — не трогаем
        text = str(context[key]).strip()
        if not text or is_literal_value(text):
            continue
        forms = position_overrides.get(normalize_lookup_key(text), {})
        context[key] = Phrase(text, inflector, forms)


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
    decline_surnames: set[str] | None = None,
    position_inflector: PhraseInflector | None = None,
    position_overrides: dict[str, CaseForms] | None = None,
    rank_inflector: RankInflector | None = None,
    rank_overrides: dict[str, CaseForms] | None = None,
) -> dict[str, object]:
    """Построить контекст; с движками — склоняемые ФИО/звание/любая фраза."""
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
            context,
            person,
            roles,
            fullname_source,
            inflector,
            gender_overrides or {},
            decline_surnames or set(),
        )

    # Звание — спец-ветка ДО generic-обёртки, чтобы её колонка стала `Rank` и
    # не была перехвачена универсальным фраз-движком.
    if rank_inflector is not None:
        _add_rank(context, person, roles, rank_inflector, rank_overrides or {})
    if position_inflector is not None:
        _add_phrases(context, person, position_inflector, position_overrides or {})
    return context
