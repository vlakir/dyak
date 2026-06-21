"""Тесты чтения xlsx по заголовкам колонок (T006)."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from dyak.config import Config
from dyak.errors import TableError
from dyak.io.excel import read_table

_HEADERS = ['Фамилия', 'Имя', 'Отчество', 'Должность', 'Дата начала']
_ROWS = [
    ['Иванов', 'Пётр', 'Семёнович', 'директор', '01.07.2026'],
    ['Петрова', 'Анна', 'Сергеевна', 'главный бухгалтер', '02.07.2026'],
]


def _make_xlsx(
    path: Path,
    headers: list[str],
    rows: list[list[str]],
    sheet_title: str | None = None,
) -> Path:
    wb = Workbook()
    ws = wb.active
    if sheet_title is not None:
        ws.title = sheet_title
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def test_reads_all_rows(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path / 't.xlsx', _HEADERS, _ROWS)
    table = read_table(xlsx, Config())
    assert len(table.people) == 2
    assert table.people[0].cells['Фамилия'] == 'Иванов'
    assert table.people[1].cells['Имя'] == 'Анна'


def test_header_spaces_normalized_to_key(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path / 't.xlsx', _HEADERS, _ROWS)
    table = read_table(xlsx, Config())
    assert table.people[0].cells['Дата_начала'] == '01.07.2026'
    assert 'Дата начала' not in table.people[0].cells


def test_roles_recognized(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path / 't.xlsx', _HEADERS, _ROWS)
    table = read_table(xlsx, Config())
    assert table.roles == {
        'surname': 'Фамилия',
        'name': 'Имя',
        'patronymic': 'Отчество',
        'position': 'Должность',
    }


def test_roles_use_aliases(tmp_path: Path) -> None:
    headers = ['Сотрудник', 'Дата начала']
    rows = [['Иванов', '01.07.2026']]
    xlsx = _make_xlsx(tmp_path / 't.xlsx', headers, rows)
    config = Config.model_validate({'aliases': {'Сотрудник': 'surname'}})
    table = read_table(xlsx, config)
    assert table.roles == {'surname': 'Сотрудник'}


def test_header_collision_after_normalization_raises(tmp_path: Path) -> None:
    headers = ['Дата начала', 'Дата_начала']
    rows = [['01.07.2026', '02.07.2026']]
    xlsx = _make_xlsx(tmp_path / 't.xlsx', headers, rows)
    with pytest.raises(TableError, match='одинаковый ключ'):
        read_table(xlsx, Config())


def test_skips_fully_empty_rows(tmp_path: Path) -> None:
    rows = [
        ['Иванов', 'Пётр', 'Семёнович', 'директор', '01.07.2026'],
        ['', '', '', '', ''],
    ]
    xlsx = _make_xlsx(tmp_path / 't.xlsx', _HEADERS, rows)
    table = read_table(xlsx, Config())
    assert len(table.people) == 1


def test_sheet_not_found_raises(tmp_path: Path) -> None:
    xlsx = _make_xlsx(tmp_path / 't.xlsx', _HEADERS, _ROWS)
    with pytest.raises(TableError, match='не найден'):
        read_table(xlsx, Config(), sheet='Нет такого')


def test_empty_table_raises(tmp_path: Path) -> None:
    path = tmp_path / 't.xlsx'
    Workbook().save(path)
    with pytest.raises(TableError, match='пуст'):
        read_table(path, Config())


def test_numeric_cell_rendered_without_decimal(tmp_path: Path) -> None:
    xlsx = _make_xlsx(
        tmp_path / 't.xlsx',
        [*_HEADERS, 'Номер'],
        [[*_ROWS[0], 17]],
    )
    table = read_table(xlsx, Config())
    assert table.people[0].cells['Номер'] == '17'


def test_single_fullname_column_sets_source(tmp_path: Path) -> None:
    headers = ['ФИО', 'Должность']
    rows = [['Иванов Пётр Семёнович', 'директор']]
    xlsx = _make_xlsx(tmp_path / 't.xlsx', headers, rows)
    table = read_table(xlsx, Config())
    assert table.fullname_source == 'ФИО'
    assert table.people[0].cells['ФИО'] == 'Иванов Пётр Семёнович'
    assert table.roles['surname'] == 'Фамилия'


def test_sheet_selected_by_name(tmp_path: Path) -> None:
    path = tmp_path / 't.xlsx'
    wb = Workbook()
    wb.active.title = 'Прочее'
    target = wb.create_sheet('Сотрудники')
    target.append(_HEADERS)
    for row in _ROWS:
        target.append(row)
    wb.save(path)
    table = read_table(path, Config(), sheet='Сотрудники')
    assert len(table.people) == 2
    assert table.people[0].cells['Фамилия'] == 'Иванов'
