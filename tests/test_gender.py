"""Тесты автоопределения пола (T002): отчество → имя → override → дефолт."""

from __future__ import annotations

import logging

import pytest

from dyak.domain import Gender
from dyak.inflection import GenderSource, detect_gender, parse_gender, resolve_gender


@pytest.mark.parametrize(
    ('patronymic', 'expected'),
    [
        ('Семёнович', Gender.MALE),
        ('Кузьмич', Gender.MALE),
        ('Ильич', Gender.MALE),
        ('Сергеевна', Gender.FEMALE),
        ('Ильинична', Gender.FEMALE),
        ('Кузьминична', Gender.FEMALE),
    ],
)
def test_gender_by_patronymic(patronymic: str, expected: Gender) -> None:
    # Имя нейтральное/чужого рода — отчество приоритетнее.
    assert detect_gender('Саша', patronymic) == expected


@pytest.mark.parametrize(
    ('name', 'expected'),
    [('Анна', Gender.FEMALE), ('Пётр', Gender.MALE), ('Ольга', Gender.FEMALE)],
)
def test_gender_by_name_when_no_patronymic(name: str, expected: Gender) -> None:
    assert detect_gender(name, '') == expected


def test_ambiguous_name_defaults_to_male_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = detect_gender('Саша', '')
    assert result == Gender.MALE
    assert any('Саша' in r.message for r in caplog.records)


def test_override_wins_over_detection() -> None:
    # Отчество мужское, но override явно задаёт женский.
    assert detect_gender('Саша', 'Семёнович', override=Gender.FEMALE) == Gender.FEMALE


def test_patronymic_wins_over_name() -> None:
    # «Анна» (femn по имени), но отчество мужское → мужской.
    assert detect_gender('Анна', 'Иванович') == Gender.MALE


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('м', Gender.MALE),
        ('муж', Gender.MALE),
        ('Мужской', Gender.MALE),
        ('male', Gender.MALE),
        ('ж', Gender.FEMALE),
        ('жен', Gender.FEMALE),
        ('Женский', Gender.FEMALE),
        ('female', Gender.FEMALE),
        ('непонятно', None),
        ('', None),
    ],
)
def test_parse_gender(text: str, expected: Gender | None) -> None:
    assert parse_gender(text) == expected


def test_resolve_gender_sources() -> None:
    assert resolve_gender('Анна', 'Сергеевна').source is GenderSource.PATRONYMIC
    assert resolve_gender('Анна', '').source is GenderSource.NAME
    assert resolve_gender('Саша', '').source is GenderSource.DEFAULT
    res = resolve_gender('Саша', 'Семёнович', override=Gender.FEMALE)
    assert res.source is GenderSource.OVERRIDE
    assert res.gender is Gender.FEMALE


def test_gender_resolution_is_confident() -> None:
    assert resolve_gender('Анна', 'Сергеевна').is_confident is True
    assert resolve_gender('Саша', '').is_confident is False
