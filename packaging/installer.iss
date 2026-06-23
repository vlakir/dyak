; Inno Setup — инсталлятор GUI «Дьяк» (T010).
; Per-user установка без админ-прав. Запуск из корня репозитория:
;   iscc packaging\installer.iss   (VERSION берётся из переменной окружения)
; Содержимое берётся из onedir-сборки PyInstaller (dist\dyak\, см. dyak.spec).

#define MyAppName "Дьяк"
#define MyAppExeName "dyak.exe"
#define MyAppPublisher "Vladimir Kirievskiy"
#define MyAppVersion GetEnv("VERSION")

[Setup]
AppId={{8E2C4F1A-7B3D-4A9E-B6C5-2F0D1A9E4C7B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Установка в профиль пользователя без прав администратора
DefaultDirName={localappdata}\Programs\dyak
PrivilegesRequired=lowest
UsePreviousAppDir=no
DisableDirPage=auto
DefaultGroupName={#MyAppName}
OutputDir=.
OutputBaseFilename=dyak-{#MyAppVersion}-setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64os
SetupIconFile={#SourcePath}\..\src\dyak\gui\assets\icon.ico

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
; Onedir-сборка PyInstaller целиком в каталог установки
Source: "{#SourcePath}\..\dist\dyak\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
; Ярлык в меню «Пуск» и на рабочем столе текущего пользователя
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent
