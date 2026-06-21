"""Тесты склонения должностей через pymorphy3: движок + Position + override (T003)."""

from __future__ import annotations

import pytest

from dyak.domain import Case
from dyak.inflection import Declinable, Position, PymorphyInflector
from dyak.inflection.morph import get_analyzer

_CASES = [
    ('рд', Case.GENT),
    ('дт', Case.DATV),
    ('вн', Case.ACCS),
    ('тв', Case.ABLT),
    ('пр', Case.LOCT),
]


@pytest.fixture(scope='module')
def inflector() -> PymorphyInflector:
    return PymorphyInflector()


@pytest.mark.parametrize(
    ('text', 'case', 'expected'),
    [
        ('директор', Case.GENT, 'директора'),
        ('директор', Case.DATV, 'директору'),
        ('директор', Case.ABLT, 'директором'),
        ('главный бухгалтер', Case.GENT, 'главного бухгалтера'),
        ('главный бухгалтер', Case.ABLT, 'главным бухгалтером'),
        ('инженер-программист', Case.GENT, 'инженера-программиста'),
        ('инженер-программист', Case.DATV, 'инженеру-программисту'),
    ],
)
def test_phrase_declension(
    text: str,
    case: Case,
    expected: str,
    inflector: PymorphyInflector,
) -> None:
    assert inflector.inflect(text, case) == expected


def test_nominative_returns_source(inflector: PymorphyInflector) -> None:
    assert inflector.inflect('главный бухгалтер', Case.NOMN) == 'главный бухгалтер'


def test_empty_text_returns_empty(inflector: PymorphyInflector) -> None:
    assert inflector.inflect('', Case.GENT) == ''


def test_unparsable_token_kept_as_is(inflector: PymorphyInflector) -> None:
    # Цифры/непонятные токены не склоняются — остаются как есть.
    assert inflector.inflect('грейд 7', Case.GENT) == 'грейда 7'


def test_position_str_is_nominative(inflector: PymorphyInflector) -> None:
    assert str(Position('директор', inflector)) == 'директор'


def test_position_uses_engine_without_override(inflector: PymorphyInflector) -> None:
    pos = Position('директор', inflector)
    assert pos.inflect(Case.GENT) == 'директора'


def test_position_override_wins_over_engine(inflector: PymorphyInflector) -> None:
    # Сложная фраза, которую пословный движок рассогласует в косвенных.
    forms = {
        'рд': 'заместителя генерального директора',
        'дт': 'заместителю генерального директора',
    }
    pos = Position('заместитель генерального директора', inflector, forms)
    assert pos.inflect(Case.GENT) == 'заместителя генерального директора'
    assert pos.inflect(Case.DATV) == 'заместителю генерального директора'


def test_position_partial_override_falls_back_to_engine(
    inflector: PymorphyInflector,
) -> None:
    # Задан только дт — остальные падежи берутся из движка.
    pos = Position('главный бухгалтер', inflector, {'дт': 'главбуху'})
    assert pos.inflect(Case.DATV) == 'главбуху'  # override
    assert pos.inflect(Case.GENT) == 'главного бухгалтера'  # движок


def test_analyzer_is_singleton() -> None:
    assert get_analyzer() is get_analyzer()


def test_position_is_declinable(inflector: PymorphyInflector) -> None:
    assert isinstance(Position('директор', inflector), Declinable)
