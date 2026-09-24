; YTGet Windows installer (Inno Setup 6)
;
; Wraps the PyInstaller --onedir output (dist\YTGet) into a single setup
; executable so the release page can offer a normal installer alongside the
; .zip and .7z archives.
;
; Build from the repository root:
;   iscc /DAppVersion=2.8.1 packaging\windows\ytget.iss
;
; Expects:
;   dist\YTGet\YTGet.exe   PyInstaller onedir build
;   ytget_gui\icon.ico     application icon

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#ifndef SourceDir
  #define SourceDir "..\..\dist\YTGet"
#endif

#ifndef OutputDir
  #define OutputDir "..\.."
#endif

#define AppName "YTGet"
#define AppPublisher "Erfan Namira"
#define AppURL "https://github.com/ErfanNamira/ytget-gui"
#define AppExeName "YTGet.exe"
; Must match APP_USER_MODEL_ID in ytget_gui/_version.py, or Windows
; cannot match the running window to its shortcut and falls back to the
; placeholder taskbar icon.
#define AppUserModelID "ErfanNamira.YTGet"

[Setup]
; Stable AppId: lets a newer version upgrade an existing install in place
; instead of stacking a second entry in Apps & features.
AppId=YTGet.8F3C6A62-2E0B-4C4C-9A59-2F7B1C0F5E11
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}

; Per-user install by default: no UAC prompt, and the in-app updater can
; replace files without an elevated helper. A machine-wide install is still
; offered on the first wizard page.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile=..\..\LICENSE

; x64 only: the bundled yt-dlp/ffmpeg/deno binaries are 64-bit.
; `x64compatible` needs Inno Setup 6.3; older 6.x only knows `x64`.
#if Ver >= EncodeVer(6,3,0)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
#else
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
#endif
MinVersion=10.0

OutputDir={#OutputDir}
OutputBaseFilename=YTGet-{#AppVersion}-windows-setup
SetupIconFile=..\..\ytget_gui\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startupicon"; Description: "Start {#AppName} automatically when I sign in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; recursesubdirs picks up PyInstaller's _internal tree. ignoreversion is
; required because the Qt DLLs carry version resources that would otherwise
; block a same-version reinstall or a downgrade.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Clear the previous build's bundled tree before writing the new one:
; leftover Python/Qt DLLs from another version crash the app at launch.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; AppUserModelID: "{#AppUserModelID}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon; AppUserModelID: "{#AppUserModelID}"
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Parameters: "--minimized"; Tasks: startupicon; AppUserModelID: "{#AppUserModelID}"

[Registry]
; YTGet writes this itself when "run at login" is enabled in
; Preferences (autostart.py). dontcreatekey means setup never adds it;
; uninsdeletevalue stops an uninstall from leaving a dead entry that
; Windows would try to launch at every sign-in.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#AppName}"; ValueData: ""; \
    Flags: dontcreatekey uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; PyInstaller writes .pyc files next to the bundled package at runtime; they
; are not listed in [Files], so the folder would survive an uninstall.
Type: filesandordirs; Name: "{app}\_internal"
Type: dirifempty; Name: "{app}"

[Code]
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  // Overwriting a running exe fails mid-install with a confusing "file in
  // use" error, so check first. tasklist ships with every supported Windows.
  Result := False;
  if Exec(ExpandConstant('{cmd}'),
          '/C tasklist /FI "IMAGENAME eq {#AppExeName}" | find /I "{#AppExeName}" >nul',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := (ResultCode = 0);
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if IsAppRunning() then
  begin
    if MsgBox('YTGet is still running. Close it and click Retry, or Cancel to stop the installation.',
              mbConfirmation, MB_RETRYCANCEL) = IDRETRY then
      Result := not IsAppRunning()
    else
      Result := False;

    if not Result then
      MsgBox('Setup cannot continue while YTGet is running.', mbError, MB_OK);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if IsAppRunning() then
  begin
    MsgBox('Please close YTGet before uninstalling.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  // Settings, cookies and the saved queue live in the per-user data folder,
  // outside the install directory, so they survive an uninstall unless
  // removed here. Asked, not assumed: a reinstall usually wants them kept.
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(DataDir) then
      if MsgBox('Also delete your YTGet settings, cookies and saved queue?'
                + #13#10 + DataDir, mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
