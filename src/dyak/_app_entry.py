"""
Единая точка входа PyInstaller-бандла «Дьяк» (T010).

В собранном виде GUI и CLI-ядро живут в одном exe: при двойном клике
(без аргументов) поднимается окно, а когда GUI зовёт ядро через
subprocess (`sys.executable -m dyak generate …`), тот же exe должен
отработать как CLI. Bootloader PyInstaller не интерпретирует `-m`, а
прокидывает весь `argv` сюда — поэтому префикс `-m dyak` снимаем сами и
по наличию команды разводим режим. Так `runner.base_argv()` остаётся
неизменным и одинаково работает из исходников и из бандла.
"""

from __future__ import annotations

import sys

from dyak.cli import app
from dyak.gui.app import main as gui_main


def run() -> int:
    """GUI без аргументов, иначе — CLI-ядро (тот же exe из subprocess)."""
    argv = sys.argv[1:]
    if argv[:2] == ['-m', 'dyak']:  # subprocess-вызов ядра из GUI-бандла
        argv = argv[2:]
    if argv:
        sys.argv = ['dyak', *argv]
        app()
        return 0
    return gui_main()


if __name__ == '__main__':
    raise SystemExit(run())
