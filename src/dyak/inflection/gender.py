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
from dataclasses import dataclass
from enum import StrEnum

from dyak.domain import Gender
from dyak.inflection.morph import get_analyzer

logger = logging.getLogger(__name__)


class GenderSource(StrEnum):
    """Откуда взят пол — для отчёта `check` (T004)."""

    OVERRIDE = 'override'  # ручное указание в `genders`
    PATRONYMIC = 'patronymic'  # по окончанию отчества
    NAME = 'name'  # по имени (pymorphy)
    DEFAULT = 'default'  # не определён, взят мужской по умолчанию


@dataclass(frozen=True, slots=True)
class GenderResolution:
    """Результат определения пола: значение + источник (уверенность)."""

    gender: Gender
    source: GenderSource

    @property
    def is_confident(self) -> bool:
        """Уверенно ли определён пол (не дефолт-заглушка)."""
        return self.source is not GenderSource.DEFAULT


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


def resolve_gender(
    name: str,
    patronymic: str,
    *,
    override: Gender | None = None,
) -> GenderResolution:
    """Определить пол с источником: override → отчество → имя → дефолт."""
    if override is not None:
        return GenderResolution(override, GenderSource.OVERRIDE)
    by_patronymic = _by_patronymic(patronymic)
    if by_patronymic is not None:
        return GenderResolution(by_patronymic, GenderSource.PATRONYMIC)
    by_name = _by_name(name)
    if by_name is not None:
        return GenderResolution(by_name, GenderSource.NAME)
    return GenderResolution(Gender.MALE, GenderSource.DEFAULT)


def detect_gender(
    name: str,
    patronymic: str,
    *,
    override: Gender | None = None,
) -> Gender:
    """Пол для горячего пути (с предупреждением при дефолте)."""
    resolution = resolve_gender(name, patronymic, override=override)
    if resolution.source is GenderSource.DEFAULT:
        logger.warning(
            'Не удалось определить пол для «%s %s» — беру мужской по умолчанию; '
            'уточните в секции `genders` конфига при необходимости',
            name,
            patronymic,
        )
    return resolution.gender
