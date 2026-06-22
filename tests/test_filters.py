"""Тесты русских падежных фильтров Jinja и контекста со склонением (T002)."""

from __future__ import annotations

import jinja2
import pytest

from dyak.domain import Case, Gender, Person
from dyak.errors import TemplateError
from dyak.inflection import PetrovichInflector, PymorphyInflector
from dyak.render.context import build_context, normalize_lookup_key
from dyak.render.filters import agree_by_gender, build_jinja_env, make_case_filter


@pytest.fixture(scope='module')
def inflector() -> PetrovichInflector:
    return PetrovichInflector()


def _ctx(inflector: PetrovichInflector, **extra: object) -> dict[str, object]:
    person = Person(
        cells={
            'Фамилия': 'Иванов',
            'Имя': 'Пётр',
            'Отчество': 'Семёнович',
            'Должность': 'директор',
        },
    )
    roles = {
        'surname': 'Фамилия',
        'name': 'Имя',
        'patronymic': 'Отчество',
        'position': 'Должность',
    }
    return build_context(person, roles=roles, inflector=inflector, **extra)


def test_make_case_filter_inflects_declinable(inflector: PetrovichInflector) -> None:
    ctx = _ctx(inflector)
    genitive = make_case_filter(Case.GENT)
    assert genitive(ctx['Фамилия']) == 'Иванова'


def test_make_case_filter_passthrough_for_plain_string() -> None:
    # Должность в T002 — обычная строка; фильтр падежа отдаёт её как есть.
    genitive = make_case_filter(Case.GENT)
    assert genitive('директор') == 'директор'


def test_agree_by_gender_picks_form(inflector: PetrovichInflector) -> None:
    male = _ctx(inflector)['ФИО']
    female = build_context(
        Person(cells={'Фамилия': 'Петрова', 'Имя': 'Анна', 'Отчество': 'Сергеевна'}),
        roles={'surname': 'Фамилия', 'name': 'Имя', 'patronymic': 'Отчество'},
        inflector=inflector,
    )['ФИО']
    assert agree_by_gender(male, 'назначен', 'назначена') == 'назначен'
    assert agree_by_gender(female, 'назначен', 'назначена') == 'назначена'


def test_agree_by_gender_renders_in_template(inflector: PetrovichInflector) -> None:
    env = build_jinja_env()
    ctx = _ctx(inflector)
    tpl = env.from_string("{{ ФИО | согл('ознакомлен', 'ознакомлена') }}")
    assert tpl.render(ctx) == 'ознакомлен'


def test_agree_by_gender_rejects_non_fio() -> None:
    with pytest.raises(TemplateError, match='согл'):
        agree_by_gender('директор', 'м', 'ж')


def test_strict_undefined_raises_in_template(inflector: PetrovichInflector) -> None:
    env = build_jinja_env()
    with pytest.raises(jinja2.UndefinedError):
        env.from_string('{{ Неизвестно }}').render(_ctx(inflector))


def test_jinja_env_renders_fio_filters(inflector: PetrovichInflector) -> None:
    env = build_jinja_env()
    ctx = _ctx(inflector)
    tpl = env.from_string('{{ ФИО | вн }} — {{ Фамилия | дт }}')
    assert tpl.render(ctx) == 'Иванова Петра Семёновича — Иванову'


def test_jinja_env_renders_initials(inflector: PetrovichInflector) -> None:
    env = build_jinja_env()
    ctx = _ctx(inflector)
    tpl = env.from_string('{{ ФИО.инициалы_впереди }}')
    assert tpl.render(ctx) == 'П. С. Иванов'


def test_bare_fio_renders_nominative(inflector: PetrovichInflector) -> None:
    env = build_jinja_env()
    ctx = _ctx(inflector)
    assert env.from_string('{{ ФИО }}').render(ctx) == 'Иванов Пётр Семёнович'


def test_context_builds_fio_from_fullname_column(inflector: PetrovichInflector) -> None:
    person = Person(cells={'ФИО': 'Петрова Анна Сергеевна'})
    ctx = build_context(
        person,
        fullname_source='ФИО',
        roles={'surname': 'Фамилия', 'name': 'Имя', 'patronymic': 'Отчество'},
        inflector=inflector,
    )
    assert ctx['Фамилия'].inflect(Case.GENT) == 'Петровой'
    assert str(ctx['ФИО']) == 'Петрова Анна Сергеевна'
    assert ctx['ФИО'].inflect(Case.ACCS) == 'Петрову Анну Сергеевну'


def test_context_gender_override_applies(inflector: PetrovichInflector) -> None:
    # «Саша Ким» неоднозначно — override делает женский (фамилия не склоняется).
    person = Person(cells={'Фамилия': 'Ким', 'Имя': 'Саша', 'Отчество': ''})
    overrides = {normalize_lookup_key('Ким Саша'): Gender.FEMALE}
    ctx = build_context(
        person,
        roles={'surname': 'Фамилия', 'name': 'Имя', 'patronymic': 'Отчество'},
        inflector=inflector,
        gender_overrides=overrides,
    )
    assert ctx['Фамилия'].inflect(Case.DATV) == 'Ким'


def test_context_without_name_roles_stays_flat(inflector: PetrovichInflector) -> None:
    person = Person(cells={'Дата_начала': '01.07.2026', 'Номер': '17'})
    ctx = build_context(person, roles={}, inflector=inflector)
    assert ctx == {'Дата_начала': '01.07.2026', 'Номер': '17'}
    assert 'ФИО' not in ctx


def test_position_declines_in_template(inflector: PetrovichInflector) -> None:
    # T003: должность под падежным фильтром склоняется (раньше проходила как есть).
    ctx = _ctx(inflector, position_inflector=PymorphyInflector())
    env = build_jinja_env()
    tpl = env.from_string('на должность {{ Должность | рд }}')
    assert tpl.render(ctx) == 'на должность директора'


def test_position_override_applies_in_context(inflector: PetrovichInflector) -> None:
    person = Person(cells={'Должность': 'заместитель генерального директора'})
    key = normalize_lookup_key('Заместитель генерального директора')
    ctx = build_context(
        person,
        roles={'position': 'Должность'},
        inflector=inflector,
        position_inflector=PymorphyInflector(),
        position_overrides={key: {'дт': 'заместителю генерального директора'}},
    )
    assert ctx['Должность'].inflect(Case.DATV) == 'заместителю генерального директора'
