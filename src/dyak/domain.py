"""
Доменная модель dyak.

T006: контекст строится по заголовкам колонок, поэтому `Person` стал плоским
словарём «нормализованный заголовок → значение ячейки», а распознанные роли
колонок вынесены в `Table`. Структурные `Fio`/`Position` и склонение
(`Declinable`) добавятся в T002–T003 поверх ролей, не ломая эту модель.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Case(StrEnum):
    """Русский падеж. Значения — граммемы pymorphy (внутренний код)."""

    NOMN = 'nomn'  # именительный (petrovich его не знает → исходная форма)
    GENT = 'gent'  # родительный
    DATV = 'datv'  # дательный
    ACCS = 'accs'  # винительный
    ABLT = 'ablt'  # творительный
    LOCT = 'loct'  # предложный


class Gender(StrEnum):
    """Грамматический род для склонения ФИО."""

    MALE = 'male'
    FEMALE = 'female'


# Мост: русское сокращение из шаблона (`{{ Фамилия | рд }}`) → внутренний падеж.
RUS_CASE: dict[str, Case] = {
    'им': Case.NOMN,
    'рд': Case.GENT,
    'дт': Case.DATV,
    'вн': Case.ACCS,
    'тв': Case.ABLT,
    'пр': Case.LOCT,
}


@dataclass(frozen=True, slots=True)
class Person:
    """
    Одна строка таблицы как плоский контекст для шаблона.

    `cells` — `нормализованный заголовок → строковое значение ячейки`.
    Доступ в шаблоне идёт по этим ключам напрямую: `{{ Фамилия }}`,
    `{{ Дата_начала }}`.
    """

    cells: dict[str, str]


@dataclass(frozen=True, slots=True)
class Table:
    """
    Прочитанная таблица: распознанные роли колонок + строки.

    `roles` — `роль (surname/name/patronymic/position) → ключ контекста`;
    фундамент маршрутизации склонения в T002 и сборки дефолтного имени файла.
    `fullname_source` — ключ колонки «ФИО», которую надо разбирать построчно
    на фамилию/имя/отчество (либо `None`). `people` — строки данных.
    """

    roles: dict[str, str]
    fullname_source: str | None
    people: list[Person]
