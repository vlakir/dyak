"""
Главное окно GUI dyak (T008): вкладки «Генерация» и «Справка» + прогресс.

Базовый набор для нетехнического пользователя — только генерация
документов и встроенная офлайн-справка (решение Разработчика 2026-06-23).
Тонкий слой над `runner`: форма собирает значения, `runner` строит argv,
ядро гоняется через `QProcess` (UI не замерзает, чтение stderr — в Qt
event-loop, без ручных потоков). Прогресс берётся из JSONL-событий stderr
(`runner.parse_progress_line`), итог — из кода возврата (`runner.classify`).
Доменной логики здесь нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess, QProcessEnvironment
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from dyak.gui import runner
from dyak.gui.help_content import HELP_SECTIONS

if TYPE_CHECKING:
    from collections.abc import Callable

_DOCX = 'Документ Word (*.docx)'
_XLSX = 'Таблица Excel (*.xlsx)'


class _PathRow(QWidget):
    """Строка выбора пути: поле ввода + кнопка «Обзор…» (файл/папка)."""

    def __init__(
        self,
        mode: str,
        caption: str,
        file_filter: str = '',
    ) -> None:
        super().__init__()
        self._mode = mode
        self._caption = caption
        self._filter = file_filter
        self.edit = QLineEdit()
        button = QPushButton('Обзор…')
        button.clicked.connect(self._browse)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit)
        layout.addWidget(button)

    def value(self) -> str:
        """Текущий путь (как введён/выбран)."""
        return self.edit.text().strip()

    def _browse(self) -> None:
        if self._mode == 'open':
            path, _ = QFileDialog.getOpenFileName(self, self._caption, '', self._filter)
        elif self._mode == 'save':
            path, _ = QFileDialog.getSaveFileName(self, self._caption, '', self._filter)
        else:
            path = QFileDialog.getExistingDirectory(self, self._caption)
        if path:
            self.edit.setText(path)


class MainWindow(QMainWindow):
    """Окно dyak: вкладки «Генерация»/«Справка», прогресс-бар, панель вывода."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle('Дьяк — генератор кадровых документов')
        self.resize(720, 640)

        self._proc: QProcess | None = None
        self._stdout = ''
        self._stderr = ''
        self._stderr_tail = ''
        self._run_buttons: list[QPushButton] = []

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_generate_tab(), 'Генерация')
        self._tabs.addTab(self._build_help_tab(), 'Справка')
        root.addWidget(self._tabs)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        self._status = QLabel('Готов к работе.')
        root.addWidget(self._status)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont('monospace'))
        self._log.setMinimumHeight(160)
        root.addWidget(self._log)

        self._cancel_button = QPushButton('Отмена')
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._cancel)
        root.addWidget(self._cancel_button)

    # --- построение вкладок ------------------------------------------------

    def _build_generate_tab(self) -> QWidget:
        tab = QWidget()
        form = QFormLayout(tab)
        self._gen_table = _PathRow('open', 'Выберите таблицу', _XLSX)
        self._gen_template = _PathRow('open', 'Выберите шаблон', _DOCX)
        self._gen_out = _PathRow('dir', 'Папка для результатов')
        form.addRow('Таблица (.xlsx):', self._gen_table)
        form.addRow('Шаблон (.docx):', self._gen_template)
        form.addRow('Папка результата:', self._gen_out)
        form.addRow('', self._make_run_button('Сгенерировать', self._run_generate))
        return tab

    def _build_help_tab(self) -> QWidget:
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        html = '\n<hr/>\n'.join(section.html for section in HELP_SECTIONS)
        browser.setHtml(html)
        return browser

    def _make_run_button(self, text: str, slot: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(slot)
        self._run_buttons.append(button)
        return button

    # --- запуск команд -----------------------------------------------------

    def _run_generate(self) -> None:
        if not self._require(self._gen_table.value(), 'таблицу'):
            return
        if not self._require(self._gen_template.value(), 'шаблон'):
            return
        if not self._require(self._gen_out.value(), 'папку результата'):
            return
        argv = runner.build_generate_argv(
            self._gen_table.value(),
            self._gen_template.value(),
            self._gen_out.value(),
        )
        self._start(argv)

    def _require(self, value: str, what: str) -> bool:
        """Подсветить незаполненное обязательное поле в статусе/логе."""
        if value:
            return True
        self._status.setText(f'Укажите {what}.')
        return False

    # --- процесс -----------------------------------------------------------

    def _start(self, argv: list[str]) -> None:
        if self._proc is not None:
            self._status.setText('Дождитесь завершения текущей операции.')
            return
        self._stdout = ''
        self._stderr = ''
        self._stderr_tail = ''
        self._log.clear()
        self._set_running(running=True)
        # Неопределённый «busy»-индикатор до первого события прогресса (start).
        self._progress.setRange(0, 0)
        self._progress.setVisible(True)
        self._status.setText('Выполняется…')

        proc = QProcess(self)
        proc.setProgram(argv[0])
        proc.setArguments(argv[1:])
        # Ядро-подпроцесс пишет UTF-8 (T023): иначе на русской Windows stdout
        # уходит в cp1251, а GUI декодирует UTF-8 → кракозябры в окне лога.
        qenv = QProcessEnvironment.systemEnvironment()
        for key, value in runner.subprocess_env({}).items():
            qenv.insert(key, value)
        proc.setProcessEnvironment(qenv)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.finished.connect(self._on_finished)
        self._proc = proc
        proc.start()

    def _on_stdout(self) -> None:
        if self._proc is None:
            return
        chunk = bytes(self._proc.readAllStandardOutput().data()).decode(
            'utf-8', errors='replace'
        )
        self._stdout += chunk

    def _on_stderr(self) -> None:
        if self._proc is None:
            return
        chunk = bytes(self._proc.readAllStandardError().data()).decode(
            'utf-8', errors='replace'
        )
        self._stderr += chunk
        self._stderr_tail += chunk
        lines = self._stderr_tail.split('\n')
        self._stderr_tail = lines.pop()
        for line in lines:
            self._handle_stderr_line(line)

    def _handle_stderr_line(self, line: str) -> None:
        event = runner.parse_progress_line(line)
        if event is None:
            if line.strip():
                self._log.appendPlainText(line)
            return
        self._apply_progress(event)

    def _apply_progress(self, event: dict[str, object]) -> None:
        kind = event.get('event')
        total = event.get('total')
        done = event.get('done')
        if kind == 'start' and isinstance(total, int):
            self._progress.setRange(0, max(total, 1))
            self._progress.setValue(0)
        elif kind == 'progress' and isinstance(done, int):
            self._progress.setValue(done)
            file = event.get('file')
            shown = f' — {file}' if isinstance(file, str) else ''
            self._status.setText(f'Сгенерировано {done}/{total}{shown}')

    def _on_finished(self, exit_code: int, _status: object) -> None:
        if self._stderr_tail.strip():
            self._handle_stderr_line(self._stderr_tail)
            self._stderr_tail = ''
        result = runner.classify(exit_code, self._stdout, self._stderr)
        report = result.stdout.strip()
        if report:
            self._log.appendPlainText(report)
        self._status.setText(
            result.message if result.ok else f'Ошибка: {result.message}'
        )
        self._progress.setVisible(False)
        self._set_running(running=False)
        self._proc = None

    def _cancel(self) -> None:
        if self._proc is None:
            return
        done = self._progress.value()
        total = self._progress.maximum()
        self._proc.kill()
        self._status.setText(
            f'Остановлено пользователем на {done}/{total}. '
            'Уже созданные файлы сохранены.'
        )

    def _set_running(self, *, running: bool) -> None:
        for button in self._run_buttons:
            button.setEnabled(not running)
        self._cancel_button.setEnabled(running)
