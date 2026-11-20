#ifndef MyAppVersion
  #define VersionFile FileOpen(AddBackslash(SourcePath) + "..\cntag\__init__.py")
  #define VersionLine FileRead(VersionFile)
  #expr FileClose(VersionFile)
  #define MyAppVersion Copy(VersionLine, Pos('"', VersionLine) + 1, RPos('"', VersionLine) - Pos('"', VersionLine) - 1)
#endif
#define MyAppName "CNTag"
#define MyAppPublisher "pretenderlu"
#define MyAppURL "https://github.com/pretenderlu/CNTag"

[Setup]
AppId={{8D468791-D322-4EB0-BDC1-CC1DADADC9F9}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}.0
DefaultDirName={localappdata}\Programs\CNTag
DefaultGroupName=CNTag
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=CNTagSetup-v{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\CNTag.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Files]
Source: "..\dist\CNTag\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Icons]
Name: "{autoprograms}\CNTag"; Filename: "{app}\CNTag.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\CNTag"; Filename: "{app}\CNTag.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\CNTag.exe"; Description: "启动 CNTag"; Flags: postinstall nowait
