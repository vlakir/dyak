"""Smoke-тесты главного окна GUI (`dyak.gui.main_window`) под offscreen.

Реальные процессы не запускаются: `_start` подменяется и проверяется собранный
argv; обработчики прогресса/итога вызываются напрямую.
"""

from __future__ import annotations

import pytest

from dyak.gui import app as app_module
from dyak.gui import main_window as mw
from dyak.gui.help_content import HELP_SECTIONS
from dyak.gui.main_window import MainWindow


class _Bytes:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def data(self) -> bytes:
        return self._payload


class _Signal:
    def connect(self, _slot) -> None:  # noqa: ANN001
        pass


class _FakeProcess:
    """Минимальная замена QProcess: фиксирует program/args и kill()."""

    last: "_FakeProcess | None" = None

    def __init__(self, _parent=None) -> None:  # noqa: ANN001
        self.program = ""
        self.arguments: list[str] = []
        self.started = False
        self.killed = False
        self.process_environment = None
        self.readyReadStandardError = _Signal()
        self.readyReadStandardOutput = _Signal()
        self.finished = _Signal()
        self._err = b""
        self._out = b""
        _FakeProcess.last = self

    def setProgram(self, program: str) -> None:  # noqa: N802
        self.program = program

    def setArguments(self, arguments: list[str]) -> None:  # noqa: N802
        self.arguments = arguments

    def setProcessEnvironment(self, env) -> None:  # noqa: ANN001, N802
        self.process_environment = env

    def start(self) -> None:
        self.started = True

    def kill(self) -> None:
        self.killed = True

    def feed_err(self, payload: bytes) -> None:
        self._err = payload

    def readAllStandardError(self):  # noqa: ANN201, N802
        data, self._err = self._err, b""
        return _Bytes(data)

    def readAllStandardOutput(self):  # noqa: ANN201, N802
        data, self._out = self._out, b""
        return _Bytes(data)


@pytest.fixture
def window(qapp):
    win = MainWindow()
    yield win
    win.close()


def test_window_has_expected_tabs(window):
    titles = [window._tabs.tabText(i) for i in range(window._tabs.count())]
    assert titles == ["Генерация", "Справка"]


def test_log_lives_only_in_generate_tab(window):
    # T030: лог/прогресс/«Отмена» — внутри вкладки «Генерация», на «Справке» их
    # нет (справка занимает всю область вкладки).
    generate_tab = window._tabs.widget(0)
    help_tab = window._tabs.widget(1)
    assert generate_tab.isAncestorOf(window._log)
    assert generate_tab.isAncestorOf(window._cancel_button)
    assert not help_tab.isAncestorOf(window._log)


def test_require_blocks_empty(window):
    assert window._require("", "таблицу") is False
    assert "таблицу" in window._status.text()
    assert window._require("ok", "таблицу") is True


def test_run_generate_builds_argv(window, monkeypatch):
    captured = {}
    monkeypatch.setattr(window, "_start", lambda argv: captured.update(argv=argv))
    window._gen_table.edit.setText("t.xlsx")
    window._gen_template.edit.setText("tpl.docx")
    window._gen_out.edit.setText("out")
    window._run_generate()
    argv = captured["argv"]
    assert "generate" in argv
    assert argv[argv.index("--table") + 1] == "t.xlsx"
    assert "--out" in argv
    assert "--progress-json" in argv


