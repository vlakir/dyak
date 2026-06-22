"""Тесты распознавания колонок, разбора ФИО и нормализации (T006 + T016)."""

from __future__ import annotations

import logging

import pytest

from dyak.columns import (
    infer_role,
    normalize_header,
    recognize,
    split_fullname,
)
from dyak.inflection.morph import get_analyzer


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


# --- T016: контентное распознавание ролей по содержимому ----------------------


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('Иванов', 'surname'),
        ('Пётр', 'name'),
        ('Семёнович', 'patronymic'),
        ('директор', 'position'),
        ('главный бухгалтер', 'position'),
        ('майор', 'rank'),
        ('капитан 3 ранга', 'rank'),
        ('контр-адмирал', 'rank'),
        ('12.05.2020', None),  # дата → не роль склонения
        ('2020-05-12', None),
        ('1234567', 'personal_number'),
        ('АА-123456', 'personal_number'),
        ('Иванов Пётр Семёнович', 'fullname'),
        ('Шевченко', 'surname'),  # несклоняемая — роль всё равно verna
        ('Дюма', 'surname'),
        ('', None),
    ],
)
def test_infer_role_single_sample(value: str, expected: str | None) -> None:
    guess = infer_role([value], get_analyzer())
    assert guess.role == expected


def test_infer_role_majority_and_confidence() -> None:
    samples = ['Иванов', 'Петров', 'Сидоров', 'директор']
    guess = infer_role(samples, get_analyzer())
    assert guess.role == 'surname'
    assert guess.confident is True  # 3/4 ≥ 0.6
    assert guess.unanimous is False
    assert guess.n == len(samples)


def test_infer_role_empty_samples() -> None:
    guess = infer_role(['', '   '], get_analyzer())
    assert guess.role is None
    assert guess.n == 0


def test_content_recognizes_nonstandard_headers_without_aliases() -> None:
    # Заголовки незнакомы словарю синонимов — роль по содержимому.
    samples = {
        'Сотрудник': [
            'Иванов Пётр Семёнович',
            'Петрова Анна Сергеевна',
            'Ким Олег Викторович',
        ],
        'Наименование_должности': ['директор', 'бухгалтер', 'инженер'],
        'Дата_приказа': ['12.05.2020', '13.05.2020', '14.05.2020'],
    }
    rec = recognize(list(samples), {}, samples)
    assert rec.fullname_source == 'Сотрудник'
    assert rec.roles['position'] == 'Наименование_должности'
    assert rec.roles['surname'] == 'Фамилия'  # разбор ФИО
    assert 'Дата_приказа' not in rec.roles.values()  # дата без роли


def test_content_recognizes_rank_and_personal_number() -> None:
    samples = {
        'Кому_присвоено': ['майор', 'капитан', 'полковник'],
        'Идентификатор': ['1234567', '7654321', 'АА-099887'],
    }
    rec = recognize(list(samples), {}, samples)
    assert rec.roles['rank'] == 'Кому_присвоено'
    assert rec.roles['personal_number'] == 'Идентификатор'


def test_alias_beats_content_guess() -> None:
    # Содержимое — фамилии, но alias жёстко назначает position.
    samples = {'Колонка': ['Иванов', 'Петров', 'Сидоров']}
    rec = recognize(['Колонка'], {'Колонка': 'position'}, samples)
    assert rec.roles == {'position': 'Колонка'}


def test_content_overrides_header_only_when_unanimous() -> None:
    # Заголовок «Имя», но ВСЕ ячейки — явные должности, имя не подтверждено
    # ни в одной → жёсткий порог срабатывает, контент перебивает.
    samples = {'Имя': ['директор', 'бухгалтер', 'инженер', 'слесарь']}
    rec = recognize(['Имя'], {}, samples)
    assert rec.roles == {'position': 'Имя'}


def test_header_wins_when_content_confirms_it() -> None:
    # Заголовок «Имя», содержимое — имена → заголовок остаётся.
    samples = {'Имя': ['Пётр', 'Анна', 'Олег']}
    rec = recognize(['Имя'], {}, samples)
    assert rec.roles == {'name': 'Имя'}


def test_header_wins_when_content_not_unanimous() -> None:
    # Заголовок «Имя», содержимое смешанное (имя подтверждено в части ячеек)
    # → жёсткий порог НЕ срабатывает, заголовок главнее.
    samples = {'Имя': ['Пётр', 'директор', 'инженер']}
    rec = recognize(['Имя'], {}, samples)
    assert rec.roles == {'name': 'Имя'}


def test_ambiguous_content_best_guess_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Незнакомый заголовок, образцы расходятся (нет ≥60% согласия) →
    # лучшая догадка + предупреждение.
    samples = {'Поле': ['Иванов', 'директор']}
    with caplog.at_level(logging.WARNING):
        rec = recognize(['Поле'], {}, samples)
    # Ровно одна роль-догадка (не пусто) из допустимого набора.
    assert len(rec.roles) == 1
    assert set(rec.roles) <= {'surname', 'position'}
    assert any('неуверенно' in r.message for r in caplog.records)


def test_no_samples_behaves_as_header_only() -> None:
    # Без образцов (или пустой samples) — поведение T006, pymorphy не зовётся.
    rec = recognize(['Фамилия', 'Прочее'], {}, {})
    assert rec.roles == {'surname': 'Фамилия'}
