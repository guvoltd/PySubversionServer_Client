; Inno Setup script for SVN Server Admin.
; Compile with ISCC.exe (Inno Setup 6) after building svn-server-admin.exe via
; PyInstaller (see scripts/package-server-windows.ps1, which runs both steps).
;
; AppId is a fixed GUID -- do not change it between releases, or Windows
; will treat upgrades as a different, unrelated application (no clean
; upgrade/uninstall of the previous version).
;
; NOTE: this installer packages the GUI only. The privileged-action helper
; (system-helper.sh + pkexec) that some repository-management actions rely
; on is Linux-specific; on Windows those actions are not currently wired up
; to an elevation path, so running the app "as Administrator" when you need
; them is the closest equivalent for now.

#define MyAppName "SVN Server Admin"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "SVN Suite"
#define MyAppExeName "svn-server-admin.exe"

[Setup]
AppId={{6CB20A40-21F5-4820-8440-B9687433C1D1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=SVN-Server-Admin-Setup
SetupIconFile=..\resources\icons\org.svnsuite.SvnServerAdmin.ico
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
