"""
Русские падежные фильтры Jinja (§8.1, §8.4).

`build_jinja_env` собирает окружение с шестью фильтрами `им/рд/дт/вн/тв/пр`.
Одно и то же окружение нужно и телу документа (docxtpl), и шаблону имени
файла, поэтому регистрация вынесена сюда. `autoescape=True` всегда: для
XML тела это обязательно, а кадровые ФИО/номера на практике не содержат
HTML-спецсимволов (`&<>"'`), поэтому на имена файлов это не влияет.

Фильтр падежа вызывает `.inflect(case)` на любом `Declinable`-значении
(ФИО в T002; должности в T003). Прочие значения проходят как есть —
поэтому `{{ Должность | рд }}` в T002 (до pymorphy) безопасно отдаёт
исходную строку, а не падает.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jinja2

from dyak.domain import RUS_CASE

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


def build_jinja_env() -> jinja2.Environment:
    """Окружение Jinja с зарегистрированными русскими падежными фильтрами."""
    env = jinja2.Environment(autoescape=True)
    for rus, case in RUS_CASE.items():
        env.filters[rus] = make_case_filter(case)
    return env
