"""
Индикатор прогресса `generate` (T013): rich-бар + JSONL-контракт CLI↔GUI.

Пакетные прогоны объёмные (тысячи строк), поэтому `generate` показывает
живой прогресс. Два независимых канала, оба в **stderr** (stdout остаётся
чист под результат):

- **человекочитаемый бар** через `rich` — рисуется только в интерактивном
  терминале (TTY); в pipe/файл (в т.ч. под GUI или в тесте) он отключён и
  ничего не печатает;
- **машиночитаемые события** по флагу `--progress-json` — построчный JSONL
  (`{"event": "...", ...}`), который потребляет GUI (T008) через
  `subprocess`. Пишутся напрямую в stderr, поэтому корректны и тогда, когда
  бар отключён (типичный случай GUI — не-TTY).

События: `start` (всего N), `progress` (на каждый документ), `done` (итог)
или `error` (прерывание с сообщением).
"""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Self

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
)

if TYPE_CHECKING:
    from types import TracebackType


class GenerateProgress:
    """
    Контекст-менеджер прогресса `generate`.

    Использование::

        with GenerateProgress(total, json_events=flag) as progress:
            for ...:
                ...  # сгенерировать документ
                progress.advance(name)

    Бар обновляется на каждый `advance`; при `json_events` туда же (в
    stderr) идёт построчный JSONL. Выход без исключения эмитит `done`,
    выход с исключением — `error` (и не подавляет его).
    """

    def __init__(self, total: int, *, json_events: bool) -> None:
        self._total = total
        self._json = json_events
        self._done = 0
        self._progress = Progress(
            TextColumn('[progress.description]{task.description}'),
            BarColumn(),
            MofNCompleteColumn(),
            TimeRemainingColumn(),
            console=Console(stderr=True),
            disable=not sys.stderr.isatty(),
        )
        self._task = self._progress.add_task('Генерация', total=total)

    def __enter__(self) -> Self:
        self._progress.start()
        self._emit({'event': 'start', 'total': self._total})
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._progress.stop()
        if exc is None:
            self._emit(
                {'event': 'done', 'ok': self._done, 'failed': 0},
            )
        else:
            self._emit(
                {
                    'event': 'error',
                    'done': self._done,
                    'total': self._total,
                    'message': str(exc),
                },
            )

    def advance(self, file: str) -> None:
        """Отметить сгенерированный документ `file`: сдвинуть бар + событие."""
        self._done += 1
        self._progress.update(self._task, advance=1)
        self._emit(
            {
                'event': 'progress',
                'done': self._done,
                'total': self._total,
                'file': file,
            },
        )

    def _emit(self, event: dict[str, object]) -> None:
        """Записать JSON-событие в stderr (только при `--progress-json`)."""
        if not self._json:
            return
        sys.stderr.write(json.dumps(event, ensure_ascii=False) + '\n')
        sys.stderr.flush()
