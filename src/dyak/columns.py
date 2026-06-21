"""
Распознавание колонок таблицы (T006).

Контекст шаблона строится напрямую по заголовкам колонок: заголовок
нормализуется (пробелы → `_`) и становится ключом Jinja-переменной.
Стандартные кадровые колонки (фамилия/имя/отчество/должность) дополнительно
распознаются по названию и получают «роль» — это фундамент маршрутизации
склонения в T002. Нестандартные заголовки можно привязать к роли через
секцию `aliases` в `dyak.yaml`.

Отдельный случай — **одна колонка «ФИО»** (частая форма кадровой таблицы):
она распознаётся как `fullname` и разбирается на фамилию/имя/отчество
(`split_fullname`). Тогда в контексте доступны и целое `{{ ФИО }}`, и
производные `{{ Фамилия }}`/`{{ Имя }}`/`{{ Отчество }}`. Если в ячейке два
слова — отчества нет (пустое); это сигнал для автоопределения пола в T002.

Роль — это контракт «заголовок → одна из surname/name/patronymic/position»,
поверх которого T002 навешивает движки склонения, не трогая T006.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)

# Роли склоняемых кадровых колонок (значения совпадают с `Role` в config.py).
SURNAME = 'surname'
NAME = 'name'
PATRONYMIC = 'patronymic'
POSITION = 'position'
FULLNAME = 'fullname'

# Канонические ключи контекста для частей ФИО, разобранных из одной колонки.
KEY_SURNAME = 'Фамилия'
KEY_NAME = 'Имя'
KEY_PATRONYMIC = 'Отчество'

# Синонимы заголовков → роль (нормализованный заголовок в нижнем регистре).
_SYNONYMS = {
    'фамилия': SURNAME,
    'имя': NAME,
    'отчество': PATRONYMIC,
    'должность': POSITION,
    'позиция': POSITION,
    'фио': FULLNAME,
    'ф.и.о.': FULLNAME,
    'ф.и.о': FULLNAME,
    'фамилия_имя_отчество': FULLNAME,
}

# Роли, которые покрывает разбор одной колонки «ФИО».
_FIO_PARTS = frozenset({SURNAME, NAME, PATRONYMIC})

_WHITESPACE = re.compile(r'\s+')


@dataclass(frozen=True, slots=True)
class Recognition:
    """
    Результат распознавания колонок.

    `roles` — `роль → ключ контекста` (физический заголовок или, для разбора
    ФИО, канонический `Фамилия`/`Имя`/`Отчество`). `fullname_source` — ключ
    колонки «ФИО», которую надо разбирать построчно, либо `None`.
    """

    roles: dict[str, str]
    fullname_source: str | None


def normalize_header(raw: str) -> str:
    """Привести заголовок к Jinja-идентификатору: пробелы → подчёркивание."""
    return _WHITESPACE.sub('_', raw.strip())


def split_fullname(value: str) -> tuple[str, str, str]:
    """
    Разобрать ячейку «ФИО» на (фамилия, имя, отчество).

    Три слова → полное ФИО; два → без отчества (пустое); одно → только
    фамилия. Лишние слова (4-е и далее) приклеиваются к отчеству.
    """
    surname, *rest = value.split() or ['']
    name = rest[0] if rest else ''
    patronymic = ' '.join(rest[1:])
    return surname, name, patronymic


def recognize(
    headers: list[str],
    aliases: Mapping[str, str],
) -> Recognition:
    """
    Сопоставить нормализованным заголовкам роли (surname/name/...).

    `headers` — уже нормализованные ключи колонок. `aliases` — из конфига
    (сырой заголовок → роль). Первый заголовок, претендующий на роль,
    закрепляет её; повторные кандидаты на ту же роль игнорируются с
    предупреждением. Колонка `fullname` разбирается на части, только если в
    таблице нет отдельных колонок фамилии/имени/отчества.
    """
    alias_map = {normalize_header(k).lower(): v for k, v in aliases.items()}

    raw: dict[str, str] = {}
    for header in headers:
        key = header.lower()
        role = alias_map.get(key) or _SYNONYMS.get(key)
        if role is None:
            continue
        if role in raw:
            logger.warning(
                'Колонка «%s» претендует на роль «%s», уже занятую колонкой «%s» — '
                'игнорирую',
                header,
                role,
                raw[role],
            )
            continue
        raw[role] = header

    fullname_source = raw.pop(FULLNAME, None)
    roles = dict(raw)
    if fullname_source is not None and not (_FIO_PARTS & roles.keys()):
        roles[SURNAME] = KEY_SURNAME
        roles[NAME] = KEY_NAME
        roles[PATRONYMIC] = KEY_PATRONYMIC
    elif fullname_source is not None:
        # Есть отдельные колонки ФИО — колонку «ФИО» не разбираем, она
        # остаётся доступной как целый тег `{{ ФИО }}`.
        logger.warning(
            'Колонка «%s» и отдельные колонки фамилии/имени/отчества заданы '
            'одновременно — «%s» не разбираю, доступна целиком',
            fullname_source,
            fullname_source,
        )
        fullname_source = None
    return Recognition(roles=roles, fullname_source=fullname_source)
