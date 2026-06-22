"""
Русские фильтры Jinja: падежи (§8.1, §8.4) + согласование по полу (§8.3).

`build_jinja_env` собирает окружение с шестью падежными фильтрами
`им/рд/дт/вн/тв/пр`, фильтром согласования `согл` и строгим режимом
`StrictUndefined` (T004): неизвестная переменная шаблона не подставляется
молча пустотой, а поднимает ошибку (рендер заворачивает её в доменную
`TemplateError` с именем переменной).

Одно и то же окружение нужно и телу документа (docxtpl), и шаблону имени
файла. `autoescape=True` всегда: для XML тела это обязательно, а кадровые
ФИО/номера на практике не содержат HTML-спецсимволов (`&<>"'`), поэтому на
имена файлов это не влияет.

Фильтр падежа вызывает `.inflect(case)` на любом `Declinable`-значении
(ФИО — T002; должности — T003). Прочие значения проходят как есть —
поэтому `{{ Должность | рд }}` безопасно отдаёт исходную строку, а не
падает. Фильтр `согл` выбирает форму по полу `Declinable`-ФИО.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jinja2

from dyak.domain import RUS_CASE, Gender
from dyak.errors import TemplateError

if TYPE_CHECKING:
    from collections.abc import Callable

    from dyak.domain import Case


def make_case_filter(case: Case) -> Callable[[object], object]:
    """Фильтр падежа: склоняет `Declinable`, прочее отдаёт как есть."""

    def case_filter(value: object) -> object:
        inflect = getattr(value, 'inflect', None)
        if callable(inflect):
            return inflect(case)
        return value

    return case_filter


def agree_by_gender(value: object, male: str, female: str) -> str:
    """Фильтр `согл`: вернуть форму по полу `value` (ФИО). Муж. форма — первая."""
    gender = getattr(value, 'gender', None)
    if not isinstance(gender, Gender):
        msg = (
            'Фильтр «согл» применим к ФИО (несёт пол), а получил значение без '
            f'пола: {value!r}. Используйте, например, {{{{ ФИО | согл(…, …) }}}}.'
        )
        raise TemplateError(msg)
    return female if gender is Gender.FEMALE else male


def build_jinja_env() -> jinja2.Environment:
    """Окружение Jinja: русские фильтры + строгий режим неизвестных переменных."""
    env = jinja2.Environment(autoescape=True, undefined=jinja2.StrictUndefined)
    for rus, case in RUS_CASE.items():
        env.filters[rus] = make_case_filter(case)
    env.filters['согл'] = agree_by_gender
    return env
