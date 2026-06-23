"""Тесты единой точки входа бандла (`dyak._app_entry`) — без Qt и CLI.

Проверяется разводка режимов GUI/CLI по argv и снятие префикса `-m dyak`
(механика PyInstaller-бандла T010): bootloader прокидывает весь argv в
entry, GUI зовёт ядро тем же exe через subprocess.
"""

from __future__ import annotations

import sys

from dyak import _app_entry


def test_no_args_runs_gui(monkeypatch):
    calls = {}
    monkeypatch.setattr(_app_entry, "gui_main", lambda: calls.setdefault("gui", 0) or 0)
    monkeypatch.setattr(
        _app_entry, "app", lambda: calls.setdefault("cli", True)
    )
    monkeypatch.setattr(sys, "argv", ["dyak"])

    rc = _app_entry.run()

    assert rc == 0
    assert "gui" in calls
    assert "cli" not in calls


def test_gui_return_code_propagates(monkeypatch):
    monkeypatch.setattr(_app_entry, "gui_main", lambda: 7)
    monkeypatch.setattr(sys, "argv", ["dyak"])

    assert _app_entry.run() == 7


def test_args_run_cli(monkeypatch):
    seen = {}
    monkeypatch.setattr(_app_entry, "app", lambda: seen.update(argv=list(sys.argv)))
    monkeypatch.setattr(
        _app_entry, "gui_main", lambda: seen.setdefault("gui", True)
    )
    monkeypatch.setattr(sys, "argv", ["dyak", "generate", "--table", "t.xlsx"])

    rc = _app_entry.run()

    assert rc == 0
    assert "gui" not in seen
    assert seen["argv"] == ["dyak", "generate", "--table", "t.xlsx"]


def test_strips_dash_m_dyak_prefix(monkeypatch):
    seen = {}
    monkeypatch.setattr(_app_entry, "app", lambda: seen.update(argv=list(sys.argv)))
    monkeypatch.setattr(sys, "argv", ["dyak", "-m", "dyak", "generate", "--out", "o"])

    rc = _app_entry.run()

    assert rc == 0
    # Префикс `-m dyak` снят, команда передана ядру как обычный argv
    assert seen["argv"] == ["dyak", "generate", "--out", "o"]


def test_bare_dash_m_dyak_falls_back_to_gui(monkeypatch):
    """`-m dyak` без команды (теоретический пустой вызов) → GUI."""
    calls = {}
    monkeypatch.setattr(_app_entry, "gui_main", lambda: calls.setdefault("gui", 0) or 0)
    monkeypatch.setattr(sys, "argv", ["dyak", "-m", "dyak"])

    assert _app_entry.run() == 0
    assert "gui" in calls
