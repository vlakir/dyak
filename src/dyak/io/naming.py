"""
Разрешение коллизий имён выходных файлов (§12).

При совпадении имени к основе добавляется числовой суффикс `_2`, `_3`, …
с предупреждением в лог. `used` накапливает занятые имена в пределах
одного прогона.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def unique_filename(name: str, used: set[str]) -> str:
    """Вернуть имя, не пересекающееся с `used`; занять его в `used`."""
    if name not in used:
        used.add(name)
        return name

    path = Path(name)
    stem, suffix = path.stem, path.suffix
    counter = 2
    candidate = f'{stem}_{counter}{suffix}'
    while candidate in used:
        counter += 1
        candidate = f'{stem}_{counter}{suffix}'

    logger.warning('Коллизия имени «%s» — сохраняю как «%s»', name, candidate)
    used.add(candidate)
    return candidate
