"""
Кандидаты на замену: значение строки → искомые формы + целевые теги (T007).

Фаза 1 (точные совпадения) работала только с **плоскими ячейками** строки.
Фаза 2 добавляет **decline-and-match**: склоняемые значения (части ФИО,
должность, целое ФИО, инициалы) дают набор форм по 6 падежам, и каждая форма
несёт свой тег с падежным фильтром (`{{ Фамилия | дт }}`). Падеж формы
вычисляется тем, какая из шести просклонённых строк совпала в документе;
именительный → тег без фильтра. Если несколько падежей дают одну и ту же
строку (омонимия, напр. фамилия «Иванова» = рд = вн у м.р.) — берём первый
по каноническому порядку (именительный раньше прочих) и помечаем форму
`ambiguous` (отчёт + подсветка).

Источник склоняемых объектов — тот же `build_context`, что у `generate`:
переиспользуем `Fio`/`NamePart`/`Phrase` и не дублируем логику ролей/пола.
Без движков (`inflector`/`position_inflector` = `None`) поведение совпадает с
фазой 1 — кандидаты только из плоских ячеек.

ФИО по частям (Q3): целое `{{ ФИО }}` рождается только когда в строке есть
колонка «ФИО» (`fullname_source`); при отдельных колонках фамилии/имени/
отчества заменяем по частям. Инициалы — best-effort, вторичные кандидаты.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dyak.domain import CASE_RUS, Case
from dyak.inflection import Fio, NamePart, Phrase, Rank
from dyak.render.context import KEY_FULLNAME, build_context

if TYPE_CHECKING:
    from dyak.config import CaseForms
    from dyak.domain import Gender, Person
    from dyak.inflection import (
        Declinable,
        PetrovichInflector,
        PhraseInflector,
        RankInflector,
    )

# Падежи в каноническом порядке (именительный первым): при омонимии форм
# выигрывает падеж раньше по списку, поэтому совпавшая основа без склонения
# становится тегом без фильтра, а не случайным косвенным падежом.
_CASES: tuple[Case, ...] = tuple(Case)

# Имена атрибутов инициалов `Fio` → ключ-тег (`{{ ФИО.инициалы | дт }}`).
_INITIALS_ATTRS: tuple[str, ...] = ('инициалы', 'инициалы_впереди', 'инициалы_слитно')


@dataclass(frozen=True, slots=True)
class SearchForm:
    """
    Одна искомая форма значения: текст для поиска в документе → целевой тег.

    `ambiguous` — несколько падежей дают эту же строку, выбран первый по
    `_CASES`; место помечается в отчёте и подсвечивается в шаблоне.
    """

    text: str
    tag: str
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class Candidate:
    """
    Значение строки как кандидат на замену в документе.

    `key` — ключ для группировки в отчёте (заголовок колонки / `ФИО` и т.п.);
    `display` — именительная/исходная форма для сообщений; `forms` — искомые
    формы с тегами; `primary` — ждём ли значение в документе (если да и не
    нашлось → `not_found`; вторичные fallback-кандидаты молчат при отсутствии).
    `name_part` — кандидат относится к имени субъекта (фамилия/имя/отчество/
    целое ФИО/инициалы): по сумме их совпадений T018 предупреждает о возможной
    подписи/исполнителе.
    """

    key: str
    display: str
    forms: tuple[SearchForm, ...]
    primary: bool = True
    name_part: bool = False


def _tag(key: str) -> str:
    """Тег вывода без падежного фильтра (`{{ Дата_начала }}`)."""
    return f'{{{{ {key} }}}}'


def _case_tag(key: str, case: Case) -> str:
    """Тег вывода с падежным фильтром (именительный → без фильтра)."""
    if case is Case.NOMN:
        return _tag(key)
    return f'{{{{ {key} | {CASE_RUS[case]} }}}}'


def _decline_forms(obj: Declinable, key: str) -> tuple[SearchForm, ...]:
    """Формы склоняемого значения по 6 падежам (омонимия → `ambiguous`)."""
    cases_by_text: dict[str, list[Case]] = {}
    for case in _CASES:
        form = obj.inflect(case)
        if form:
            cases_by_text.setdefault(form, []).append(case)
    return tuple(
        SearchForm(text, _case_tag(key, cases[0]), ambiguous=len(cases) > 1)
        for text, cases in cases_by_text.items()
    )


def _fio_candidates(
    fio: Fio,
    fullname_source: str | None,
    consumed: set[str],
) -> list[Candidate]:
    """Целое ФИО (только при колонке «ФИО», Q3) + инициалы (best-effort)."""
    candidates: list[Candidate] = []
    if fullname_source is not None:
        forms = _decline_forms(fio, fullname_source)
        if forms:
            candidates.append(
                Candidate(
                    fullname_source,
                    fio.inflect(Case.NOMN),
                    forms,
                    primary=True,
                    name_part=True,
                )
            )
            consumed.add(fullname_source)
    for attr in _INITIALS_ATTRS:
        initials = getattr(fio, attr)
        forms = _decline_forms(initials, f'{KEY_FULLNAME}.{attr}')
        if forms:
            candidates.append(
                Candidate(
                    f'{KEY_FULLNAME}.{attr}',
                    initials.inflect(Case.NOMN),
                    forms,
                    primary=False,
                    name_part=True,
                )
            )
    return candidates


def _declinable_candidates(
    context: dict[str, object],
    person: Person,
    fullname_source: str | None,
    consumed: set[str],
) -> list[Candidate]:
    """Склоняемые кандидаты из контекста (части ФИО, должность, ФИО, инициалы)."""
    candidates: list[Candidate] = []
    for key, value in context.items():
        if isinstance(value, NamePart | Phrase | Rank):
            forms = _decline_forms(value, key)
            if not forms:
                continue
            # Часть ФИО / должность / звание под её реальной колонкой (есть в
            # `cells`) — первичная;
            # производная из колонки «ФИО» (канонический ключ, нет в `cells`) —
            # вторичный fallback, чтобы не шуметь `not_found` поверх целого ФИО.
            primary = key in person.cells
            candidates.append(
                Candidate(
                    key,
                    value.text,
                    forms,
                    primary=primary,
                    name_part=isinstance(value, NamePart),
                )
            )
            if key in person.cells:
                consumed.add(key)
    fio = context.get(KEY_FULLNAME)
    if isinstance(fio, Fio):
        candidates.extend(_fio_candidates(fio, fullname_source, consumed))
    return candidates


def build_candidates(
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
) -> list[Candidate]:
    """
    Собрать кандидатов на замену из строки данных.

    С движками склонения (`inflector`/`position_inflector`/`rank_inflector`)
    добавляются склоняемые кандидаты (фаза 2); без них — только плоские ячейки
    (фаза 1). Плоские ячейки, уже покрытые склонением, пропускаются
    (`consumed`).
    """
    candidates: list[Candidate] = []
    consumed: set[str] = set()

    if (
        inflector is not None
        or position_inflector is not None
        or rank_inflector is not None
    ):
        context = build_context(
            person,
            fullname_source=fullname_source,
            roles=roles or {},
            inflector=inflector,
            gender_overrides=gender_overrides,
            decline_surnames=decline_surnames,
            position_inflector=position_inflector,
            position_overrides=position_overrides,
            rank_inflector=rank_inflector,
            rank_overrides=rank_overrides,
        )
        candidates.extend(
            _declinable_candidates(context, person, fullname_source, consumed)
        )

    for key, raw in person.cells.items():
        if key in consumed:
            continue
        value = raw.strip()
        if value:
            candidates.append(
                Candidate(key=key, display=value, forms=(SearchForm(value, _tag(key)),))
            )
    return candidates
