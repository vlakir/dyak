"""
Автоопределение пола сотрудника (ADR 2026-06-21, замена колонки «Пол»).

Источники из ADR — ручной `override` и авто-цепочка «отчество → имя».
Приоритет (фактический в коде): **override → отчество → имя → дефолт**.
Ручное указание (если задано) перекрывает автоматику — это и есть смысл
«escape-hatch для неоднозначных» из ADR.

0. Ручной `override` из `dyak.yaml` (секция `genders`) — высший приоритет;
   если задан, остальное не считаем.
1. Окончание отчества решает почти всё детерминированно: `-вич/-ич/-ыч`
   → мужской, `-вна/-чна` → женский.
2. Нет отчества или оно нестандартное — пробуем имя через `pymorphy3`
   (`masc`/`femn`). Имена вроде «Саша», «Женя» дают `None` (неоднозначно).
3. Иначе дефолт «мужской» + предупреждение (зерно сигнала для отчёта
   `check` в T004); такие имена и стоит закрывать `override`.

`MorphAnalyzer` дорог в создании, поэтому кешируется (`functools.cache`):
загружается только если реально дошли до шага 2. Импорт `pymorphy3` — в
шапке модуля (правило импортов), отложена лишь инстанциация.
"""

from __future__ import annotations

import logging

from dyak.domain import Gender
from dyak.inflection.morph import get_analyzer

logger = logging.getLogger(__name__)

# Окончания отчеств (нормализованные, нижний регистр).
_MALE_PATRONYMIC = ('ич', 'ыч')  # Семёнович, Кузьмич, Лукич, Фомич
_FEMALE_PATRONYMIC = ('вна', 'чна')  # Семёновна, Ильинична, Кузьминична

# Распознавание ручного указания пола (`genders` в конфиге).
_MALE_WORDS = frozenset({'м', 'муж', 'мужской', 'male', 'm'})
_FEMALE_WORDS = frozenset({'ж', 'жен', 'женский', 'female', 'f'})


def parse_gender(text: str) -> Gender | None:
    """Разобрать ручное значение пола (`м`/`ж`/`male`/…) или вернуть `None`."""
    token = text.strip().lower()
    if token in _MALE_WORDS:
        return Gender.MALE
    if token in _FEMALE_WORDS:
        return Gender.FEMALE
    return None


def _by_patronymic(patronymic: str) -> Gender | None:
    token = patronymic.strip().lower()
    if not token:
        return None
    if token.endswith(_FEMALE_PATRONYMIC):
        return Gender.FEMALE
    if token.endswith(_MALE_PATRONYMIC):
        return Gender.MALE
    return None


def _by_name(name: str) -> Gender | None:
    token = name.strip()
    if not token:
        return None
    tag = get_analyzer().parse(token)[0].tag
    if tag.gender == 'masc':
        return Gender.MALE
    if tag.gender == 'femn':
        return Gender.FEMALE
    return None


def detect_gender(
    name: str,
    patronymic: str,
    *,
    override: Gender | None = None,
) -> Gender:
    """Определить пол: отчество → имя → override → дефолт «мужской»."""
    if override is not None:
        return override
    by_patronymic = _by_patronymic(patronymic)
    if by_patronymic is not None:
        return by_patronymic
    by_name = _by_name(name)
    if by_name is not None:
        return by_name
    logger.warning(
        'Не удалось определить пол для «%s %s» — беру мужской по умолчанию; '
        'уточните в секции `genders` конфига при необходимости',
        name,
        patronymic,
    )
    return Gender.MALE
