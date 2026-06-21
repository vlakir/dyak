"""Тесты рендера контекста, имени файла и docx (этап 0, T001)."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate

from dyak.config import Config
from dyak.domain import Person
from dyak.render.context import build_context
from dyak.render.engine import render_document, render_filename


def _config() -> Config:
    return Config.model_validate(
        {
            'columns': {
                'surname': 'Фамилия',
                'name': 'Имя',
                'patronymic': 'Отчество',
                'position': 'Должность',
                'gender': 'Пол',
            },
            'filename': 'Приказ_{{ сотрудник.фамилия }}.docx',
        },
    )


def _person() -> Person:
    return Person(
        surname='Иванов',
        name='Пётр',
        patronymic='Семёнович',
        position='директор',
        gender='м',
        extra={'дата_начала': '01.07.2026'},
    )


def test_build_context_exposes_facade_and_extra() -> None:
    ctx = build_context(_person())
    assert ctx['сотрудник']['фамилия'] == 'Иванов'
    assert ctx['сотрудник']['должность'] == 'директор'
    assert ctx['дата_начала'] == '01.07.2026'


def test_render_filename_substitutes_fields() -> None:
    ctx = build_context(_person())
    assert render_filename('Приказ_{{ сотрудник.фамилия }}.docx', ctx) == (
        'Приказ_Иванов.docx'
    )


def test_render_document_substitutes_into_docx(tmp_path: Path) -> None:
    template = tmp_path / 'tpl.docx'
    doc = Document()
    doc.add_paragraph('Назначить {{ сотрудник.фамилия }} {{ сотрудник.имя }}')
    doc.add_paragraph('с {{ дата_начала }}.')
    doc.save(template)

    out = tmp_path / 'out.docx'
    render_document(template, build_context(_person()), out)

    text = '\n'.join(p.text for p in Document(out).paragraphs)
    assert 'Назначить Иванов Пётр' in text
    assert 'с 01.07.2026.' in text


def test_render_document_runs_split_placeholder(tmp_path: Path) -> None:
    # docxtpl должен склеивать плейсхолдер, разрезанный по run'ам.
    template = tmp_path / 'tpl.docx'
    doc = Document()
    para = doc.add_paragraph()
    para.add_run('{{ сотрудник.')
    para.add_run('фамилия }}')
    doc.save(template)

    out = tmp_path / 'out.docx'
    render_document(template, build_context(_person()), out)
    text = '\n'.join(p.text for p in Document(out).paragraphs)
    assert 'Иванов' in text


def test_render_uses_template_object(tmp_path: Path) -> None:
    # Контроль: DocxTemplate действительно рендерит наш контекст.
    template = tmp_path / 'tpl.docx'
    doc = Document()
    doc.add_paragraph('{{ сотрудник.должность }}')
    doc.save(template)
    tpl = DocxTemplate(template)
    tpl.render({'сотрудник': {'должность': 'директор'}})
    out = tmp_path / 'o.docx'
    tpl.save(out)
    assert 'директор' in '\n'.join(p.text for p in Document(out).paragraphs)
