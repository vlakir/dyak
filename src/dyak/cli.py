"""
CLI dyak (typer): команды `generate`, `check`, `init`, `reverse`.

`generate` (T006) — подстановка по заголовкам колонок; `check` (T004) —
сухой прогон с отчётом; `init` (T005) — стартовый scaffold-набор;
`reverse` (T007) — обратная генерация шаблона из готового документа.

Сам движок — склонение, рендер, чтение таблицы, обратная сборка — живёт
в библиотеке `chancellery` (T033). Здесь остаётся лицо приложения:
разбор аргументов, прогресс-бар, экспорт в PDF и scaffold.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Annotated

import typer
from chancellery import (
    ChancelleryError,
    check_table,
    decline_surnames,
    fio_overrides,
    format_check_report,
    format_reverse_report,
    gender_overrides,
    generate_documents,
    load_config,
    position_overrides,
    rank_overrides,
    read_table,
    reverse_template,
)

from dyak.errors import DyakError
from dyak.pdf import export_to_pdf
from dyak.progress import GenerateProgress
from dyak.scaffolding import init_project

logger = logging.getLogger(__name__)

app = typer.Typer(
    help='dyak — генератор кадровых документов с русским склонением.',
    add_completion=False,
)

_DEFAULT_CONFIG = Path('dyak.yaml')


def configure_stdio() -> None:
    """
    UTF-8 на stdout/stderr, если ядро запущено с `PYTHONUTF8=1` (из GUI, T023).

    Frozen-интерпретатор PyInstaller НЕ honor-ит `PYTHONUTF8` для кодировки
    потоков (проверено Windows CI: ядро падало `UnicodeEncodeError` на выводе
    кириллицы), поэтому переключаем явно: GUI выставляет подпроцессу
    `PYTHONUTF8=1` (`gui/runner.subprocess_env`), а ядро по этому флагу эмитит
    UTF-8 — совпадая с UTF-8-декодом окна лога. Прямой CLI (без `PYTHONUTF8`)
    не затрагивается: вывод в нативную консоль (cp1251 на рус. Windows) остаётся.
    """
    if os.environ.get('PYTHONUTF8') != '1':
        return
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            reconfigure(encoding='utf-8')


@app.callback()
def _main() -> None:
    """Dyak — пакетная генерация кадровых документов с русским склонением."""


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
        typer.Option(help='Опциональный dyak.yaml (по умолчанию ./dyak.yaml)'),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option(help='Имя листа (по умолчанию активный)'),
    ] = None,
    filename: Annotated[
        str | None,
        typer.Option(
            help='Шаблон имени файла (по умолчанию по колонкам ФИО), '
            'напр. "Приказ_{{ Номер_приказа }}_{{ Фамилия }}.docx"',
        ),
    ] = None,
    *,
    progress_json: Annotated[
        bool,
        typer.Option(
            '--progress-json',
            help='Машиночитаемый прогресс (JSONL-события) в stderr — для GUI',
        ),
    ] = False,
    pdf: Annotated[
        bool,
        typer.Option(
            '--pdf',
            help='Дополнительно сконвертировать вывод в PDF (нужен LibreOffice)',
        ),
    ] = False,
) -> None:
    """Сгенерировать набор документов из таблицы и шаблона."""
    try:
        written = generate_documents(
            table,
            template,
            out,
            config=config or _DEFAULT_CONFIG,
            sheet=sheet,
            filename=filename,
            progress_factory=lambda total: GenerateProgress(
                total, json_events=progress_json
            ),
        )
        pdfs = export_to_pdf(written, out) if pdf else []
    except ChancelleryError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    suffix = f' (+ {len(pdfs)} PDF)' if pdf else ''
    typer.echo(f'Готово: {len(written)} документ(ов){suffix} в {out}')


@app.command()
def check(
    table: Annotated[
        Path,
        typer.Option(help='Таблица данных (xlsx)', exists=True, dir_okay=False),
    ],
    template: Annotated[
        Path,
        typer.Option(help='Шаблон документа (docx)', exists=True, dir_okay=False),
    ],
    config: Annotated[
        Path | None,
        typer.Option(help='Опциональный dyak.yaml (по умолчанию ./dyak.yaml)'),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option(help='Имя листа (по умолчанию активный)'),
    ] = None,
) -> None:
    """Сухой прогон: проверить склонение/пол/шаблон без записи файлов."""
    try:
        cfg = load_config(config or _DEFAULT_CONFIG)
        data = read_table(table, cfg, sheet)
        report = check_table(
            data,
            template,
            gender_overrides=gender_overrides(cfg),
            decline_surnames=decline_surnames(cfg),
            fio_overrides=fio_overrides(cfg),
            position_overrides=position_overrides(cfg),
            rank_overrides=rank_overrides(cfg),
        )
    except ChancelleryError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(format_check_report(report))
    if report.fatal:
        raise typer.Exit(code=1)


@app.command()
def init(
    directory: Annotated[
        Path | None,
        typer.Option(
            '--dir',
            help='Каталог для scaffold-набора (по умолчанию текущий)',
        ),
    ] = None,
    *,
    force: Annotated[
        bool,
        typer.Option('--force', help='Перезаписать существующие файлы'),
    ] = False,
) -> None:
    """Выложить стартовый набор: dyak.yaml + пример шаблона + пример таблицы."""
    target = directory if directory is not None else Path.cwd()
    try:
        created = init_project(target, force=force)
    except DyakError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo('Создан стартовый набор dyak:')
    for path in created:
        typer.echo(f'  {path}')
    typer.echo(
        '\nДальше: отредактируйте table.xlsx и template.docx под себя '
        '(в шаблоне удалите блок «ШПАРГАЛКА»), затем\n'
        '  dyak generate --table table.xlsx --template template.docx --out out',
    )


@app.command()
def reverse(
    doc: Annotated[
        Path,
        typer.Option(
            help='Образец-документ (заполненный docx)', exists=True, dir_okay=False
        ),
    ],
    table: Annotated[
        Path,
        typer.Option(help='Таблица данных (xlsx)', exists=True, dir_okay=False),
    ],
    row: Annotated[
        int,
        typer.Option(help='Номер строки данных (1-based), из которой сделан образец'),
    ],
    out: Annotated[Path, typer.Option(help='Куда сохранить собранный шаблон (docx)')],
    config: Annotated[
        Path | None,
        typer.Option(help='Опциональный dyak.yaml (по умолчанию ./dyak.yaml)'),
    ] = None,
    sheet: Annotated[
        str | None,
        typer.Option(help='Имя листа (по умолчанию активный)'),
    ] = None,
) -> None:
    """Собрать docx-шаблон из готового документа и строки таблицы (best-effort)."""
    try:
        report = reverse_template(
            doc, table, out, row, config=config or _DEFAULT_CONFIG, sheet=sheet
        )
    except ChancelleryError as exc:
        typer.echo(f'Ошибка: {exc}', err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(format_reverse_report(report))
    typer.echo(f'\nШаблон сохранён: {out}')


if __name__ == '__main__':
    app()