def test_run_generate_requires_fields(window, monkeypatch):
    called = False

    def fake_start(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(window, "_start", fake_start)
    window._run_generate()  # поля пустые
    assert called is False


def test_apply_progress_updates_bar(window):
    window._apply_progress({"event": "start", "total": 5})
    assert window._progress.maximum() == 5
    window._apply_progress({"event": "progress", "done": 3, "total": 5, "file": "a.docx"})
    assert window._progress.value() == 3
    assert "3/5" in window._status.text()
    assert "a.docx" in window._status.text()


def test_handle_stderr_line_routes(window):
    window._handle_stderr_line("просто предупреждение")
    assert "предупреждение" in window._log.toPlainText()
    window._handle_stderr_line('{"event": "start", "total": 2}')
    assert window._progress.maximum() == 2


def test_on_finished_success(window):
    window._stdout = "Готово: 2 документ(ов) в out"
    window._stderr = ""
    window._on_finished(0, None)
    assert "Готово" in window._status.text()
    assert window._proc is None
    assert window._progress.isVisible() is False


def test_on_finished_error(window):
    window._stdout = ""
    window._stderr = "Ошибка: нет колонки\n"
    window._on_finished(1, None)
    assert window._status.text().startswith("Ошибка:")


def test_cancel_without_process_is_safe(window):
    window._cancel()  # не должно падать
    assert window._proc is None


def test_start_wires_process(window, monkeypatch):
    monkeypatch.setattr(mw, "QProcess", _FakeProcess)
    argv = ["python", "-m", "dyak", "generate", "--table", "t.xlsx"]
    window._start(argv)
    proc = _FakeProcess.last
    assert proc.program == "python"
    assert proc.arguments == argv[1:]
    assert proc.started is True
    # T023: дочернему процессу выставлено UTF-8-окружение.
    assert proc.process_environment.value("PYTHONUTF8") == "1"
    assert window._proc is proc
    assert window._cancel_button.isEnabled() is True
    for button in window._run_buttons:
        assert button.isEnabled() is False


def test_start_refuses_second_run(window, monkeypatch):
    monkeypatch.setattr(mw, "QProcess", _FakeProcess)
    window._start(["python", "init"])
    window._start(["python", "check"])  # второй — отклонён
    assert "Дождитесь" in window._status.text()


def test_stderr_stream_splits_lines(window, monkeypatch):
    monkeypatch.setattr(mw, "QProcess", _FakeProcess)
    window._start(["python", "generate"])
    proc = _FakeProcess.last
    proc.feed_err('{"event": "start", "total": 3}\nчастичная'.encode())
    window._on_stderr()
    assert window._progress.maximum() == 3
    assert window._stderr_tail == "частичная"  # хвост без \n не обработан
    proc.feed_err(" строка\n".encode())
    window._on_stderr()
    assert "частичная строка" in window._log.toPlainText()


def test_stdout_accumulates(window, monkeypatch):
    monkeypatch.setattr(mw, "QProcess", _FakeProcess)
    window._start(["python", "init"])
    proc = _FakeProcess.last
    proc._out = "Готово".encode()
    window._on_stdout()
    assert window._stdout == "Готово"


def test_cancel_kills_process(window, monkeypatch):
    monkeypatch.setattr(mw, "QProcess", _FakeProcess)
    window._start(["python", "generate"])
    window._progress.setRange(0, 10)
    window._progress.setValue(4)
    window._cancel()
    assert _FakeProcess.last.killed is True
    assert "Остановлено" in window._status.text()
    assert "4/10" in window._status.text()


def test_help_sections_render():
    assert len(HELP_SECTIONS) >= 5
    assert all(section.html.strip().startswith("<h2>") for section in HELP_SECTIONS)


def test_load_app_icon_not_null(qapp):
    icon = app_module.load_app_icon()
    assert not icon.isNull()


def test_app_main_wires_and_returns_code(monkeypatch):
    app = app_module
    state = {}

    class _FakeApp:
        def __init__(self, _argv) -> None:  # noqa: ANN001
            state["created"] = True

        def setApplicationName(self, name: str) -> None:  # noqa: N802
            state["name"] = name

        def setWindowIcon(self, _icon) -> None:  # noqa: ANN001, N802
            state["icon"] = True

        def exec(self) -> int:
            return 0

    class _FakeWindow:
        def show(self) -> None:
            state["shown"] = True

    monkeypatch.setattr(app, "QApplication", _FakeApp)
    monkeypatch.setattr(app, "MainWindow", _FakeWindow)
    monkeypatch.setattr(app, "load_app_icon", lambda: object())
    assert app.main() == 0
    assert state == {"created": True, "name": "Дьяк", "icon": True, "shown": True}
