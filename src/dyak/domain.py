"""
Доменная модель dyak.

Этап 0 (T001): `Person` — плоская запись таблицы, все значения строки.
Структурные `Fio`/`Position`/`Gender` и склонение (`Declinable`)
добавляются в T002–T003 поверх этой модели, не ломая её.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Person:
    """
    Одна строка таблицы сотрудников.

    `extra` — дополнительные колонки (даты, номера приказов и т.п.),
    доступные в шаблоне по русскому имени-ключу из `config.columns`.
    """

    surname: str
    name: str
    patronymic: str
    position: str
    gender: str
    extra: dict[str, str] = field(default_factory=dict)
