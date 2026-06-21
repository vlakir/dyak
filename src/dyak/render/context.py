"""
Сборка русскоязычного контекста для Jinja/docxtpl (§8.4).

Этап 0 (T001): `сотрудник` — простой словарь строковых полей, никаких
склонений. В T002 фасад заменяется на объект с `Declinable`-полями, а
падежные фильтры регистрируются в Jinja-окружении.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dyak.domain import Person


def build_context(person: Person) -> dict[str, object]:
    """Построить Jinja-контекст для одной записи таблицы."""
    facade = {
        'фамилия': person.surname,
        'имя': person.name,
        'отчество': person.patronymic,
        'должность': person.position,
    }
    context: dict[str, object] = {'сотрудник': facade}
    context.update(person.extra)
    return context
