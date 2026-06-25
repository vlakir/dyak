"""Тесты сухого прогона `dyak check`: отчёт о склонении/поле/шаблоне (T004)."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from dyak.check import CheckReport, IssueKind, check_table, format_report
from dyak.domain import Gender, Person, Table
from dyak.render.context import normalize_lookup_key

_ROLES = {
    'surname': 'Фамилия',
    'name': 'Имя',
    'patronymic': 'Отчество',
    'position': 'Должность',
}


def _template(
    tmp_path: Path, body: str = '{{ ФИО | вн }} {{ Должность | рд }}'
) -> Path:
    path = tmp_path / 'tpl.docx'
    doc = Document()
    doc.add_paragraph(body)
    doc.save(path)
    return path


def _table(*people: Person) -> Table:
    return Table(roles=_ROLES, fullname_source=None, people=list(people))


def _person(surname: str, name: str, patronymic: str, position: str) -> Person:
    return Person(
        cells={
            'Фамилия': surname,
            'Имя': name,
            'Отчество': patronymic,
            'Должность': position,
        },
    )


def _kinds(report: CheckReport) -> set[IssueKind]:
    return {issue.kind for issue in report.issues}


def test_clean_table_has_no_issues(tmp_path: Path) -> None:
    table = _table(_person('Иванов', 'Пётр', 'Семёнович', 'директор'))
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        position_overrides={},
        rank_overrides={},
    )
    assert report.ok
    assert not report.fatal
    assert report.rows == 1
    assert 'Проблем не найдено' in format_report(report)


def test_undefined_variable_is_fatal(tmp_path: Path) -> None:
    table = _table(_person('Иванов', 'Пётр', 'Семёнович', 'директор'))
    template = _template(tmp_path, '{{ Опечатка }}')
    report = check_table(
        table, template, gender_overrides={}, position_overrides={}, rank_overrides={}
    )
    assert report.fatal
    assert IssueKind.UNDEFINED in _kinds(report)
    assert any('Опечатка' in i.message for i in report.issues)


def test_filter_misuse_reported_as_template_not_undefined(tmp_path: Path) -> None:
    # `согл` применён к должности (не ФИО) → ошибка шаблона, но НЕ «undefined».
    table = _table(_person('Иванов', 'Пётр', 'Семёнович', 'директор'))
    template = _template(tmp_path, "{{ Должность | согл('м', 'ж') }}")
    report = check_table(
        table, template, gender_overrides={}, position_overrides={}, rank_overrides={}
    )
    assert IssueKind.TEMPLATE in _kinds(report)
    assert IssueKind.UNDEFINED not in _kinds(report)
    assert report.fatal  # шаблон не рендерится → всё равно фатально


def test_ambiguous_gender_reported(tmp_path: Path) -> None:
    table = _table(_person('Ким', 'Саша', '', 'директор'))
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        position_overrides={},
        rank_overrides={},
    )
    assert IssueKind.GENDER_AMBIGUOUS in _kinds(report)
    assert not report.fatal


def test_gender_mismatch_reported(tmp_path: Path) -> None:
    # Ручной пол ж, но отчество мужское → расхождение.
    table = _table(_person('Петров', 'Иван', 'Иванович', 'директор'))
    overrides = {normalize_lookup_key('Петров Иван Иванович'): Gender.FEMALE}
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides=overrides,
        position_overrides={},
        rank_overrides={},
    )
    assert IssueKind.GENDER_MISMATCH in _kinds(report)


def test_not_declined_position_reported(tmp_path: Path) -> None:
    # Аббревиатура-должность не склоняется → попадает в отчёт.
    table = _table(_person('Иванов', 'Пётр', 'Семёнович', 'СЕО'))
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        position_overrides={},
        rank_overrides={},
    )
    not_declined = [i for i in report.issues if i.kind is IssueKind.NOT_DECLINED]
    assert any('СЕО' in i.message for i in not_declined)


def test_position_override_suppresses_not_declined(tmp_path: Path) -> None:
    # С override должность «склоняется» → не во всех падежах совпадает с исходной.
    forms = {'рд': 'СЕО-директора', 'дт': 'СЕО-директору'}
    table = _table(_person('Иванов', 'Пётр', 'Семёнович', 'СЕО'))
    overrides = {normalize_lookup_key('СЕО'): forms}
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        position_overrides=overrides,
        rank_overrides={},
    )
    not_declined = [
        i
        for i in report.issues
        if i.kind is IssueKind.NOT_DECLINED and 'СЕО' in i.message
    ]
    assert not not_declined


def test_report_counts_rows(tmp_path: Path) -> None:
    table = _table(
        _person('Иванов', 'Пётр', 'Семёнович', 'директор'),
        _person('Петрова', 'Анна', 'Сергеевна', 'бухгалтер'),
    )
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        position_overrides={},
        rank_overrides={},
    )
    assert report.rows == 2


@pytest.mark.parametrize('fatal_kind', [IssueKind.UNDEFINED])
def test_report_format_lists_issues(tmp_path: Path, fatal_kind: IssueKind) -> None:
    table = _table(_person('Иванов', 'Пётр', 'Семёнович', 'директор'))
    report = check_table(
        table,
        _template(tmp_path, '{{ Х }}'),
        gender_overrides={},
        position_overrides={},
        rank_overrides={},
    )
    text = format_report(report)
    assert 'строка 1' in text
    assert fatal_kind in _kinds(report)


def test_common_noun_surname_flagged_with_hint(tmp_path: Path) -> None:
    # T027: фамилия-нарицательное оставлена в им. → отчёт с подсказкой про
    # `decline_surnames` (а не общий «добавьте override»).
    table = _table(_person('Бивень', 'Абрам', 'Моисеевич', 'директор'))
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        position_overrides={},
        rank_overrides={},
    )
    not_declined = [
        i.message for i in report.issues if i.kind is IssueKind.NOT_DECLINED
    ]
    assert any('Бивень' in m and 'decline_surnames' in m for m in not_declined)


def test_force_decline_suppresses_surname_flag(tmp_path: Path) -> None:
    # С decline_surnames фамилия склоняется → не попадает в отчёт.
    table = _table(_person('Бивень', 'Абрам', 'Моисеевич', 'директор'))
    report = check_table(
        table,
        _template(tmp_path),
        gender_overrides={},
        decline_surnames={normalize_lookup_key('Бивень')},
        position_overrides={},
        rank_overrides={},
    )
    assert not [
        i for i in report.issues
        if i.kind is IssueKind.NOT_DECLINED and 'Бивень' in i.message
    ]
