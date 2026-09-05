"""Тесты команды generate (T006: подстановка по заголовкам, --filename)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from typer.testing import CliRunner

from dyak.cli import app, configure_stdio

_HEADERS = ['Фамилия', 'Имя', 'Отчество', 'Должность', 'Дата начала']
_ROWS = [
    ['Иванов', 'Пётр', 'Семёнович', 'директор', '01.07.2026'],
    ['Петрова', 'Анна', 'Сергеевна', 'главный бухгалтер', '02.07.2026'],
]


def _make_xlsx(path: Path, rows: list[list[str]], headers: list[str]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _make_template(path: Path) -> Path:
    doc = Document()
    doc.add_paragraph(
        'Назначить {{ Фамилия }} {{ Имя }} на должность '
        '{{ Должность }} с {{ Дата_начала }}.',
    )
    doc.save(path)
    return path


def _fixtures(
    tmp_path: Path,
    rows: list[list[str]] | None = None,
    headers: list[str] | None = None,
) -> tuple[Path, Path]:
    table = _make_xlsx(
        tmp_path / 'emp.xlsx',
        rows if rows is not None else _ROWS,
        headers if headers is not None else _HEADERS,
    )
    template = _make_template(tmp_path / 'tpl.docx')
    return table, template








def test_module_entrypoint_exposes_app() -> None:
    import dyak.__main__ as entry

    assert entry.app is not None


def test_cli_generate_exit_zero_zero_config(tmp_path: Path) -> None:
    table, template = _fixtures(tmp_path)
    out = tmp_path / 'out'
    result = CliRunner().invoke(
        app,
        [
            'generate',
            '--table', str(table),
            '--template', str(template),
            '--out', str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(list(out.glob('*.docx'))) == 2


def test_cli_generate_reports_error_on_header_collision(tmp_path: Path) -> None:
    headers = ['Дата начала', 'Дата_начала']
    table = _make_xlsx(tmp_path / 'emp.xlsx', [['a', 'b']], headers)
    template = _make_template(tmp_path / 'tpl.docx')
    result = CliRunner().invoke(
        app,
        [
            'generate',
            '--table', str(table),
            '--template', str(template),
            '--out', str(tmp_path / 'out'),
        ],
    )
    assert result.exit_code == 1




def test_cli_check_clean_table_exits_zero(tmp_path: Path) -> None:
    table = _make_xlsx(tmp_path / 'emp.xlsx', _ROWS, _HEADERS)
    template = _make_template(tmp_path / 'tpl.docx')
    result = CliRunner().invoke(
        app,
        [
            'check',
            '--table', str(table),
            '--template', str(template),
        ],
    )
    assert result.exit_code == 0, result.output
    assert 'Проблем не найдено' in result.output


def test_cli_check_undefined_var_exits_one(tmp_path: Path) -> None:
    table = _make_xlsx(tmp_path / 'emp.xlsx', _ROWS, _HEADERS)
    template = tmp_path / 'bad.docx'
    doc = Document()
    doc.add_paragraph('{{ Опечатка }}')
    doc.save(template)
    result = CliRunner().invoke(
        app,
        [
            'check',
            '--table', str(table),
            '--template', str(template),
        ],
    )
    assert result.exit_code == 1
    assert 'Опечатка' in result.output


class _RecordingStream:
    def __init__(self) -> None:
        self.encodings: list[str] = []

    def reconfigure(self, *, encoding: str) -> None:
        self.encodings.append(encoding)


def test_configure_stdio_switches_to_utf8_when_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # T023: ядро из GUI (PYTHONUTF8=1) переключает потоки на UTF-8.
    monkeypatch.setenv('PYTHONUTF8', '1')
    out, err = _RecordingStream(), _RecordingStream()
    monkeypatch.setattr('dyak.cli.sys.stdout', out)
    monkeypatch.setattr('dyak.cli.sys.stderr', err)
    configure_stdio()
    assert out.encodings == ['utf-8']
    assert err.encodings == ['utf-8']


def test_configure_stdio_noop_without_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    # Прямой CLI (без PYTHONUTF8) — потоки не трогаем (нативная консоль).
    monkeypatch.delenv('PYTHONUTF8', raising=False)
    out = _RecordingStream()
    monkeypatch.setattr('dyak.cli.sys.stdout', out)
    configure_stdio()
    assert out.encodings == []


# --- reverse через CLI --------------------------------------------------------
#
# Тесты вернулись из уехавшего test_reverse.py: сама обратная сборка теперь в
# библиотеке, но КОМАНДА `dyak reverse` — по-прежнему наша, и порядок её
# аргументов при переезде поменялся (`row` стал четвёртым позиционным в
# `reverse_template`). Без этих двух тестов перестановку ловить нечем.


def _sample_doc(path: Path, text: str) -> Path:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def test_cli_reverse_builds_template(tmp_path: Path) -> None:
    table = _make_xlsx(
        tmp_path / 'emp.xlsx',
        [['Иванов', 'Пётр', 'директор']],
        ['Фамилия', 'Имя', 'Должность'],
    )
    sample = _sample_doc(tmp_path / 'sample.docx', 'Назначить Иванов на директор.')
    out = tmp_path / 'tpl.docx'
    result = CliRunner().invoke(
        app,
        [
            'reverse',
            '--doc',
            str(sample),
            '--table',
            str(table),
            '--row',
            '1',
            '--out',
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    body = '\n'.join(p.text for p in Document(out).paragraphs)
    assert '{{ Фамилия }}' in body
    assert '{{ Должность }}' in body


def test_cli_reverse_row_out_of_range_exits_one(tmp_path: Path) -> None:
    # Заодно проверяет, что `row` доехал до библиотеки как номер строки, а не
    # перепутался с `config`/`sheet`: иначе диапазон не проверится.
    table = _make_xlsx(tmp_path / 'emp.xlsx', [['Иванов']], ['Фамилия'])
    sample = _sample_doc(tmp_path / 'sample.docx', 'Иванов.')
    result = CliRunner().invoke(
        app,
        [
            'reverse',
            '--doc',
            str(sample),
            '--table',
            str(table),
            '--row',
            '5',
            '--out',
            str(tmp_path / 'tpl.docx'),
        ],
    )
    assert result.exit_code == 1
    assert 'диапазона' in result.output
