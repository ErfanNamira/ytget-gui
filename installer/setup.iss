; setup.iss — Inno Setup script for YTGet
;
; Builds a lightweight Windows installer around a "thin" PyInstaller build
; (app code + PySide6 only — no yt-dlp/ffmpeg/ffprobe/phantomjs/deno/spotdl).
; After installing, it runs download-deps.ps1 to fetch those large runtime
; tools directly onto the user's machine, instead of bundling them in the
; installer itself.
;
; Expected to be compiled from the repo root with:
;   iscc installer\setup.iss /DMyAppVersion=2.7.2 /DSourceDir=dist\YTGet
;
; MyAppVersion / SourceDir are supplied by the CI workflow; sensible
; defaults are provided below so the script also works for local testing.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0-dev"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\YTGet"
#endif

#define MyAppName "YTGet"
#define MyAppPublisher "ErfanNamira"
#define MyAppURL "https://github.com/ErfanNamira/ytget-gui"
#define MyAppExeName "YTGet.exe"

[Setup]
AppId={{2E6F6E62-9B0E-4B7B-9A0B-7C0F7B1E7C31}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=YTGet-{#MyAppVersion}-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\ytget_gui\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "fetchdeps"; Description: "Download required components now (yt-dlp, ffmpeg, PhantomJS, Deno, spotDL — recommended)"; GroupDescription: "Setup:"; Flags: checkedonce

[Files]
; The thin PyInstaller onedir output — app code + PySide6 only.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Dependency downloader, kept in the install dir so it can be re-run later
; (e.g. from a "Repair components" shortcut, or manually if setup skipped it).
Source: "download-deps.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Download Required Components"; Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\download-deps.ps1"" -TargetDir ""{app}"""; \
    IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Fetch the large runtime tools right after install, in a visible console
; window so the user can see download progress (URLs can be slow).
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\download-deps.ps1"" -TargetDir ""{app}"""; \
    WorkingDir: "{app}"; StatusMsg: "Downloading yt-dlp, ffmpeg, PhantomJS, Deno and spotDL..."; \
    Flags: waituntilterminated; Tasks: fetchdeps
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
