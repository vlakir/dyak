"""
Сборка контекста для Jinja/docxtpl (T006).

Контекст плоский: ключ = нормализованный заголовок колонки, значение =
строка ячейки. Доступ в шаблоне напрямую — `{{ Фамилия }}`,
`{{ Дата_начала }}`. Если таблица хранит ФИО в одной колонке
(`fullname_source`), она дополнительно разбирается на канонические ключи
`Фамилия`/`Имя`/`Отчество` — при этом целое `{{ ФИО }}` тоже остаётся
доступным. В T002 поверх ролей (см. `Table.roles`) появятся склоняемые
объекты, а падежные фильтры регистрируются в Jinja-окружении.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dyak.columns import KEY_NAME, KEY_PATRONYMIC, KEY_SURNAME, split_fullname

if TYPE_CHECKING:
    from dyak.domain import Person


def build_context(
    person: Person,
    fullname_source: str | None = None,
) -> dict[str, object]:
    """Построить плоский Jinja-контекст; при наличии — разобрать ФИО на части."""
    context: dict[str, object] = {}
    context.update(person.cells)
    if fullname_source is not None:
        raw = person.cells.get(fullname_source, '')
        surname, name, patronymic = split_fullname(raw)
        context[KEY_SURNAME] = surname
        context[KEY_NAME] = name
        context[KEY_PATRONYMIC] = patronymic
    return context
