"""
`dyak init` — scaffold нового проекта генерации (T005).

Команда выкладывает в каталог пользователя готовый стартовый набор:
`dyak.yaml` (закомментированный пример конфига), `template.docx` (пример
шаблона приказа со шпаргалкой падежных фильтров) и `table.xlsx` (пример
таблицы сотрудников). Кадровик стартует с рабочего набора, а не с пустого
листа: достаточно подменить данные и текст шаблона.

Ассеты лежат рядом как **package-data** (`dyak/scaffold/`) и копируются
байт-в-байт через `importlib.resources` (ADR 2026-06-22) — это работает
и из исходников, и из собранного бандла (T010).
"""

from __future__ import annotations

import logging
from importlib import resources
from typing import TYPE_CHECKING

from dyak.errors import DyakError

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

# Ресурсный пакет с готовыми файлами scaffold-набора.
_SCAFFOLD_PACKAGE = 'dyak.scaffold'

# Имена файлов набора (имя ресурса = имя в целевом каталоге).
SCAFFOLD_FILES = ('dyak.yaml', 'template.docx', 'table.xlsx')


class ScaffoldExistsError(DyakError):
    """Целевой файл scaffold уже существует, а `--force` не передан."""


def init_project(target_dir: Path, *, force: bool) -> list[Path]:
    """
    Скопировать scaffold-набор в `target_dir`. Вернуть созданные пути.

    Коллизии проверяются до записи: если хоть один файл набора уже есть и
    `force` не задан — поднимаем `ScaffoldExistsError`, ничего не трогая
    (не оставляем каталог в полузаписанном состоянии).
    """
    if target_dir.exists() and not target_dir.is_dir():
        msg = f'Путь «{target_dir}» уже существует и не является каталогом.'
        raise DyakError(msg)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        reason = exc.strerror or str(exc)
        msg = f'Не удалось создать каталог «{target_dir}»: {reason}'
        raise DyakError(msg) from exc

    existing = [
        target_dir / name for name in SCAFFOLD_FILES if (target_dir / name).exists()
    ]
    if existing and not force:
        names = ', '.join(path.name for path in existing)
        msg = (
            f'В каталоге «{target_dir}» уже есть: {names}. '
            'Запустите с --force, чтобы перезаписать.'
        )
        raise ScaffoldExistsError(msg)

    source = resources.files(_SCAFFOLD_PACKAGE)
    created: list[Path] = []
    for name in SCAFFOLD_FILES:
        dest = target_dir / name
        dest.write_bytes((source / name).read_bytes())
        logger.info('Создан %s', dest)
        created.append(dest)
    return created
