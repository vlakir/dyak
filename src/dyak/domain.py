"""
Доменная модель dyak.

T006: контекст строится по заголовкам колонок, поэтому `Person` стал плоским
словарём «нормализованный заголовок → значение ячейки», а распознанные роли
колонок вынесены в `Table`. Структурные `Fio`/`Position` и склонение
(`Declinable`) добавятся в T002–T003 поверх ролей, не ломая эту модель.
"""

from __future__ import annotations

from dataclasses import dataclass


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
