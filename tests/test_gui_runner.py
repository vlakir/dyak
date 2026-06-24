"""Тесты чистого слоя GUI (`dyak.gui.runner`) — без Qt."""

from __future__ import annotations

import sys

from dyak.gui import runner


def test_base_argv_uses_current_interpreter():
    assert runner.base_argv() == [sys.executable, "-m", "dyak"]


def test_build_generate_argv_minimal():
    argv = runner.build_generate_argv("t.xlsx", "tpl.docx", "out", progress_json=False)
    assert argv == [
        sys.executable,
        "-m",
        "dyak",
        "generate",
        "--table",
        "t.xlsx",
        "--template",
        "tpl.docx",
        "--out",
        "out",
    ]


def test_build_generate_argv_full():
    argv = runner.build_generate_argv("t.xlsx", "tpl.docx", "out", config="c.yaml")
    assert "--config" in argv and "c.yaml" in argv
    assert "--progress-json" in argv  # по умолчанию для GUI


def test_build_generate_argv_skips_blank_options():
    argv = runner.build_generate_argv("t.xlsx", "tpl.docx", "out", config="  ")
    assert "--config" not in argv


def test_subprocess_env_forces_utf8():
    # T023: ядро-подпроцесс должно писать UTF-8, иначе на рус. Windows GUI
    # получает cp1251 и показывает кракозябры в окне лога.
    env = runner.subprocess_env({})
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_subprocess_env_preserves_base():
    env = runner.subprocess_env({"PATH": "/bin", "PYTHONUTF8": "0"})
    assert env["PATH"] == "/bin"  # базовое окружение сохранено
    assert env["PYTHONUTF8"] == "1"  # наш форс перекрывает


def test_parse_progress_line_valid_event():
    event = runner.parse_progress_line('{"event": "progress", "done": 2, "total": 5}')
    assert event == {"event": "progress", "done": 2, "total": 5}


def test_parse_progress_line_rejects_non_json():
    assert runner.parse_progress_line("обычный лог-варнинг") is None
    assert runner.parse_progress_line("") is None
    assert runner.parse_progress_line("   ") is None


def test_parse_progress_line_rejects_json_without_event():
    assert runner.parse_progress_line('{"done": 1}') is None
    assert runner.parse_progress_line("[1, 2, 3]") is None


def test_parse_progress_line_rejects_broken_json():
    assert runner.parse_progress_line('{"event": broken') is None


def test_extract_message_success_uses_last_stdout_line():
    msg = runner.extract_message(0, "шум\nГотово: 3 документ(ов) в out\n", "")
    assert msg == "Готово: 3 документ(ов) в out"


def test_extract_message_success_fallback():
    assert runner.extract_message(0, "   \n", "") == "Готово"


def test_extract_message_error_prefers_oshibka_line():
    stderr = '{"event": "start", "total": 1}\nОшибка: колонка не найдена\n'
    assert runner.extract_message(1, "", stderr) == "Ошибка: колонка не найдена"


def test_extract_message_error_skips_json_tail():
    stderr = 'предупреждение про колонку\n{"event": "error", "message": "x"}\n'
    assert runner.extract_message(1, "", stderr) == "предупреждение про колонку"


def test_extract_message_error_generic_when_empty():
    assert runner.extract_message(2, "", "") == "Процесс завершился с кодом 2"


def test_classify_ok():
    result = runner.classify(0, "Готово: 1 документ(ов) в out", "")
    assert result.ok is True
    assert result.exit_code == 0
    assert result.message.startswith("Готово")


def test_classify_error():
    result = runner.classify(1, "", "Ошибка: нет шаблона")
    assert result.ok is False
    assert result.message == "Ошибка: нет шаблона"
