"""
Кандидаты на замену: значение строки → искомый текст + целевой тег (T007).

Фаза 1 (точные совпадения) работает с **плоскими ячейками** строки:
каждый непустой `Person.cells[ключ]` даёт кандидата, который ищется в
документе как есть (именительный падеж / любой текст ячейки) и заменяется
на `{{ ключ }}` — тот же нормализованный заголовок, что в `generate`.

Склоняемые формы (ФИО/должность по 6 падежам) и падежные фильтры
(`{{ Фамилия | дт }}`) добавит фаза 2 поверх этой же структуры —
`Candidate` уже несёт набор искомых форм, а не единственную строку.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dyak.domain import Person


@dataclass(frozen=True, slots=True)
class Candidate:
    """
    Одно значение строки как кандидат на замену в документе.

    `key` — нормализованный заголовок колонки (`Дата_начала`); `tag` —
    готовый тег вывода (`{{ Дата_начала }}`); `forms` — искомые формы
    текста (в фазе 1 ровно одна — текст ячейки; фаза 2 добавит падежи).
    """

    key: str
    tag: str
    forms: tuple[str, ...]


def _tag(key: str) -> str:
    """Собрать тег вывода для нормализованного ключа колонки."""
    return f'{{{{ {key} }}}}'


def build_candidates(person: Person) -> list[Candidate]:
    """
    Собрать кандидатов из плоских ячеек строки (фаза 1).

    Пустые/пробельные ячейки пропускаем (искать нечего). Дубли значений
    под разными ключами не схлопываем — приоритет при перекрытии решает
    matcher (по длине), а в отчёт попадёт каждый ключ.
    """
    candidates: list[Candidate] = []
    for key, raw in person.cells.items():
        value = raw.strip()
        if not value:
            continue
        candidates.append(Candidate(key=key, tag=_tag(key), forms=(value,)))
    return candidates
