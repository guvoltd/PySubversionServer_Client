; Inno Setup script for SVN Client.
; Compile with ISCC.exe (Inno Setup 6) after building svn-client.exe via
; PyInstaller (see scripts/package-client-windows.ps1, which runs both steps).
;
; AppId is a fixed GUID -- do not change it between releases, or Windows
; will treat upgrades as a different, unrelated application (no clean
; upgrade/uninstall of the previous version).

#define MyAppName "SVN Client"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SVN Suite"
#define MyAppExeName "svn-client.exe"

[Setup]
AppId={{9BF5C8F1-4184-4C69-83CB-A919C72D63EC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SVN-Client-Setup
SetupIconFile=..\resources\icons\org.svnsuite.SvnClient.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\pyinstaller\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
