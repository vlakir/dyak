"""
Порты подсистемы склонения (§6 CONCEPT).

`Declinable` — доменный объект, умеющий склонять себя к падежу. Падежные
фильтры Jinja (`render/filters.py`) вызывают `.inflect(case)` на любом
значении контекста, у которого этот метод есть; прочие значения проходят
как есть. Это держит маршрутизацию открытой: ФИО (T002), должности (T003)
и любые будущие склоняемые типы подключаются без правки фильтров.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dyak.domain import Case


@runtime_checkable
class Declinable(Protocol):
    """Объект, который умеет вернуть свою форму в заданном падеже."""

    def inflect(self, case: Case) -> str: ...
