"""
CLI dyak (typer). Этап 0 (T001): команда `generate`.

Команды `check` и `init` появляются в T004/T005.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer

from dyak.config import load_config
from dyak.errors import DyakError
from dyak.io.excel import read_table
from dyak.io.naming import unique_filename
from dyak.render.context import build_context
from dyak.render.engine import render_document, render_filename

logger = logging.getLogger(__name__)

app = typer.Typer(
    help='dyak — генератор кадровых документов с русским склонением.',
    add_completion=False,
)

_DEFAULT_CONFIG = Path('dyak.yaml')


@app.callback()
def _main() -> None:
    """Dyak — пакетная генерация кадровых документов с русским склонением."""


def generate_documents(
    table: Path,
    template: Path,
    out: Path,
    config: Path,
    sheet: str | None,
) -> list[Path]:
    """Сгенерировать по документу на строку таблицы. Вернуть пути файлов."""
    cfg = load_config(config)
    people = read_table(table, cfg, sheet)
    out.mkdir(parents=True, exist_ok=True)

    used: set[str] = set()
    written: list[Path] = []
    for person in people:
        context = build_context(person)
        name = unique_filename(render_filename(cfg.filename, context), used)
        target = out / name
        render_document(template, context, target)
        written.append(target)

    logger.info('Сгенерировано документов: %d → %s', len(written), out)
    return written


@app.command()
def generate(
    table: Annotated[
        Path,
        typer.Option(help='Таблица данных (xlsx)', exists=True, dir_okay=False),
    ],
    template: Annotated[
        Path,
        typer.Option(help='Шаблон документа (docx)', exists=True, dir_okay=False),
    ],
    out: Annotated[Path, typer.Option(help='Каталог для результатов')],
    config: Annotated[
        Path | None,
        typer.Option(help='Конфиг dyak.yaml (по умолчанию ./dyak.yaml)'),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option(help='Имя листа (по умолчанию активный)'),
    ] = None,
) -> None:
    """Сгенерировать набор документов из таблицы и шаблона."""
    try:
        written = generate_documents(
            table,
            template,
            out,
            config or _DEFAULT_CONFIG,
            sheet,
        )
    except DyakError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f'Готово: {len(written)} документ(ов) в {out}')


if __name__ == '__main__':
    app()
