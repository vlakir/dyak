"""Тесты обратной генерации шаблона (`dyak reverse`, T007 фаза 1)."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from openpyxl import Workbook
from typer.testing import CliRunner

from dyak.cli import app, reverse_template
from dyak.domain import Person
from dyak.render.context import build_context
from dyak.render.engine import render_document
from dyak.reverse import FindingKind, build_template, format_report
from dyak.reverse.candidates import build_candidates
from dyak.reverse.docx_rewrite import flatten_runs, rewrite_paragraph
from dyak.reverse.matcher import find_spans
from dyak.reverse.report import Finding, ReverseReport


def _person(**cells: str) -> Person:
    return Person(cells=dict(cells))


def _paragraph_text(doc: Document) -> str:
    return '\n'.join(p.text for p in doc.paragraphs)


# --- candidates ---------------------------------------------------------------


def test_build_candidates_skips_empty_cells() -> None:
    person = _person(Фамилия='Иванов', Отчество='', Должность='  ')
    candidates = build_candidates(person)
    keys = {c.key for c in candidates}
    assert keys == {'Фамилия'}
    (cand,) = candidates
    assert cand.tag == '{{ Фамилия }}'
    assert cand.forms == ('Иванов',)


# --- matcher ------------------------------------------------------------------


def test_find_spans_exact_match() -> None:
    candidates = build_candidates(_person(Фамилия='Иванов'))
    (match,) = find_spans('Назначить Иванов', candidates)
    assert (match.start, match.end) == (10, 16)
    assert match.candidate.tag == '{{ Фамилия }}'


def test_find_spans_respects_word_boundary() -> None:
    # Значение «Иван» не должно совпасть внутри «Иванов» (склонённые/составные
    # формы — забота фазы 2, не точного матча).
    candidates = build_candidates(_person(Имя='Иван'))
    assert find_spans('Иванов', candidates) == []


def test_find_spans_inflected_form_not_matched() -> None:
    # «Иванову» (дат. падеж) не совпадает с именительным «Иванов».
    candidates = build_candidates(_person(Фамилия='Иванов'))
    assert find_spans('вручить Иванову', candidates) == []


def test_find_spans_prefers_longer_on_overlap() -> None:
    person = _person(Должность='главный бухгалтер', Слово='бухгалтер')
    matches = find_spans('главный бухгалтер', build_candidates(person))
    assert len(matches) == 1
    assert matches[0].candidate.key == 'Должность'


def test_find_spans_multiple_occurrences() -> None:
    candidates = build_candidates(_person(Город='Москва'))
    matches = find_spans('Москва — город Москва', candidates)
    assert [m.start for m in matches] == [0, 15]


# --- docx run-split rewriting -------------------------------------------------


def test_rewrite_run_split_keeps_tag_intact(tmp_path: Path) -> None:
    doc = Document()
    para = doc.add_paragraph()
    para.add_run('Назначить Ива')  # значение «Иванов» разрезано по run'ам
    para.add_run('нов на должность')

    full, bounds = flatten_runs(para)
    matches = find_spans(full, build_candidates(_person(Фамилия='Иванов')))
    rewrite_paragraph(para, full, bounds, matches)

    # Тег целиком в одном run — docxtpl увидит его неразрезанным.
    assert any('{{ Фамилия }}' in run.text for run in para.runs)
    assert para.text == 'Назначить {{ Фамилия }} на должность'

    # И forward-рендер шаблона воспроизводит исходный текст.
    template = tmp_path / 'tpl.docx'
    doc.save(template)
    out = tmp_path / 'out.docx'
    render_document(template, build_context(_person(Фамилия='Иванов')), out)
    assert 'Назначить Иванов на должность' in _paragraph_text(Document(out))


# --- engine end-to-end --------------------------------------------------------


def _sample_doc(path: Path, text: str) -> Path:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)
    return path


def test_build_template_replaces_flat_values_roundtrip(tmp_path: Path) -> None:
    person = _person(
        Фамилия='Иванов', Имя='Пётр', Должность='директор', Дата_начала='01.07.2026'
    )
    sample = _sample_doc(
        tmp_path / 'sample.docx',
        'Назначить Иванов Пётр на должность директор с 01.07.2026.',
    )
    document, report = build_template(sample, person)

    body = _paragraph_text(document)
    assert '{{ Фамилия }}' in body
    assert '{{ Дата_начала }}' in body
    assert report.replaced_count == 4
    assert report.of_kind(FindingKind.NOT_FOUND) == []

    # Round-trip: собранный шаблон воспроизводит исходный документ.
    template = tmp_path / 'tpl.docx'
    document.save(template)
    out = tmp_path / 'out.docx'
    render_document(template, build_context(person), out)
    assert (
        'Назначить Иванов Пётр на должность директор с 01.07.2026.'
        in _paragraph_text(Document(out))
    )


def test_build_template_reports_not_found(tmp_path: Path) -> None:
    person = _person(Фамилия='Иванов', Отчество='Семёнович')
    sample = _sample_doc(tmp_path / 'sample.docx', 'Уведомить Иванов.')
    _document, report = build_template(sample, person)

    not_found = report.of_kind(FindingKind.NOT_FOUND)
    assert any('Семёнович' in f.message for f in not_found)


def test_build_template_reports_unmatched_data(tmp_path: Path) -> None:
    # Дата в документе, которой нет в строке → unmatched_text.
    person = _person(Фамилия='Иванов')
    sample = _sample_doc(
        tmp_path / 'sample.docx', 'Иванов, приказ от 09.09.2099.'
    )
    _document, report = build_template(sample, person)

    unmatched = report.of_kind(FindingKind.UNMATCHED_TEXT)
    assert any('09.09.2099' in f.message for f in unmatched)


def test_build_template_rewrites_table_cells(tmp_path: Path) -> None:
    # Значения во вложенной таблице тоже переписываются.
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run('директор Иванов')
    sample = tmp_path / 'sample.docx'
    doc.save(sample)

    person = _person(Фамилия='Иванов', Должность='директор')
    document, _report = build_template(sample, person)
    cell_text = document.tables[0].cell(0, 0).text
    assert '{{ Фамилия }}' in cell_text
    assert '{{ Должность }}' in cell_text


# --- report formatting --------------------------------------------------------


def test_format_report_groups_sections() -> None:
    report = ReverseReport(
        findings=[
            Finding(FindingKind.REPLACED, 'Фамилия: «Иванов» → {{ Фамилия }}'),
            Finding(FindingKind.NOT_FOUND, 'Отчество: «Семёнович» не найдено'),
        ]
    )
    text = format_report(report)
    assert 'Заменено значений: 1' in text
    assert 'Заменено:' in text
    assert 'Не найдено в документе:' in text


# --- CLI ----------------------------------------------------------------------


def _xlsx(path: Path, headers: list[str], rows: list[list[str]]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def test_cli_reverse_builds_template(tmp_path: Path) -> None:
    table = _xlsx(
        tmp_path / 'emp.xlsx',
        ['Фамилия', 'Имя', 'Должность'],
        [['Иванов', 'Пётр', 'директор']],
    )
    sample = _sample_doc(tmp_path / 'sample.docx', 'Назначить Иванов на директор.')
    out = tmp_path / 'tpl.docx'
    result = CliRunner().invoke(
        app,
        [
            'reverse',
            '--doc', str(sample),
            '--table', str(table),
            '--row', '1',
            '--out', str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    body = _paragraph_text(Document(out))
    assert '{{ Фамилия }}' in body
    assert '{{ Должность }}' in body


def test_cli_reverse_row_out_of_range_exits_one(tmp_path: Path) -> None:
    table = _xlsx(tmp_path / 'emp.xlsx', ['Фамилия'], [['Иванов']])
    sample = _sample_doc(tmp_path / 'sample.docx', 'Иванов.')
    result = CliRunner().invoke(
        app,
        [
            'reverse',
            '--doc', str(sample),
            '--table', str(table),
            '--row', '5',
            '--out', str(tmp_path / 'tpl.docx'),
        ],
    )
    assert result.exit_code == 1
    assert 'диапазона' in result.output


def test_reverse_template_helper_returns_report(tmp_path: Path) -> None:
    table = _xlsx(tmp_path / 'emp.xlsx', ['Фамилия'], [['Иванов']])
    sample = _sample_doc(tmp_path / 'sample.docx', 'Иванов.')
    report = reverse_template(
        sample, table, tmp_path / 'tpl.docx', None, None, 1
    )
    assert report.replaced_count == 1
