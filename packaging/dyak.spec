# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-сборка GUI «Дьяк» (T010): два таргета из одного Analysis.

Единая точка входа `dyak._app_entry` разводит режимы: без аргументов окно,
с аргументами CLI-ядро (GUI зовёт ядро тем же exe через subprocess).

- **onedir** (`dist/dyak/`) — для инсталлятора (Inno пакует папку).
- **onefile** (`dist/dyak-portable[.exe]`) — portable: один self-extracting
  exe без папок. Спайк T010 подтвердил: self-relaunch ядра работает и в
  onefile (повторная распаковка во временную папку, ~секунды).

Запуск из корня репозитория: `pyinstaller packaging/dyak.spec`.
"""

import os

from PyInstaller.utils.hooks import collect_all

# .spec — не обычный Python: Analysis/PYZ/EXE/COLLECT/SPECPATH вбрасывает
# PyInstaller при выполнении файла. Поэтому spec не входит в ruff/mypy-гейт
# (ruff обходит не-.py; стандартно для PyInstaller-спек).
# Пути — относительно корня репозитория (spec лежит в packaging/).
ROOT = os.path.dirname(SPECPATH)
SRC = os.path.join(ROOT, 'src')

# GUI-ассеты: load_app_icon() читает icon.png через importlib.resources —
# в бандле ресурс должен лежать под dyak/gui/assets.
datas = [(os.path.join(SRC, 'dyak', 'gui', 'assets'), 'dyak/gui/assets')]
binaries = []
hiddenimports = []

# Package-data зависимостей ядра (склонение ФИО/должностей). Без них бандл
# падает на petrovich/rules/rules.json и словарях pymorphy3 (выявлено
# спайком T010).
for _pkg in ('petrovich', 'pymorphy3', 'pymorphy3_dicts_ru'):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h

a = Analysis(
    [os.path.join(SRC, 'dyak', '_app_entry.py')],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='dyak',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed GUI; subprocess-ядро пишет в QProcess-пайпы
    disable_windowed_traceback=True,  # ошибки идут в лог, не во всплывающее окно (T026)
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SRC, 'dyak', 'gui', 'assets', 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='dyak',  # → dist/dyak/ (для инсталлятора, Inno пакует папку)
)

# Portable — единый self-extracting exe (onefile): один файл, без папок.
# Тот же Analysis, но binaries/datas инлайнятся в exe, без COLLECT.
exe_portable = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='dyak-portable',  # → dist/dyak-portable[.exe]
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,  # ошибки идут в лог, не во всплывающее окно (T026)
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(SRC, 'dyak', 'gui', 'assets', 'icon.ico'),
)
