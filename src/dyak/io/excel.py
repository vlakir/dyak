"""
Чтение входной таблицы xlsx с маппингом колонок и валидацией (§11).

Этап 0 (T001): значения колонок читаются как строки ровно как в ячейке
(§12). Предполагается, что даты и номера в таблице введены текстом —
openpyxl тогда возвращает их строкой без переформатирования.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openpyxl import load_workbook

from dyak.domain import Person
from dyak.errors import TableError

if TYPE_CHECKING:
    from pathlib import Path

    from openpyxl.workbook import Workbook
    from openpyxl.worksheet.worksheet import Worksheet

    from dyak.config import Config

# Доменное поле Person → атрибут заголовка в config.columns.
_REQUIRED_FIELDS = ('surname', 'name', 'patronymic', 'position', 'gender')


def _to_str(value: object) -> str:
    """Привести значение ячейки к строке без переформатирования."""
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _select_sheet(wb: Workbook, sheet: str | None) -> Worksheet:
    if sheet is None:
        ws = wb.active
        if ws is None:
            msg = 'В книге нет активного листа'
            raise TableError(msg)
        return ws
    if sheet not in wb.sheetnames:
        msg = f'Лист не найден: {sheet}'
        raise TableError(msg)
    return wb[sheet]


def read_table(path: Path, config: Config, sheet: str | None = None) -> list[Person]:
    """Прочитать xlsx в список `Person` согласно `config.columns`."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return _read_rows(_select_sheet(wb, sheet), config)
    finally:
        wb.close()


def _read_rows(ws: Worksheet, config: Config) -> list[Person]:
    rows = ws.iter_rows(values_only=True)
    header_row = next(rows, None)
    if header_row is None:
        msg = 'Таблица пуста: нет строки заголовков'
        raise TableError(msg)

    header_index = {str(h): i for i, h in enumerate(header_row) if h is not None}
    required_titles = {f: getattr(config.columns, f) for f in _REQUIRED_FIELDS}
    extra_titles = config.columns.extra_fields()  # русский ключ → заголовок

    for title in (*required_titles.values(), *extra_titles.values()):
        if title not in header_index:
            msg = f'В таблице не найдена колонка: {title}'
            raise TableError(msg)

    def cell(row: tuple[Any, ...], title: str) -> str:
        idx = header_index[title]
        return _to_str(row[idx]) if idx < len(row) else ''

    people: list[Person] = []
    for line, row in enumerate(rows, start=2):
        values = {f: cell(row, title) for f, title in required_titles.items()}
        for field_name, value in values.items():
            if value == '':
                title = required_titles[field_name]
                msg = f'Пустая обязательная ячейка «{title}» в строке {line}'
                raise TableError(msg)
        extra = {key: cell(row, title) for key, title in extra_titles.items()}
        people.append(Person(extra=extra, **values))
    return people
