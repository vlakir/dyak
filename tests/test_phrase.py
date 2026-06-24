"""Тесты универсального фраз-движка склонения (T024): движок + Phrase + override."""

from __future__ import annotations

import pytest

from dyak.domain import Case
from dyak.inflection import Declinable, Phrase, PhraseInflector
from dyak.inflection.morph import get_analyzer


@pytest.fixture(scope='module')
def inflector() -> PhraseInflector:
    return PhraseInflector()


@pytest.mark.parametrize(
    ('text', 'case', 'expected'),
    [
        # Одиночное слово.
        ('директор', Case.GENT, 'директора'),
        ('директор', Case.DATV, 'директору'),
        ('директор', Case.ABLT, 'директором'),
        ('командир', Case.DATV, 'командиру'),
        # Согласование прилагательного с головой.
        ('главный бухгалтер', Case.GENT, 'главного бухгалтера'),
        ('главный бухгалтер', Case.ABLT, 'главным бухгалтером'),
        ('старший техник', Case.DATV, 'старшему технику'),
        ('младший научный сотрудник', Case.DATV, 'младшему научному сотруднику'),
        # Замороженный родительный хвост (T022).
        ('рота связи', Case.ACCS, 'роту связи'),
        ('рота связи', Case.DATV, 'роте связи'),
        ('взвод охраны', Case.DATV, 'взводу охраны'),
        ('начальник штаба', Case.GENT, 'начальника штаба'),
        ('заместитель командира роты', Case.DATV, 'заместителю командира роты'),
        ('помощник начальника штаба', Case.DATV, 'помощнику начальника штаба'),
        # Одушевлённость в винительном (неодуш. муж./ср.: вн = им.).
        ('танковый батальон', Case.ACCS, 'танковый батальон'),
        ('1 мотострелковый батальон', Case.ACCS, '1 мотострелковый батальон'),
        ('1 мотострелковый батальон', Case.DATV, '1 мотострелковому батальону'),
        # Тесный дефис: известная лексема — целиком, иначе — каждая часть.
        ('инженер-программист', Case.GENT, 'инженера-программиста'),
        ('механик-водитель', Case.DATV, 'механику-водителю'),
        ('стрелок-радист', Case.DATV, 'стрелку-радисту'),
        ('генерал-майор', Case.DATV, 'генерал-майору'),
        # Разделитель-с-пробелами → две параллельных должности (символ-в-символ).
        (
            'телефонист - линейный надсмотрщик',
            Case.DATV,
            'телефонисту - линейному надсмотрщику',
        ),
        (
            'начальник штаба — заместитель командира',
            Case.DATV,
            'начальнику штаба — заместителю командира',
        ),
    ],
)
def test_phrase_declension(
    text: str, case: Case, expected: str, inflector: PhraseInflector
) -> None:
    assert inflector.inflect(text, case) == expected


def test_nominative_returns_source(inflector: PhraseInflector) -> None:
    assert inflector.inflect('рота связи', Case.NOMN) == 'рота связи'


def test_empty_text_returns_empty(inflector: PhraseInflector) -> None:
    assert inflector.inflect('', Case.GENT) == ''


def test_unparsable_token_kept_as_is(inflector: PhraseInflector) -> None:
    # Цифры/непонятные токены не склоняются — остаются как есть.
    assert inflector.inflect('грейд 7', Case.GENT) == 'грейда 7'


def test_dash_separator_preserved_char_for_char(inflector: PhraseInflector) -> None:
    # Разные чёрточки с пробелами сохраняются символ-в-символ (en-dash).
    assert (
        inflector.inflect('сменный – подменный', Case.DATV)
        == 'сменному – подменному'
    )


def test_phrase_str_is_nominative(inflector: PhraseInflector) -> None:
    assert str(Phrase('рота связи', inflector)) == 'рота связи'


def test_phrase_uses_engine_without_override(inflector: PhraseInflector) -> None:
    assert Phrase('рота связи', inflector).inflect(Case.ACCS) == 'роту связи'


def test_phrase_override_wins_over_engine(inflector: PhraseInflector) -> None:
    forms = {
        'рд': 'заместителя генерального директора',
        'дт': 'заместителю генерального директора',
    }
    phrase = Phrase('заместитель генерального директора', inflector, forms)
    assert phrase.inflect(Case.GENT) == 'заместителя генерального директора'
    assert phrase.inflect(Case.DATV) == 'заместителю генерального директора'


def test_phrase_partial_override_falls_back_to_engine(
    inflector: PhraseInflector,
) -> None:
    phrase = Phrase('главный бухгалтер', inflector, {'дт': 'главбуху'})
    assert phrase.inflect(Case.DATV) == 'главбуху'  # override
    assert phrase.inflect(Case.GENT) == 'главного бухгалтера'  # движок


def test_analyzer_is_singleton() -> None:
    assert get_analyzer() is get_analyzer()


def test_phrase_is_declinable(inflector: PhraseInflector) -> None:
    assert isinstance(Phrase('директор', inflector), Declinable)
