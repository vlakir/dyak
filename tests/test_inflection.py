"""Тесты склонения ФИО: petrovich-обёртка, NamePart, Fio, инициалы (T002)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from petrovich.enums import Case as PCase
from petrovich.enums import Gender as PGender
from petrovich.main import DEFAULT_RULES_PATH, Petrovich

from dyak.domain import Case, Gender
from dyak.inflection import (
    Fio,
    Initials,
    NamePart,
    PetrovichInflector,
    is_known_surname,
)

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


def test_utf8_rules_load_fixes_locale_decode(inflector: PetrovichInflector) -> None:
    """Регрессия T021: правила читаются UTF-8, а не локальной кодировкой.

    На русской Windows дефолтный `open()` берёт `cp1251`: UTF-8-кириллица в
    суффиксах `rules.json` мис-декодируется, тесты правил не совпадают, фамилия
    проходит несклонённой. Воспроизводим механизм (cp1251-загрузка молча не
    склоняет) и подтверждаем, что наша UTF-8-обёртка склоняет.
    """
    broken = Petrovich.__new__(Petrovich)
    with Path(DEFAULT_RULES_PATH).open(encoding='cp1251') as fp:
        broken.data = json.load(fp)
    # Старый путь: cp1251 ломает правила → фамилия не склоняется (баг T021).
    assert broken.lastname('Пупкин', PCase.DATIVE, PGender.MALE) == 'Пупкин'
    # Фикс: UTF-8-обёртка (внутри `PetrovichInflector`) склоняет.
    part = NamePart('Пупкин', 'surname', Gender.MALE, inflector)
    assert part.inflect(Case.DATV) == 'Пупкину'


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


# --- T027: фамилии-нарицательные не склоняются по умолчанию --------------------


def test_is_known_surname_signal() -> None:
    # Обычные фамилии — pymorphy знает их как фамилии (грамема Surn).
    assert is_known_surname('Иванов')
    assert is_known_surname('Соколов')
    assert is_known_surname('БИВЕНЬ') is False  # нарицательное, не опознано
    assert is_known_surname('Кузнец') is False


def test_common_noun_surname_stays_nominative(inflector: PetrovichInflector) -> None:
    # T027: фамилия-нарицательное (Бивень) по умолчанию НЕ склоняется.
    part = NamePart('Бивень', 'surname', Gender.MALE, inflector)
    assert part.inflect(Case.DATV) == 'Бивень'
    assert part.inflect(Case.GENT) == 'Бивень'
    # Обычная фамилия рядом — склоняется как обычно.
    normal = NamePart('Иванов', 'surname', Gender.MALE, inflector)
    assert normal.inflect(Case.DATV) == 'Иванову'


def test_force_decline_overrides_rule(inflector: PetrovichInflector) -> None:
    # Обход (список decline_surnames конфига): всё-таки склонять.
    part = NamePart('Бивень', 'surname', Gender.MALE, inflector, force_decline=True)
    assert part.inflect(Case.DATV) == 'Бивеню'


def test_rule_applies_only_to_surnames(inflector: PetrovichInflector) -> None:
    # Имя/отчество правилом не затронуты (склоняются по petrovich как раньше).
    name = NamePart('Пётр', 'name', Gender.MALE, inflector)
    assert name.inflect(Case.DATV) == 'Петру'


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
