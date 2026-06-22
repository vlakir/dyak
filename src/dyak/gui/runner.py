"""
Чистый (Qt-free) слой вызова CLI dyak: сборка argv, разбор вывода, результат.

Это тестируемое ядро GUI (ADR T008). Виджет (`main_window`) строит argv
`build_generate_argv`, гоняет процесс через `QProcess` для живого прогресса
и на каждой строке/по завершении зовёт `parse_progress_line` / `classify`.
PySide6 здесь не импортируется.

Контракт ядра (см. `cli.py`, `progress.py`):

- запуск: ``sys.executable -m dyak generate <опции>`` — тот же
  интерпретатор, надёжно в PyInstaller-бандле (T010);
- прогресс `generate --progress-json`: построчный JSONL в **stderr**
  (`start`/`progress`/`done`/`error`); человекочитаемый результат — в
  **stdout** (`Готово: N …`);
- ошибки: ненулевой код возврата, текст `Ошибка: …` в stderr
  (1 = `DyakError`, 2 = неверные аргументы typer).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    """Итог одного вызова CLI: успех/код возврата + потоки + сообщение."""

    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    message: str


def base_argv() -> list[str]:
    """Префикс запуска ядра тем же интерпретатором: ``python -m dyak``."""
    return [sys.executable, '-m', 'dyak']


def _opt(flag: str, value: str | None) -> list[str]:
    """``[flag, value]`` если значение непустое, иначе пусто."""
    text = (value or '').strip()
    return [flag, text] if text else []


def build_generate_argv(
    table: str,
    template: str,
    out: str,
    *,
    config: str | None = None,
    progress_json: bool = True,
) -> list[str]:
    """Собрать argv для ``dyak generate`` (по умолчанию с `--progress-json`)."""
    argv = [
        *base_argv(),
        'generate',
        '--table',
        table,
        '--template',
        template,
        '--out',
        out,
        *_opt('--config', config),
    ]
    if progress_json:
        argv.append('--progress-json')
    return argv


def parse_progress_line(line: str) -> dict[str, object] | None:
    """
    Разобрать строку stderr как JSONL-событие прогресса.

    Возвращает dict с ключом ``event`` (`start`/`progress`/`done`/`error`)
    либо ``None`` для всего, что не является таким событием: человекочитаемых
    логов (`logger.warning`), пустых строк, `Ошибка: …`. Никогда не бросает —
    stderr смешанный, парсер обязан это переживать (Analyze 🟡-1).
    """
    text = line.strip()
    if not text or text[0] != '{':
        return None
    try:
        data = json.loads(text)
    except ValueError:  # json.JSONDecodeError — подкласс ValueError
        return None
    if isinstance(data, dict) and isinstance(data.get('event'), str):
        return data
    return None


def _last_nonempty(text: str) -> str:
    """Последняя непустая строка текста (или пустая строка)."""
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return ''


def extract_message(exit_code: int, stdout: str, stderr: str) -> str:
    """
    Человекочитаемый итог: при успехе — финал stdout, при ошибке — текст
    ошибки из stderr (без трейсбека, см. Analyze E1).
    """
    if exit_code == 0:
        return _last_nonempty(stdout) or 'Готово'
    for line in reversed(stderr.splitlines()):
        if line.strip().startswith('Ошибка:'):
            return line.strip()
    # Не-JSON хвост stderr (warning'и/typer) либо общий код возврата.
    tail = _last_nonempty(
        '\n'.join(ln for ln in stderr.splitlines() if parse_progress_line(ln) is None),
    )
    return tail or f'Процесс завершился с кодом {exit_code}'


def classify(exit_code: int, stdout: str, stderr: str) -> CommandResult:
    """Собрать `CommandResult` из кода возврата и потоков процесса."""
    return CommandResult(
        ok=exit_code == 0,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        message=extract_message(exit_code, stdout, stderr),
    )
