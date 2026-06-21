"""Тесты распознавания колонок, разбора ФИО и нормализации (T006)."""

from __future__ import annotations

import logging

import pytest

from dyak.columns import normalize_header, recognize, split_fullname


def test_normalize_collapses_spaces() -> None:
    assert normalize_header('Дата начала') == 'Дата_начала'
    assert normalize_header('  Номер   приказа  ') == 'Номер_приказа'
    assert normalize_header('Фамилия') == 'Фамилия'


def test_recognizes_standard_roles() -> None:
    headers = ['Фамилия', 'Имя', 'Отчество', 'Должность', 'Дата_начала']
    rec = recognize(headers, {})
    assert rec.roles == {
        'surname': 'Фамилия',
        'name': 'Имя',
        'patronymic': 'Отчество',
        'position': 'Должность',
    }
    assert rec.fullname_source is None


def test_recognition_is_case_insensitive_and_synonyms() -> None:
    rec = recognize(['ФАМИЛИЯ', 'Позиция'], {})
    assert rec.roles == {'surname': 'ФАМИЛИЯ', 'position': 'Позиция'}


def test_alias_binds_nonstandard_header() -> None:
    rec = recognize(['Сотрудник', 'Прочее'], {'Сотрудник': 'surname'})
    assert rec.roles['surname'] == 'Сотрудник'


def test_alias_matches_after_normalization() -> None:
    rec = recognize(['Полное_имя'], {'Полное имя': 'name'})
    assert rec.roles == {'name': 'Полное_имя'}


def test_unrecognized_headers_have_no_roles() -> None:
    rec = recognize(['Дата_начала', 'Номер_приказа'], {})
    assert rec.roles == {}
    assert rec.fullname_source is None


def test_duplicate_role_first_wins_and_warns(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        rec = recognize(['Должность', 'Позиция'], {})
    assert rec.roles == {'position': 'Должность'}
    assert any('Позиция' in r.message for r in caplog.records)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('Иванов Пётр Семёнович', ('Иванов', 'Пётр', 'Семёнович')),
        ('Петрова Анна', ('Петрова', 'Анна', '')),
        ('Иванов', ('Иванов', '', '')),
        ('', ('', '', '')),
        ('  Ким   Олег  Викторович ', ('Ким', 'Олег', 'Викторович')),
        ('ИВАНОВ Пётр Семёнович', ('ИВАНОВ', 'Пётр', 'Семёнович')),
        ('Аль Хорезми Мухаммед ибн Муса', ('Аль', 'Хорезми', 'Мухаммед ибн Муса')),
    ],
)
def test_split_fullname(value: str, expected: tuple[str, str, str]) -> None:
    assert split_fullname(value) == expected


def test_fullname_column_recognized_and_split_source() -> None:
    rec = recognize(['ФИО', 'Должность'], {})
    assert rec.fullname_source == 'ФИО'
    assert rec.roles == {
        'surname': 'Фамилия',
        'name': 'Имя',
        'patronymic': 'Отчество',
        'position': 'Должность',
    }


def test_fullname_synonym_dotted() -> None:
    rec = recognize(['Ф.И.О.'], {})
    assert rec.fullname_source == 'Ф.И.О.'


def test_fullname_via_alias() -> None:
    rec = recognize(['Сотрудник'], {'Сотрудник': 'fullname'})
    assert rec.fullname_source == 'Сотрудник'
    assert rec.roles['surname'] == 'Фамилия'


def test_fullname_not_split_when_separate_columns_present(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        rec = recognize(['ФИО', 'Фамилия', 'Имя'], {})
    # Отдельные колонки имеют приоритет; «ФИО» не разбирается.
    assert rec.fullname_source is None
    assert rec.roles['surname'] == 'Фамилия'
    assert rec.roles['name'] == 'Имя'
    assert any('ФИО' in r.message for r in caplog.records)
