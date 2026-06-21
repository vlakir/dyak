"""Тесты команды generate (этап 0, T001)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from typer.testing import CliRunner

from dyak.cli import app, generate_documents
from dyak.errors import TableError

_HEADERS = ['Фамилия', 'Имя', 'Отчество', 'Должность', 'Пол', 'Дата начала']
_ROWS = [
    ['Иванов', 'Пётр', 'Семёнович', 'директор', 'м', '01.07.2026'],
    ['Петрова', 'Анна', 'Сергеевна', 'главный бухгалтер', 'ж', '02.07.2026'],
]

_CONFIG = """
columns:
  surname: "Фамилия"
  name: "Имя"
  patronymic: "Отчество"
  position: "Должность"
  gender: "Пол"
  дата_начала: "Дата начала"
filename: "Приказ_{{ сотрудник.фамилия }}.docx"
"""


def _make_xlsx(path: Path, rows: list[list[str]]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(_HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _make_template(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph(
        'Назначить {{ сотрудник.фамилия }} {{ сотрудник.имя }} '
        'на должность {{ сотрудник.должность }} с {{ дата_начала }}.',
    )
    doc.save(path)
    return path


def _fixtures(tmp_path: Path, rows: list[list[str]] | None = None) -> tuple[Path, ...]:
    table = _make_xlsx(tmp_path / 'emp.xlsx', rows if rows is not None else _ROWS)
    template = _make_template(tmp_path / 'tpl.docx')
    config = tmp_path / 'dyak.yaml'
    config.write_text(_CONFIG, encoding='utf-8')
    return table, template, config


def test_generate_one_file_per_row(tmp_path: Path) -> None:
    table, template, config = _fixtures(tmp_path)
    out = tmp_path / 'out'
    written = generate_documents(table, template, out, config, sheet=None)
    assert len(written) == 2
    names = sorted(p.name for p in written)
    assert names == ['Приказ_Иванов.docx', 'Приказ_Петрова.docx']
    text = '\n'.join(p.text for p in Document(out / 'Приказ_Иванов.docx').paragraphs)
    assert 'Назначить Иванов Пётр на должность директор с 01.07.2026.' in text


def test_generate_creates_out_dir(tmp_path: Path) -> None:
    table, template, config = _fixtures(tmp_path)
    out = tmp_path / 'nested' / 'out'
    generate_documents(table, template, out, config, sheet=None)
    assert out.is_dir()


def test_generate_resolves_name_collision(tmp_path: Path) -> None:
    rows = [
        ['Иванов', 'Пётр', 'Семёнович', 'директор', 'м', '01.07.2026'],
        ['Иванов', 'Иван', 'Иванович', 'инженер', 'м', '02.07.2026'],
    ]
    table, template, config = _fixtures(tmp_path, rows)
    out = tmp_path / 'out'
    written = generate_documents(table, template, out, config, sheet=None)
    names = sorted(p.name for p in written)
    assert names == ['Приказ_Иванов.docx', 'Приказ_Иванов_2.docx']


def test_generate_propagates_table_error(tmp_path: Path) -> None:
    rows = [['', 'Пётр', 'Семёнович', 'директор', 'м', '01.07.2026']]
    table, template, config = _fixtures(tmp_path, rows)
    with pytest.raises(TableError):
        generate_documents(table, template, tmp_path / 'out', config, sheet=None)


def test_module_entrypoint_exposes_app() -> None:
    import dyak.__main__ as entry

    assert entry.app is not None


def test_cli_generate_exit_zero(tmp_path: Path) -> None:
    table, template, config = _fixtures(tmp_path)
    out = tmp_path / 'out'
    result = CliRunner().invoke(
        app,
        [
            'generate',
            '--table', str(table),
            '--template', str(template),
            '--out', str(out),
            '--config', str(config),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(list(out.glob('*.docx'))) == 2


def test_cli_generate_reports_error(tmp_path: Path) -> None:
    rows = [['', 'Пётр', 'Семёнович', 'директор', 'м', '01.07.2026']]
    table, template, config = _fixtures(tmp_path, rows)
    result = CliRunner().invoke(
        app,
        [
            'generate',
            '--table', str(table),
            '--template', str(template),
            '--out', str(tmp_path / 'out'),
            '--config', str(config),
        ],
    )
    assert result.exit_code == 1
