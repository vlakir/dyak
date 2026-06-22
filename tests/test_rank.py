"""Тесты склонения воинских/служебных званий (T016, фаза B)."""

from __future__ import annotations

import pytest

from dyak.domain import Case, Person
from dyak.inflection import Rank, RankInflector
from dyak.render.context import build_context

_INFLECTOR = RankInflector()


@pytest.mark.parametrize(
    ('text', 'case', 'expected'),
    [
        # Простые однословные — регрессия не хуже движка должностей.
        ('полковник', Case.GENT, 'полковника'),
        ('майор', Case.DATV, 'майору'),
        ('мичман', Case.ABLT, 'мичманом'),
        # Согласованное прилагательное склоняется вместе с головой.
        ('старший лейтенант', Case.DATV, 'старшему лейтенанту'),
        ('младший сержант', Case.GENT, 'младшего сержанта'),
        # Составные: голова склоняется, генитивный хвост замирает.
        ('майор медицинской службы', Case.DATV, 'майору медицинской службы'),
        ('капитан 3 ранга', Case.DATV, 'капитану 3 ранга'),
        ('советник юстиции 1 класса', Case.DATV, 'советнику юстиции 1 класса'),
        # Слово «полиция» (рд=дт=пр) — в творительном раньше ломалось.
        ('майор полиции', Case.ABLT, 'майором полиции'),
        # Дефисные служебные части — склоняется только последний сегмент.
        ('контр-адмирал', Case.DATV, 'контр-адмиралу'),
        ('вице-адмирал', Case.ABLT, 'вице-адмиралом'),
        ('генерал-майор', Case.GENT, 'генерал-майора'),
        # Имя собственное в хвосте сохраняет регистр.
        ('маршал Российской Федерации', Case.DATV, 'маршалу Российской Федерации'),
        ('генерал армии', Case.GENT, 'генерала армии'),
        # Именительный — исходный текст; пустое — пустое.
        ('капитан 1 ранга', Case.NOMN, 'капитан 1 ранга'),
        ('', Case.DATV, ''),
    ],
)
def test_rank_inflection(text: str, case: Case, expected: str) -> None:
    assert _INFLECTOR.inflect(text, case) == expected


def test_rank_tail_frozen_in_all_oblique_cases() -> None:
    # Хвост «медицинской службы» остаётся в родительном во всех косвенных.
    oblique = (Case.GENT, Case.DATV, Case.ACCS, Case.ABLT, Case.LOCT)
    for case in oblique:
        assert _INFLECTOR.inflect('майор медицинской службы', case).endswith(
            'медицинской службы'
        )


def test_rank_object_override_beats_engine() -> None:
    rank = Rank('капитан 2 ранга', _INFLECTOR, {'дт': 'капитану второго ранга'})
    assert rank.inflect(Case.DATV) == 'капитану второго ранга'
    # Падеж без override — движок.
    assert rank.inflect(Case.GENT) == 'капитана 2 ранга'


def test_rank_object_str_is_nominative() -> None:
    rank = Rank('майор медицинской службы', _INFLECTOR)
    assert str(rank) == 'майор медицинской службы'
    assert rank.inflect(Case.NOMN) == 'майор медицинской службы'


def test_rank_routed_into_context_and_declines() -> None:
    person = Person(cells={'Звание': 'майор медицинской службы', 'Фамилия': 'Петров'})
    context = build_context(
        person,
        roles={'rank': 'Звание'},
        rank_inflector=_INFLECTOR,
    )
    rank = context['Звание']
    assert isinstance(rank, Rank)
    assert rank.inflect(Case.DATV) == 'майору медицинской службы'
