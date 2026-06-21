"""Тесты склонения ФИО: petrovich-обёртка, NamePart, Fio, инициалы (T002)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dyak.domain import Case, Gender
from dyak.inflection import Fio, Initials, NamePart, PetrovichInflector

_FIXTURE = Path(__file__).parent / 'fixtures' / 'declension.csv'
_CASES = [
    ('им', Case.NOMN),
    ('рд', Case.GENT),
    ('дт', Case.DATV),
    ('вн', Case.ACCS),
    ('тв', Case.ABLT),
    ('пр', Case.LOCT),
]


@pytest.fixture(scope='module')
def inflector() -> PetrovichInflector:
    return PetrovichInflector()


def _fio(row: dict[str, str], inflector: PetrovichInflector) -> Fio:
    gender = Gender.MALE if row['gender'] == 'male' else Gender.FEMALE
    return Fio(
        NamePart(row['surname'], 'surname', gender, inflector),
        NamePart(row['name'], 'name', gender, inflector),
        NamePart(row['patronymic'], 'patronymic', gender, inflector),
    )


def _fixture_rows() -> list[dict[str, str]]:
    with _FIXTURE.open(encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


@pytest.mark.parametrize('row', _fixture_rows(), ids=lambda r: f"{r['surname']}-{r['gender']}")
def test_declension_fixture(row: dict[str, str], inflector: PetrovichInflector) -> None:
    """Регрессия: все 6 падежей совпадают с эталоном (вкл. UPPERCASE, ж, нескл.)."""
    fio = _fio(row, inflector)
    for rus, case in _CASES:
        assert fio.inflect(case) == row[rus], f'{row["surname"]} {rus}'


def test_nominative_returns_source(inflector: PetrovichInflector) -> None:
    # petrovich не знает именительного — обёртка отдаёт исходный текст.
    part = NamePart('Иванов', 'surname', Gender.MALE, inflector)
    assert part.inflect(Case.NOMN) == 'Иванов'


def test_empty_part_is_empty_not_error(inflector: PetrovichInflector) -> None:
    # Пустая часть (нет отчества) не вызывает petrovich и не падает.
    part = NamePart('', 'patronymic', Gender.MALE, inflector)
    assert part.inflect(Case.GENT) == ''


def test_uppercase_surname_declines_uppercase(inflector: PetrovichInflector) -> None:
    part = NamePart('ИВАНОВ', 'surname', Gender.MALE, inflector)
    assert part.inflect(Case.GENT) == 'ИВАНОВА'
    assert part.inflect(Case.DATV) == 'ИВАНОВУ'


def test_namepart_str_is_nominative(inflector: PetrovichInflector) -> None:
    assert str(NamePart('Иванов', 'surname', Gender.MALE, inflector)) == 'Иванов'


def test_fio_str_is_full_nominative(inflector: PetrovichInflector) -> None:
    fio = _fio(
        {'surname': 'Иванов', 'name': 'Пётр', 'patronymic': 'Семёнович', 'gender': 'male'},
        inflector,
    )
    assert str(fio) == 'Иванов Пётр Семёнович'


def test_fio_drops_empty_patronymic(inflector: PetrovichInflector) -> None:
    fio = _fio(
        {'surname': 'Дюма', 'name': 'Александр', 'patronymic': '', 'gender': 'male'},
        inflector,
    )
    # Между именем и (отсутствующим) отчеством не остаётся хвостового пробела.
    assert fio.inflect(Case.GENT) == 'Дюма Александра'


def test_initials_three_forms(inflector: PetrovichInflector) -> None:
    fio = _fio(
        {'surname': 'Иванов', 'name': 'Пётр', 'patronymic': 'Семёнович', 'gender': 'male'},
        inflector,
    )
    assert str(fio.инициалы) == 'Иванов П. С.'
    assert str(fio.инициалы_впереди) == 'П. С. Иванов'
    assert str(fio.инициалы_слитно) == 'Иванов П.С.'


def test_initials_decline_surname_in_oblique_case(inflector: PetrovichInflector) -> None:
    fio = _fio(
        {'surname': 'Иванов', 'name': 'Пётр', 'patronymic': 'Семёнович', 'gender': 'male'},
        inflector,
    )
    assert fio.инициалы.inflect(Case.GENT) == 'Иванова П. С.'
    assert fio.инициалы_впереди.inflect(Case.DATV) == 'П. С. Иванову'


def test_initials_without_patronymic(inflector: PetrovichInflector) -> None:
    fio = _fio(
        {'surname': 'Петрова', 'name': 'Анна', 'patronymic': '', 'gender': 'female'},
        inflector,
    )
    assert str(fio.инициалы) == 'Петрова А.'


def test_initials_uppercase_letters_for_lowercase_name(
    inflector: PetrovichInflector,
) -> None:
    # Инициальные буквы всегда заглавные, даже если имя записано иначе.
    fio = _fio(
        {'surname': 'Иванов', 'name': 'пётр', 'patronymic': 'семёнович', 'gender': 'male'},
        inflector,
    )
    assert str(fio.инициалы) == 'Иванов П. С.'


def test_initials_is_declinable(inflector: PetrovichInflector) -> None:
    fio = _fio(
        {'surname': 'Иванов', 'name': 'Пётр', 'patronymic': 'Семёнович', 'gender': 'male'},
        inflector,
    )
    assert isinstance(fio.инициалы, Initials)
    assert hasattr(fio.инициалы, 'inflect')
