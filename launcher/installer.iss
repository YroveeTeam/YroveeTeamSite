; Скрипт установщика для Inno Setup (бесплатно: jrsoftware.org). Запускать после build_exe.bat
[Setup]
AppName=YroveeLauncher
AppVersion=0.10
DefaultDirName={autopf}\YroveeLauncher
DefaultGroupName=YroveeLauncher
PrivilegesRequired=lowest
OutputBaseFilename=YroveeLauncher-Setup
OutputDir=installer
SetupIconFile=assets\icon.ico
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\YroveeLauncher.exe

[Files]
Source: "dist\YroveeLauncher\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\YroveeLauncher"; Filename: "{app}\YroveeLauncher.exe"
Name: "{autodesktop}\YroveeLauncher"; Filename: "{app}\YroveeLauncher.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"

[Run]
Filename: "{app}\YroveeLauncher.exe"; Description: "Запустить YroveeLauncher"; Flags: nowait postinstall skipifsilent
