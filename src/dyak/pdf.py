"""
Экспорт сгенерированных docx в PDF через LibreOffice headless (T012).

`generate --pdf` после генерации docx конвертирует их в PDF рядом, одним
вызовом `soffice --headless --convert-to pdf` (батч — один запуск на весь
набор). LibreOffice ищется кросс-платформенно: сначала в `PATH`, затем по
типичным путям установки (Linux / macOS / Windows). Если бинарник не
найден или конвертация не удалась — поднимаем доменную `PdfExportError`,
а вызывающий показывает понятное сообщение, а не трейсбек.

Используем прямой вызов `soffice`, а не библиотеку `docx2pdf` (та требует
установленный MS Word и не подходит под свободный LibreOffice) — ADR
2026-06-22.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from dyak.errors import PdfExportError

if TYPE_CHECKING:
    from collections.abc import Sequence

# Имена бинарника LibreOffice в PATH (Unix / Windows).
_SOFFICE_NAMES = ('soffice', 'soffice.exe')


def _candidate_paths() -> list[Path]:
    """Типичные пути установки LibreOffice вне PATH (Linux/macOS/Windows)."""
    candidates = [
        Path('/usr/bin/soffice'),
        Path('/usr/local/bin/soffice'),
        Path('/Applications/LibreOffice.app/Contents/MacOS/soffice'),
    ]
    candidates.extend(sorted(Path('/opt').glob('libreoffice*/program/soffice')))
    for env in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        base = os.environ.get(env)
        if base:
            soffice = Path(base) / 'LibreOffice' / 'program' / 'soffice.exe'
            candidates.append(soffice)
    return candidates


def find_soffice() -> Path | None:
    """Найти бинарник LibreOffice: сначала в `PATH`, затем по типичным путям."""
    for name in _SOFFICE_NAMES:
        located = shutil.which(name)
        if located:
            return Path(located)
    for candidate in _candidate_paths():
        if candidate.is_file():
            return candidate
    return None


def export_to_pdf(docx_paths: Sequence[Path], out_dir: Path) -> list[Path]:
    """
    Сконвертировать docx-файлы в PDF в `out_dir`. Вернуть пути созданных PDF.

    LibreOffice не найден или конвертация не удалась → `PdfExportError`
    (вызывающий показывает понятное сообщение, без трейсбека). Конвертация
    идёт одним батч-вызовом во временном профиле пользователя, чтобы не
    конфликтовать с уже запущенным экземпляром LibreOffice.
    """
    if not docx_paths:
        return []

    soffice = find_soffice()
    if soffice is None:
        msg = (
            'LibreOffice (soffice) не найден — PDF-экспорт недоступен. '
            'Установите LibreOffice или уберите --pdf. Искал в PATH и '
            'типичных каталогах установки (Linux/macOS/Windows).'
        )
        raise PdfExportError(msg)

    with tempfile.TemporaryDirectory(prefix='dyak-soffice-') as profile:
        command = [
            str(soffice),
            f'-env:UserInstallation={Path(profile).as_uri()}',
            '--headless',
            '--convert-to',
            'pdf',
            '--outdir',
            str(out_dir),
            *(str(path) for path in docx_paths),
        ]
        # Подавление S603 согласовано с Разработчиком 2026-06-22:
        # фиксированный argv без shell, путь к бинарнику из find_soffice(),
        # аргументы — сгенерированные приложением пути; ввода извне в argv нет.
        result = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
        )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        msg = (
            f'LibreOffice вернул код {result.returncode} '
            f'при конвертации в PDF: {detail}'
        )
        raise PdfExportError(msg)

    pdfs = [out_dir / f'{path.stem}.pdf' for path in docx_paths]
    missing = [pdf.name for pdf in pdfs if not pdf.exists()]
    if missing:
        msg = (
            'LibreOffice завершился успешно, но PDF не появились: '
            f'{", ".join(missing)}.'
        )
        raise PdfExportError(msg)
    return pdfs
